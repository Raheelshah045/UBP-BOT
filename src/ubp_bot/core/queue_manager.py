"""Queue management and continuous folder monitoring service for UBP Bot.

Coordinates automatic startup scanning, filesystem monitoring, stability checks,
file lifecycle transitions (input -> processing -> completed/failed), and sequential processing.
"""

import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.ubp_bot.core.config import resolve_app_path, safe_int_setting
from src.ubp_bot.core.file_detector import (
    compute_file_sha256,
    identify_system_target,
    is_file_locked_or_changing,
    move_file_safely,
    scan_directory_for_candidate_files,
    validate_file_structure,
)
from src.ubp_bot.core.pipeline import (
    init_checkpoint_db,
    is_file_already_completed,
    record_file_history,
    run_batch_automation,
)
from src.ubp_bot.security.log_sanitizer import get_logger, log_event

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
    """Safely append a file path to the processing queue if not already queued."""
    with _QUEUE_LOCK:
        for existing in _QUEUE:
            if existing.resolve() == file_path.resolve():
                return False
        if _CURRENT_PROCESSING_FILE and _CURRENT_PROCESSING_FILE.resolve() == file_path.resolve():
            return False
        _QUEUE.append(file_path)
        return True


def pop_next_queued_file() -> Optional[Path]:
    """Pop the next waiting file path from the front of the FIFO queue."""
    with _QUEUE_LOCK:
        if _QUEUE:
            return _QUEUE.pop(0)
        return None


def execute_startup_directory_scan(
    input_dir: Path,
    on_file_found: Optional[Callable[[Path], None]] = None,
    allowed_target_system: Optional[str] = None,
) -> List[Path]:
    """Scan input folder on startup for candidate files left from previous sessions."""
    logger = get_logger("queue_manager")
    candidates = scan_directory_for_candidate_files(input_dir)
    enqueued: List[Path] = []

    for file_path in candidates:
        target_sys = identify_system_target(file_path)
        if allowed_target_system and target_sys != "unknown":
            if target_sys.lower() != allowed_target_system.lower():
                continue

        if enqueue_file_if_new(file_path):
            enqueued.append(file_path)
            log_event(logger, 20, f"Startup scan detected and enqueued: {file_path.name}")
            if on_file_found:
                on_file_found(file_path)

    return enqueued


def process_queue_item(
    file_path: Path,
    config: Dict[str, Any],
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_message: Optional[Callable[[str], None]] = None,
    stop_check: Optional[Callable[[], bool]] = None,
) -> bool:
    """Process a single file through the full validation and execution lifecycle."""
    global _CURRENT_PROCESSING_FILE
    logger = get_logger("queue_manager")

    dirs_cfg = config.get("directories", {})
    processing_dir = resolve_app_path(dirs_cfg.get("processing_dir", "processing"))
    completed_dir = resolve_app_path(dirs_cfg.get("completed_dir", "completed"))
    failed_dir = resolve_app_path(dirs_cfg.get("failed_dir", "failed"))
    output_dir = resolve_app_path(dirs_cfg.get("output_dir", "output"))

    storage_cfg = config.get("storage", {})
    db_path = resolve_app_path(
        storage_cfg.get("checkpoint_db_path", "checkpoints/processing_checkpoint.db")
    )
    init_checkpoint_db(db_path)

    _CURRENT_PROCESSING_FILE = file_path
    log_event(logger, 20, f"Beginning queue processing for: {file_path.name}")
    if on_message:
        on_message(f"Checking write stability for: {file_path.name}")

    # 1. Stability validation
    if is_file_locked_or_changing(file_path, interval_seconds=0.8, required_stable_checks=2):
        log_event(logger, 30, f"File {file_path.name} is currently locked or writing. Re-queuing.")
        _CURRENT_PROCESSING_FILE = None
        enqueue_file_if_new(file_path)
        return False

    # 2. Hash calculation and duplicate prevention
    file_hash = compute_file_sha256(file_path)
    if is_file_already_completed(db_path, file_hash):
        log_event(logger, 30, f"File {file_path.name} (SHA-256: {file_hash[:8]}) already completed. Archiving.")
        if on_message:
            on_message(f"Duplicate file already completed: {file_path.name}. Archiving.")
        move_file_safely(file_path, completed_dir)
        _CURRENT_PROCESSING_FILE = None
        return True

    # 3. Structural validation
    structure_check = validate_file_structure(file_path)
    if not structure_check["is_valid"]:
        err = structure_check["error"]
        log_event(logger, 40, f"Validation error for {file_path.name}: {err}. Moving to failed.")
        if on_message:
            on_message(f"Invalid file structure ({file_path.name}): {err}")
        failed_path = move_file_safely(file_path, failed_dir)
        record_file_history(db_path, file_hash, file_path.name, str(failed_path), "FAILED", None)
        _CURRENT_PROCESSING_FILE = None
        return False

    # 4. Move to processing
    active_path = move_file_safely(file_path, processing_dir)
    _CURRENT_PROCESSING_FILE = active_path

    # 5. Route to appropriate automation runner
    target_system = identify_system_target(active_path)
    report_path: Optional[Path] = None

    if target_system == "gnb":
        log_event(logger, 20, f"Routing {active_path.name} to GNB System extraction pipeline.")
        from src.ubp_bot.portals.gnb_client import run_gnb_extraction_pipeline
        from src.ubp_bot.services.excel_reporter import generate_gnb_rejected_report

        gnb_txs = run_gnb_extraction_pipeline(
            config,
            input_file_path=active_path,
            on_message=on_message,
        )
        report_path = generate_gnb_rejected_report(output_dir, gnb_txs)
    else:
        # Default to OTC
        log_event(logger, 20, f"Routing {active_path.name} to OTC BPS automation runner.")
        report_path = run_batch_automation(
            config=config,
            input_file_path=active_path,
            output_dir=output_dir,
            on_progress=on_progress,
            on_message=on_message,
            keep_browser_open=True,
            stop_check=stop_check,
        )

    # 6. Archive to completed or failed
    if report_path and report_path.exists():
        final_path = move_file_safely(active_path, completed_dir)
        record_file_history(
            db_path, file_hash, file_path.name, str(final_path), "COMPLETED", str(report_path)
        )
        log_event(logger, 20, f"Completed processing {file_path.name}. Archived to {final_path.name}")
        if on_message:
            on_message(f"Completed and archived: {file_path.name}")
        _CURRENT_PROCESSING_FILE = None
        return True
    else:
        final_path = move_file_safely(active_path, failed_dir)
        record_file_history(
            db_path, file_hash, file_path.name, str(final_path), "FAILED", None
        )
        log_event(logger, 40, f"Execution failed for {file_path.name}. Moved to failed directory.")
        if on_message:
            on_message(f"Execution failed for: {file_path.name}")
        _CURRENT_PROCESSING_FILE = None
        return False


