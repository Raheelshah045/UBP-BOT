"""Queue management and continuous folder monitoring service.

Coordinates automatic startup scanning, filesystem monitoring, stability checks,
file lifecycle transitions (input -> processing -> completed/failed), and sequential processing.
"""

import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from playwright.sync_api import Page

from src.auth_manager import check_is_session_expired, ensure_portal_authenticated
from src.browser_manager import (
    get_active_browser_page,
    launch_persistent_browser_session,
)
from src.checkpoint import (
    init_checkpoint_db,
    is_file_already_completed,
    is_file_already_processed,
    record_file_history,
)
from src.file_detector import (
    compute_file_sha256,
    identify_system_target,
    is_file_locked_or_changing,
    move_file_safely,
    scan_directory_for_candidate_files,
    validate_file_structure,
)
from src.logger import get_logger, log_event
from src.runner import run_batch_automation

_QUEUE: List[Path] = []
_QUEUE_LOCK = threading.Lock()
_MONITORING_ACTIVE = False
_IS_PAUSED = False
_CURRENT_PROCESSING_FILE: Optional[Path] = None


def set_monitoring_state(active: bool) -> None:
    """Toggle continuous monitoring loop active status."""
    global _MONITORING_ACTIVE
    _MONITORING_ACTIVE = active


def is_monitoring_active() -> bool:
    """Check if continuous monitoring is currently active."""
    return _MONITORING_ACTIVE


def set_processing_paused(paused: bool) -> None:
    """Set pause state for the active file processing queue."""
    global _IS_PAUSED
    _IS_PAUSED = paused


def is_processing_paused() -> bool:
    """Check if the processing queue is currently paused."""
    return _IS_PAUSED


def get_current_processing_filename() -> str:
    """Return the name of the file currently being processed."""
    return _CURRENT_PROCESSING_FILE.name if _CURRENT_PROCESSING_FILE else "None"


def get_queued_files_count() -> int:
    """Return count of files currently waiting in the processing queue."""
    with _QUEUE_LOCK:
        return len(_QUEUE)


def clear_processing_queue() -> None:
    """Clear all pending file paths from the queue in memory."""
    with _QUEUE_LOCK:
        _QUEUE.clear()


def enqueue_file_if_new(file_path: Path) -> bool:
    """Safely append a file path to the processing queue if not already queued.

    Args:
        file_path: Validated candidate spreadsheet file.

    Returns:
        bool: True if newly enqueued; False if already present in queue.
    """
    with _QUEUE_LOCK:
        for existing in _QUEUE:
            if existing.resolve() == file_path.resolve():
                return False
        if _CURRENT_PROCESSING_FILE and _CURRENT_PROCESSING_FILE.resolve() == file_path.resolve():
            return False
        _QUEUE.append(file_path)
        return True


def pop_next_queued_file() -> Optional[Path]:
    """Pop the next available file from the processing queue.

    Returns:
        Optional[Path]: Next file to process, or None if queue is empty.
    """
    with _QUEUE_LOCK:
        if _QUEUE:
            return _QUEUE.pop(0)
        return None


def execute_startup_scan(
    input_dir: Path,
    db_path: Path,
    force_reprocess: bool = False,
    allowed_target_system: Optional[str] = None,
) -> List[Path]:
    """Scan input folder on startup and enqueue all existing eligible files.

    Args:
        input_dir: Monitored input folder.
        db_path: Path to checkpoint database.
        force_reprocess: If True, re-enqueues files even if completed earlier.
        allowed_target_system: Optional filter to restrict scanning ("otc" or "gnb").

    Returns:
        List[Path]: Newly discovered and enqueued file paths.
    """
    logger = get_logger("queue_manager")
    candidates = scan_directory_for_candidate_files(input_dir)
    enqueued: List[Path] = []

    for item in candidates:
        if allowed_target_system and identify_system_target(item) != allowed_target_system:
            continue
        file_hash = compute_file_sha256(item)
        if not force_reprocess and is_file_already_completed(db_path, file_hash):
            log_event(
                logger,
                20,
                f"[OTC] Startup scan: Skipping already processed file '{item.name}'.",
            )
            continue

        if enqueue_file_if_new(item):
            enqueued.append(item)
            log_event(logger, 20, f"[OTC] Startup scan: Enqueued candidate file '{item.name}'.")

    return enqueued


