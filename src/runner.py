"""Orchestration runner module for the OTC Bot.

Coordinates input ingestion, browser automation, search execution,
transaction classification, checkpointing, and Excel report generation.
"""

import hashlib
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.auth_manager import check_is_session_expired, ensure_portal_authenticated
from src.browser_manager import (
    close_browser_session,
    get_active_browser_page,
    launch_persistent_browser_session,
)
from src.checkpoint import (
    get_batch_summary,
    get_processed_row_numbers,
    init_checkpoint_db,
    record_row_result,
    register_batch,
    save_transactions,
)
from src.classifier import classify_transaction
from src.excel_reporter import generate_otc_rejected_report
from src.input_processor import process_input_file
from src.logger import get_logger, log_event
from src.portal_navigator import navigate_to_check_bill_status
from src.search_service import execute_transaction_search
from src.state_detector import is_check_bill_screen_present, is_portal_authenticated
from src.table_extractor import extract_all_transactions

_IS_PAUSED: bool = False
_IS_STOPPED: bool = False


def _check_cancellation() -> bool:
    """Check if either the batch stop flag or monitoring loop has been cancelled."""
    if _IS_STOPPED:
        return True
    try:
        from src.queue_manager import is_monitoring_active

        return not is_monitoring_active()
    except Exception:
        return False


def set_pause_state(paused: bool) -> None:
    """Set pause state for the running automation batch."""
    global _IS_PAUSED
    _IS_PAUSED = paused


def set_stop_state(stopped: bool) -> None:
    """Signal the automation batch to stop and persist current checkpoint."""
    global _IS_STOPPED
    _IS_STOPPED = stopped


def is_paused() -> bool:
    """Check if processing is paused."""
    return _IS_PAUSED


def is_stopped() -> bool:
    """Check if processing has been cancelled or stopped."""
    return _IS_STOPPED


def compute_batch_id(input_file_path: Path) -> str:
    """Generate a consistent unique batch ID based on file path and modification timestamp.

    Args:
        input_file_path: Path to the target spreadsheet file.

    Returns:
        str: Hexadecimal string identifying the batch.
    """
    hasher = hashlib.sha256()
    hasher.update(str(input_file_path.resolve()).encode("utf-8"))
    if input_file_path.exists():
        hasher.update(str(input_file_path.stat().st_mtime).encode("utf-8"))
    return f"batch_{hasher.hexdigest()[:12]}"