def start_continuous_monitoring_worker(
    config: Dict[str, Any],
    on_queue_update: Optional[Callable[[int, str], None]] = None,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_message: Optional[Callable[[str], None]] = None,
    on_portal_state_change: Optional[Callable[[str], None]] = None,
    allowed_target_system: Optional[str] = None,
) -> None:
    """Run background directory polling loop continuously processing pending queue items."""
    logger = get_logger("queue_manager")
    dirs_cfg = config.get("directories", {})
    input_dir = resolve_app_path(dirs_cfg.get("input_dir", "input"))
    try:
        poll_interval = float(str(config.get("monitoring", {}).get("poll_interval_seconds", 3.0)).strip())
        if poll_interval <= 0:
            poll_interval = 3.0
    except (TypeError, ValueError):
        poll_interval = 3.0

    set_monitoring_state(True)
    log_event(logger, 20, f"Continuous directory monitoring worker started for: {input_dir}")

    # Startup scan
    execute_startup_directory_scan(
        input_dir,
        allowed_target_system=allowed_target_system,
    )
    if on_queue_update:
        on_queue_update(get_queued_files_count(), get_current_processing_filename())

    while is_monitoring_active():
        try:
            # Poll input folder for new files
            new_files = scan_directory_for_candidate_files(input_dir)
            for f in new_files:
                target_sys = identify_system_target(f)
                if allowed_target_system and target_sys != "unknown":
                    if target_sys.lower() != allowed_target_system.lower():
                        continue

                if enqueue_file_if_new(f):
                    log_event(logger, 20, f"New file discovered and queued: {f.name}")
                    if on_message:
                        on_message(f"Queued new file: {f.name}")

            if on_queue_update:
                on_queue_update(get_queued_files_count(), get_current_processing_filename())

            # Process next item if not paused
            if not is_processing_paused():
                next_file = pop_next_queued_file()
                if next_file and next_file.exists():
                    if on_queue_update:
                        on_queue_update(get_queued_files_count(), next_file.name)

                    process_queue_item(
                        file_path=next_file,
                        config=config,
                        on_progress=on_progress,
                        on_message=on_message,
                    )

                    if on_queue_update:
                        on_queue_update(get_queued_files_count(), "None")

            time.sleep(poll_interval)
        except Exception as exc:
            log_event(logger, 40, f"Error in continuous monitoring loop: {exc}")
            time.sleep(poll_interval)

    log_event(logger, 20, "Continuous directory monitoring worker stopped.")