def process_single_queued_file(
    file_path: Path,
    config: Dict[str, Any],
    page: Page,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_message: Optional[Callable[[str], None]] = None,
) -> Optional[Path]:
    """Move candidate file to processing/, execute batch automation, and archive upon completion.

    Args:
        file_path: Source input spreadsheet path.
        config: Central configuration dictionary.
        page: Active Playwright page handle.
        on_progress: Progress update callback.
        on_message: Status message callback.

    Returns:
        Optional[Path]: Generated report path if successful, None otherwise.
    """
    global _CURRENT_PROCESSING_FILE
    logger = get_logger("queue_manager")

    dirs = config.get("directories", {})
    proc_dir = Path(dirs.get("processing_dir", "processing"))
    completed_dir = Path(dirs.get("completed_dir", "completed"))
    failed_dir = Path(dirs.get("failed_dir", "failed"))
    out_dir = Path(dirs.get("output_dir", "output"))
    db_path = Path(
        config.get("storage", {}).get("checkpoint_db_path", "checkpoints/processing_checkpoint.db")
    )

    try:
        # 1. Stability verification (fast 0.4s check)
        if on_message:
            on_message(f"Verifying '{file_path.name}' is ready to read...")
        if is_file_locked_or_changing(file_path, interval_seconds=0.2, required_stable_checks=2):
            log_event(logger, 30, f"File '{file_path.name}' is busy or open in Excel. Postponing.")
            if on_message:
                on_message(f"File '{file_path.name}' is locked. If open in Excel, please close it.")
            return None

        # 2. System routing identification & Structure validation
        target_sys = identify_system_target(file_path)
        if target_sys == "unknown":
            err_msg = (
                f"Cannot identify system target for '{file_path.name}'. "
                "Filename must contain 'OTC' or 'GNB' (e.g. OTC_Transactions.xlsx). "
                "Moved to failed/ for manual review."
            )
            log_event(logger, 40, err_msg)
            moved_failed = move_file_safely(file_path, failed_dir)
            file_hash = compute_file_sha256(moved_failed)
            record_file_history(db_path, file_hash, moved_failed.name, str(moved_failed), "FAILED")
            if on_message:
                on_message(f"Ambiguous file routed to failed/: {file_path.name}")
            return None

        struct_check = validate_file_structure(file_path)
        if not struct_check["is_valid"]:
            err_msg = struct_check["error"] or "Invalid structure"
            log_event(logger, 40, f"Validation error for '{file_path.name}': {err_msg}")
            moved_failed = move_file_safely(file_path, failed_dir)
            file_hash = compute_file_sha256(moved_failed)
            record_file_history(db_path, file_hash, moved_failed.name, str(moved_failed), "FAILED")
            if on_message:
                on_message(f"Moved invalid file to failed/: {file_path.name} ({err_msg})")
            return None

        row_count = struct_check.get("row_count", 0)
        if on_message:
            on_message(f"Validated '{file_path.name}' ({row_count} rows). Moving to processing...")

        # 3. Deduplication check
        file_hash = compute_file_sha256(file_path)
        if is_file_already_processed(db_path, file_hash):
            log_event(
                logger, 20, f"Duplicate file '{file_path.name}' previously processed. Skipping."
            )
            if on_message:
                on_message(f"Duplicate file skipped: {file_path.name}")
            return None

        # 4. Move from input/ to processing/
        try:
            processing_file = move_file_safely(file_path, proc_dir)
        except Exception as move_err:
            log_event(logger, 30, f"Cannot move '{file_path.name}': {move_err}")
            if on_message:
                on_message(f"File locked by another process: {file_path.name}")
            return None

        _CURRENT_PROCESSING_FILE = processing_file
        record_file_history(
            db_path, file_hash, processing_file.name, str(processing_file), "IN_PROGRESS"
        )

        if on_message:
            on_message(f"[{target_sys.upper()}] Starting transaction extraction for: {processing_file.name}")
        log_event(logger, 20, f"[{target_sys.upper()}] Moved '{file_path.name}' to processing folder.")

        # 5. Execute batch run according to target system
        if target_sys == "gnb":
            from src.excel_reporter import generate_gnb_rejected_report
            from src.gnb_client import run_gnb_extraction_pipeline

            gnb_txs = run_gnb_extraction_pipeline(
                config=config,
                input_file_path=processing_file,
                on_message=on_message,
                keep_browser_open=False,
            )
            report_path = generate_gnb_rejected_report(out_dir, gnb_txs)
        else:
            report_path = run_batch_automation(
                config=config,
                input_file_path=processing_file,
                output_dir=out_dir,
                on_progress=on_progress,
                on_message=on_message,
                keep_browser_open=True,
            )

        if report_path and report_path.exists():
            moved_completed = move_file_safely(processing_file, completed_dir)
            record_file_history(
                db_path,
                file_hash,
                moved_completed.name,
                str(moved_completed),
                "COMPLETED",
                str(report_path),
            )
            log_event(logger, 20, f"File '{moved_completed.name}' completed and archived.")
            if on_message:
                on_message(f"Completed and archived: {moved_completed.name}")
            return report_path
        else:
            moved_failed = move_file_safely(processing_file, failed_dir)
            record_file_history(db_path, file_hash, moved_failed.name, str(moved_failed), "FAILED")
            log_event(logger, 40, f"File processing failed: '{moved_failed.name}'.")
            if on_message:
                on_message(f"Processing failed. Moved to failed/: {moved_failed.name}")
            return None

    except Exception as exc:
        log_event(logger, 40, f"Exception processing '{file_path.name}': {exc}")
        if on_message:
            on_message(f"Error processing {file_path.name}: {exc}")
        return None
    finally:
        _CURRENT_PROCESSING_FILE = None