def run_batch_automation(
    config: Dict[str, Any],
    input_file_path: Path,
    output_dir: Optional[Path] = None,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_message: Optional[Callable[[str], None]] = None,
    keep_browser_open: bool = True,
) -> Optional[Path]:
    """Execute the end-to-end OTC transaction monitoring and extraction workflow.

    Args:
        config: Full configuration dictionary.
        input_file_path: Path to the input Excel or CSV file.
        output_dir: Optional custom directory to save Excel report.
        on_progress: Optional UI progress callback.
        on_message: Optional UI notification message callback.
        keep_browser_open: If True, leaves browser open after completion.

    Returns:
        Optional[Path]: Path to generated Excel report upon completion, or None if stopped early.
    """
    global _IS_PAUSED, _IS_STOPPED
    _IS_PAUSED = False
    _IS_STOPPED = False

    logger = get_logger("otc_runner")
    log_event(logger, 20, f"Starting batch processing for file: {input_file_path.name}")

    storage_cfg = config.get("storage", {})
    db_path = Path(storage_cfg.get("checkpoint_db_path", "checkpoints/processing_checkpoint.db"))
    init_checkpoint_db(db_path)

    batch_id = compute_batch_id(input_file_path)
    register_batch(db_path, batch_id, str(input_file_path))

    configured_banks = list(config.get("bank_mapping", {}).keys())
    input_records = process_input_file(input_file_path, configured_banks)
    log_event(logger, 20, f"Loaded {len(input_records)} input records from {input_file_path.name}.")

    processed_row_numbers = set(get_processed_row_numbers(db_path, batch_id))
    if processed_row_numbers:
        log_event(
            logger,
            20,
            f"Resuming existing batch {batch_id}. {len(processed_row_numbers)} rows already completed.",
        )

    browser_cfg = config.get("browser", {})
    portal_cfg = config.get("portal", {})
    selectors = config.get("selectors", {})
    bank_mapping = config.get("bank_mapping", {})
    rules_cfg = config.get("classification_rules", {})

    page = get_active_browser_page()
    if page is None or page.is_closed():
        _, _, page = launch_persistent_browser_session(browser_cfg)

    login_url = portal_cfg.get("login_url", "http://127.0.0.1:8080/login")
    check_bill_url = portal_cfg.get("check_bill_url")

    # If search form is not already present, ensure authenticated and navigate
    if not is_check_bill_screen_present(page):
        if is_portal_authenticated(page, selectors):
            navigate_to_check_bill_status(page, selectors, check_bill_url, on_message=on_message)

        if not is_check_bill_screen_present(page):
            auth_success = ensure_portal_authenticated(
                page=page,
                login_url=login_url,
                check_bill_url=check_bill_url,
                selectors=selectors,
                timeout_seconds=300,
                on_message_callback=on_message,
            )
            if not auth_success:
                log_event(logger, 40, "Authentication not satisfied. Aborting file processing.")
                if not keep_browser_open:
                    close_browser_session()
                return None

            navigate_to_check_bill_status(page, selectors, check_bill_url, on_message=on_message)

    total_records = len(input_records)
    for idx, record in enumerate(input_records):
        while _IS_PAUSED and not _IS_STOPPED:
            if on_message:
                on_message("Automation paused by user. Waiting to resume...")
            time.sleep(1.0)

        if _check_cancellation():
            log_event(logger, 30, "[OTC] Automation stopped by user. Checkpoint preserved.")
            if on_message:
                on_message("[OTC] Automation stopped by user.")
            break

        row_num = record["row_number"]
        consumer_num = record["consumer_number"]
        bank = record["bank_service"]
        search_date = record["date"]

        if row_num in processed_row_numbers:
            continue

        if on_progress:
            on_progress(
                {
                    "current_row": row_num,
                    "total_rows": total_records,
                    "processed_count": len(processed_row_numbers),
                    "consumer_number": consumer_num,
                    "bank": bank,
                    "filename": input_file_path.name,
                }
            )

        if not record["is_valid"]:
            err_msg = "; ".join(record["validation_errors"])
            log_event(
                logger,
                30,
                f"Row validation failed: {err_msg}",
                row_number=row_num,
                consumer_number=consumer_num,
            )
            record_row_result(
                db_path,
                batch_id,
                row_num,
                consumer_num,
                bank,
                search_date,
                "FAILED",
                0,
                0,
                err_msg,
            )
            processed_row_numbers.add(row_num)
        if _check_cancellation():
            log_event(logger, 30, "[OTC] Automation stopped by user. Checkpoint preserved.")
            if on_message:
                on_message("[OTC] Automation stopped by user.")
            break
            continue

        if check_is_session_expired(page, selectors):
            log_event(logger, 30, "Session expired mid-batch. Waiting for re-login...")
            if on_message:
                on_message("Session expired. Please re-authenticate in the browser.")
            reauth = ensure_portal_authenticated(
                page=page,
                login_url=login_url,
                check_bill_url=check_bill_url,
                selectors=selectors,
                timeout_seconds=300,
                on_message_callback=on_message,
            )
            if not reauth:
                log_event(logger, 40, "Re-authentication timed out. Stopping batch.")
                break
            navigate_to_check_bill_status(page, selectors, check_bill_url, on_message=on_message)

        search_success = False
        retry_limit = portal_cfg.get("retry_attempts", 3)
        timeout_ms = portal_cfg.get("search_timeout_ms", 15000)

        if on_message:
            on_message(
                f"[{idx + 1}/{total_records}] Searching Consumer {consumer_num} ({bank}) for {search_date}..."
            )

        for attempt in range(1, retry_limit + 1):
            try:
                search_success = execute_transaction_search(
                    page,
                    selectors,
                    bank,
                    consumer_num,
                    search_date,
                    bank_mapping,
                    timeout_ms=timeout_ms,
                )
                if search_success:
                    break
            except Exception as exc:
                log_event(
                    logger,
                    30,
                    f"Search attempt {attempt} error: {exc}",
                    row_number=row_num,
                    consumer_number=consumer_num,
                )
                time.sleep(portal_cfg.get("retry_delay_seconds", 1))

        if not search_success:
            record_row_result(
                db_path,
                batch_id,
                row_num,
                consumer_num,
                bank,
                search_date,
                "FAILED",
                0,
                0,
                "Search query timed out or failed to load results.",
            )
            processed_row_numbers.add(row_num)
            if _check_cancellation():
                log_event(logger, 30, "[OTC] Automation stopped by user. Checkpoint preserved.")
                if on_message:
                    on_message("[OTC] Automation stopped by user.")
                break
            continue

        extracted_txs = extract_all_transactions(page, selectors)
        if not extracted_txs:
            record_row_result(
                db_path,
                batch_id,
                row_num,
                consumer_num,
                bank,
                search_date,
                "NO_RECORD",
                0,
                0,
            )
            processed_row_numbers.add(row_num)
            if _check_cancellation():
                log_event(logger, 30, "[OTC] Automation stopped by user. Checkpoint preserved.")
                if on_message:
                    on_message("[OTC] Automation stopped by user.")
                break
            continue

        classified_items: List[Dict[str, Any]] = []
        qualifying_rejection_count = 0
        for tx in extracted_txs:
            cls_result = classify_transaction(
                tx.get("status", ""),
                tx.get("response_code", ""),
                rules_cfg,
            )
            tx["classification"] = cls_result["classification"]
            tx["is_qualifying_rejection"] = cls_result["is_qualifying_rejection"]
            tx["classification_reason"] = cls_result["reason"]
            if (
                cls_result["is_qualifying_rejection"]
                or "REJECT" in str(tx.get("status", "")).upper()
            ):
                qualifying_rejection_count += 1
            classified_items.append(tx)

        save_transactions(
            db_path,
            batch_id,
            row_num,
            consumer_num,
            bank,
            search_date,
            classified_items,
        )
        record_row_result(
            db_path,
            batch_id,
            row_num,
            consumer_num,
            bank,
            search_date,
            "SUCCESS",
            len(classified_items),
            qualifying_rejection_count,
        )
        processed_row_numbers.add(row_num)
        if _check_cancellation():
            log_event(logger, 30, "[OTC] Automation stopped by user. Checkpoint preserved.")
            if on_message:
                on_message("[OTC] Automation stopped by user.")
            break
        log_event(
            logger,
            20,
            f"Extracted {len(classified_items)} transactions ({qualifying_rejection_count} rejected).",
            row_number=row_num,
            consumer_number=consumer_num,
        )

    if not keep_browser_open:
        close_browser_session()

    target_out_dir = output_dir or Path(storage_cfg.get("output_dir", "output"))
    summary = get_batch_summary(db_path, batch_id)
    report_file = generate_otc_rejected_report(
        target_out_dir,
        summary["transactions"],
    )
    log_event(logger, 20, f"OTC Excel report generated successfully: {report_file}")
    if on_message:
        on_message(f"OTC Report ready: {report_file.name}")

    return report_file