def start_continuous_monitoring_worker(
    config: Dict[str, Any],
    on_queue_update: Optional[Callable[[int, str], None]] = None,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_message: Optional[Callable[[str], None]] = None,
    on_portal_status: Optional[Callable[[str], None]] = None,
    allowed_target_system: Optional[str] = "otc",
) -> None:
    """Continuous monitoring and processing loop running in background thread.

    Args:
        config: Full configuration dictionary.
        on_queue_update: Hook reporting (queued_count, current_filename).
        on_progress: Hook reporting batch row progress.
        on_message: Hook delivering text log messages.
        on_portal_status: Hook reporting portal auth state.
        allowed_target_system: Filter to isolate scanning ("otc" or "gnb").
    """
    global _MONITORING_ACTIVE, _IS_PAUSED
    _MONITORING_ACTIVE = True
    _IS_PAUSED = False

    logger = get_logger("queue_manager")
    dirs = config.get("directories", {})
    input_dir = Path(dirs.get("input_dir", "input"))
    db_path = Path(
        config.get("storage", {}).get("checkpoint_db_path", "checkpoints/processing_checkpoint.db")
    )
    init_checkpoint_db(db_path)

    log_event(logger, 20, f"[OTC] Starting continuous monitoring on: {input_dir.resolve()}")
    if on_message:
        on_message(f"[OTC] Directory monitoring active on: {input_dir.name}/")

    # Step 1: Automatic startup scan
    execute_startup_scan(input_dir, db_path, allowed_target_system=allowed_target_system)

    # Step 2: Initialize or connect to persistent browser and load portal immediately
    browser_cfg = config.get("browser", {})
    portal_cfg = config.get("portal", {})
    login_url = portal_cfg.get("login_url", "http://localhost:5173/")
    check_bill_url = portal_cfg.get("check_bill_url")
    selectors = config.get("selectors", {})

    if on_portal_status:
        on_portal_status("Opening Portal...")
    if on_message:
        on_message(f"[OTC] Connecting browser to configured portal: {login_url}")

    _, _, page = launch_persistent_browser_session(browser_cfg, initial_url=login_url)
    if page and not page.is_closed():
        try:
            if page.url in ("about:blank", ""):
                page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
            if on_portal_status:
                on_portal_status("Portal Opened")
        except Exception as nav_err:
            log_event(logger, 30, f"Initial navigation to {login_url} notice: {nav_err}")
            if on_message:
                on_message(f"[OTC] Notice: Cannot connect to {login_url}. Please check that portal is running.")
            if on_portal_status:
                on_portal_status("Connection Notice")

    # Step 3: Main Continuous Loop
    poll_sec = config.get("monitoring", {}).get("poll_interval_seconds", 2.0)
    while _MONITORING_ACTIVE:
        try:
            if _IS_PAUSED:
                if on_portal_status:
                    on_portal_status("Paused by User")
                time.sleep(1.0)
                continue

            # Check browser health
            active_page = get_active_browser_page()
            if not active_page or active_page.is_closed():
                if on_portal_status:
                    on_portal_status("Browser Disconnected")
                _, _, page = launch_persistent_browser_session(browser_cfg)

            # Check for newly dropped files in input_dir
            candidate_files = scan_directory_for_candidate_files(input_dir)
            for cand in candidate_files:
                if allowed_target_system and identify_system_target(cand) != allowed_target_system:
                    continue
                file_h = compute_file_sha256(cand)
                if not is_file_already_completed(db_path, file_h):
                    enqueue_file_if_new(cand)

            if on_queue_update:
                on_queue_update(get_queued_files_count(), get_current_processing_filename())

            # If files are queued, ensure portal authentication before processing
            next_file = pop_next_queued_file()
            if next_file:
                if on_portal_status:
                    on_portal_status("Checking Portal Session...")

                is_authed = ensure_portal_authenticated(
                    page=page,
                    login_url=login_url,
                    check_bill_url=check_bill_url,
                    selectors=selectors,
                    on_message_callback=on_message,
                )

                if not is_authed:
                    if on_portal_status:
                        on_portal_status("Authentication Required")
                    with _QUEUE_LOCK:
                        _QUEUE.insert(0, next_file)
                    time.sleep(2.0)
                    continue

                if on_portal_status:
                    on_portal_status("Session Active (BPS)")

                process_single_queued_file(
                    file_path=next_file,
                    config=config,
                    page=page,
                    on_progress=on_progress,
                    on_message=on_message,
                )

                # Check if session expired during batch
                if check_is_session_expired(page, selectors):
                    if on_portal_status:
                        on_portal_status("Session Expired")
                    if on_message:
                        on_message("[OTC] Session expired after file processing. Manual re-login needed.")

        except Exception as loop_err:
            log_event(logger, 40, f"Error in monitoring loop: {loop_err}")
            if on_message:
                on_message(f"[OTC] Monitoring notice: {loop_err}")

        time.sleep(poll_sec)

    log_event(logger, 20, "[OTC] Continuous monitoring worker terminated.")
