"""Pipeline execution and checkpointing coordinator for UBP Bot.

Coordinates input ingestion, browser automation, search execution,
transaction classification, SQLite checkpointing, and Excel report generation.
"""

import hashlib
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from src.ubp_bot.core.config import resolve_app_path
from src.ubp_bot.core.file_detector import process_input_file
from src.ubp_bot.security.log_sanitizer import get_logger, log_event

_IS_PAUSED: bool = False
_IS_STOPPED: bool = False


def _check_cancellation(custom_check: Optional[Callable[[], bool]] = None) -> bool:
    """Check if the batch run has been cancelled via explicit stop signal."""
    if _IS_STOPPED:
        return True
    if custom_check is not None:
        try:
            return bool(custom_check())
        except Exception:
            pass
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
    """Generate a consistent unique batch ID based on file path and modification timestamp."""
    hasher = hashlib.sha256()
    hasher.update(str(input_file_path.resolve()).encode("utf-8"))
    if input_file_path.exists():
        hasher.update(str(input_file_path.stat().st_mtime).encode("utf-8"))
    return f"batch_{hasher.hexdigest()[:12]}"


# =========================================================================
# Checkpoint Database Operations (SQLite WAL Mode)
# =========================================================================

def get_connection(db_path: Path) -> sqlite3.Connection:
    """Create or connect to the SQLite checkpoint database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    except Exception:
        pass
    return conn


def init_checkpoint_db(db_path: Path) -> None:
    """Initialize database tables for batch tracking, processed rows, and file history."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_history (
            file_hash TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            original_path TEXT NOT NULL,
            status TEXT NOT NULL,
            output_report TEXT,
            processed_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS batches (
            batch_id TEXT PRIMARY KEY,
            input_file TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_rows (
            batch_id TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            consumer_number TEXT NOT NULL,
            bank_service TEXT NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL,
            transactions_count INTEGER DEFAULT 0,
            rejected_count INTEGER DEFAULT 0,
            error_message TEXT,
            processed_at TEXT NOT NULL,
            PRIMARY KEY (batch_id, row_number)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            input_row_number INTEGER NOT NULL,
            consumer_number TEXT NOT NULL,
            bank_service TEXT NOT NULL,
            transaction_date TEXT,
            transaction_time TEXT,
            rrn TEXT,
            auth_id TEXT,
            amount TEXT,
            transaction_status TEXT,
            response_code TEXT,
            response_description TEXT,
            classification TEXT,
            is_qualifying_rejection INTEGER,
            classification_reason TEXT,
            raw_data TEXT
        )
    """)

    conn.commit()
    conn.close()


def register_batch(db_path: Path, batch_id: str, input_file: str) -> None:
    """Register a new batch entry if not already present."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO batches (batch_id, input_file, created_at, status) VALUES (?, ?, ?, ?)",
        (batch_id, input_file, datetime.now().isoformat(), "IN_PROGRESS"),
    )
    conn.commit()
    conn.close()


def update_batch_status(db_path: Path, batch_id: str, status: str) -> None:
    """Update status for a batch record."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE batches SET status = ? WHERE batch_id = ?", (status, batch_id))
    conn.commit()
    conn.close()


def get_processed_row_numbers(db_path: Path, batch_id: str) -> List[int]:
    """Retrieve list of row numbers already completed for this batch."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT row_number FROM processed_rows WHERE batch_id = ? AND status IN ('SUCCESS', 'NO_RECORDS', 'FAILED')",
        (batch_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [r["row_number"] for r in rows]


def record_row_result(
    db_path: Path,
    batch_id: str,
    row_number: int,
    consumer_number: str,
    bank_service: str,
    date: str,
    status: str,
    transactions_count: int = 0,
    rejected_count: int = 0,
    error_message: Optional[str] = None,
) -> None:
    """Record execution outcome for an individual input row."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO processed_rows (
            batch_id, row_number, consumer_number, bank_service, date,
            status, transactions_count, rejected_count, error_message, processed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            batch_id,
            row_number,
            consumer_number,
            bank_service,
            date,
            status,
            transactions_count,
            rejected_count,
            error_message,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def save_transactions(
    db_path: Path, batch_id: str, input_row_number: int, transactions: List[Dict[str, Any]]
) -> None:
    """Save extracted and classified transactions into the raw_transactions table."""
    if not transactions:
        return
    conn = get_connection(db_path)
    cursor = conn.cursor()

    for tx in transactions:
        cursor.execute(
            """
            INSERT INTO raw_transactions (
                batch_id, input_row_number, consumer_number, bank_service,
                transaction_date, transaction_time, rrn, auth_id, amount,
                transaction_status, response_code, response_description,
                classification, is_qualifying_rejection, classification_reason, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                batch_id,
                input_row_number,
                tx.get("consumer_number", ""),
                tx.get("bank_service", ""),
                tx.get("transaction_date", ""),
                tx.get("transaction_time", ""),
                tx.get("rrn", ""),
                tx.get("auth_id", ""),
                tx.get("amount", ""),
                tx.get("status", ""),
                tx.get("response_code", ""),
                tx.get("response_description", ""),
                tx.get("classification", ""),
                1 if tx.get("is_qualifying_rejection") else 0,
                tx.get("classification_reason", ""),
                json.dumps(tx),
            ),
        )
    conn.commit()
    conn.close()


def get_all_batch_transactions(db_path: Path, batch_id: str) -> List[Dict[str, Any]]:
    """Retrieve all stored transactions for a batch."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM raw_transactions WHERE batch_id = ? ORDER BY input_row_number ASC",
        (batch_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    tx_list: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["is_qualifying_rejection"] = bool(d["is_qualifying_rejection"])
        tx_list.append(d)
    return tx_list


def get_batch_summary(db_path: Path, batch_id: str) -> Dict[str, Any]:
    """Retrieve statistical processing summary for a batch."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT status, created_at FROM batches WHERE batch_id = ?", (batch_id,))
    batch_info = cursor.fetchone()

    cursor.execute(
        """
        SELECT
            COUNT(*) as total_processed,
            SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
            SUM(CASE WHEN status = 'NO_RECORDS' THEN 1 ELSE 0 END) as no_records_count,
            SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_count,
            SUM(transactions_count) as total_tx_extracted,
            SUM(rejected_count) as total_rejected_extracted
        FROM processed_rows WHERE batch_id = ?
    """,
        (batch_id,),
    )
    stats = cursor.fetchone()
    conn.close()

    return {
        "batch_id": batch_id,
        "batch_status": batch_info["status"] if batch_info else "UNKNOWN",
        "created_at": batch_info["created_at"] if batch_info else None,
        "total_processed_rows": stats["total_processed"] or 0,
        "success_rows": stats["success_count"] or 0,
        "no_records_rows": stats["no_records_count"] or 0,
        "failed_rows": stats["failed_count"] or 0,
        "total_transactions": stats["total_tx_extracted"] or 0,
        "total_rejected": stats["total_rejected_extracted"] or 0,
    }


def record_file_history(
    db_path: Path,
    file_hash: str,
    file_name: str,
    original_path: str,
    status: str,
    output_report: Optional[str] = None,
) -> None:
    """Record lifecycle result for an entire file identified by its SHA-256 hash."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO file_history (
            file_hash, file_name, original_path, status, output_report, processed_at
        ) VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            file_hash,
            file_name,
            original_path,
            status,
            output_report,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def is_file_already_processed(db_path: Path, file_hash: str) -> bool:
    """Check if a file with identical SHA-256 content hash has been processed."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status FROM file_history WHERE file_hash = ? AND status IN ('COMPLETED', 'FAILED')",
        (file_hash,),
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def is_file_already_completed(db_path: Path, file_hash: str) -> bool:
    """Check if a file with identical SHA-256 content has completed successfully."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status FROM file_history WHERE file_hash = ? AND status = 'COMPLETED'",
        (file_hash,),
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


# =========================================================================
# Batch Automation Runner
# =========================================================================

def run_batch_automation(
    config: Dict[str, Any],
    input_file_path: Path,
    output_dir: Optional[Path] = None,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_message: Optional[Callable[[str], None]] = None,
    keep_browser_open: bool = True,
    stop_check: Optional[Callable[[], bool]] = None,
) -> Optional[Path]:
    """Execute the end-to-end OTC transaction monitoring and extraction workflow."""
    global _IS_PAUSED, _IS_STOPPED
    _IS_PAUSED = False
    _IS_STOPPED = False

    logger = get_logger("otc_runner")
    log_event(logger, 20, f"Starting batch processing for file: {input_file_path.name}")

    storage_cfg = config.get("storage", {})
    db_path = resolve_app_path(
        storage_cfg.get("checkpoint_db_path", "checkpoints/processing_checkpoint.db")
    )
    init_checkpoint_db(db_path)

    batch_id = compute_batch_id(input_file_path)
    register_batch(db_path, batch_id, str(input_file_path))

    configured_banks = list(config.get("bank_mapping", {}).keys())
    input_records = process_input_file(input_file_path, configured_banks)
    log_event(logger, 20, f"Loaded {len(input_records)} input records from {input_file_path.name}.")

    processed_row_numbers: Set[int] = set(get_processed_row_numbers(db_path, batch_id))
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

    from src.ubp_bot.portals.otc_client import (
        check_is_session_expired,
        classify_transaction,
        ensure_portal_authenticated,
        execute_transaction_search,
        extract_all_transactions,
        is_check_bill_screen_present,
        is_portal_authenticated,
        navigate_to_check_bill_status,
    )
    from src.ubp_bot.services.browser_manager import (
        close_browser_session,
        get_active_browser_page,
        launch_persistent_browser_session,
    )
    from src.ubp_bot.services.excel_reporter import generate_otc_rejected_report

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

        if _check_cancellation(stop_check):
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
            if _check_cancellation(stop_check):
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
                log_event(logger, 40, "Re-authentication failed. Stopping batch execution.")
                break
            navigate_to_check_bill_status(page, selectors, check_bill_url, on_message=on_message)

        # Execute search for consumer
        search_success = execute_transaction_search(
            page=page,
            selectors=selectors,
            bank_name=bank,
            consumer_number=consumer_num,
            search_date=search_date,
            bank_mapping=bank_mapping,
            on_message=on_message,
        )

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
                "Portal search submission error",
            )
            processed_row_numbers.add(row_num)
            continue

        # Extract table rows
        max_pg = config.get("processing", {}).get("max_pagination_pages", 10)
        extracted_rows = extract_all_transactions(page, selectors, max_pages=max_pg)

        # Classify each transaction
        qualifying_rejected_count = 0
        for tx in extracted_rows:
            tx["input_row_number"] = row_num
            tx["consumer_number"] = consumer_num
            tx["bank_service"] = bank
            cls_result = classify_transaction(
                tx.get("status", ""), tx.get("response_code", ""), rules_cfg
            )
            tx["classification"] = cls_result["classification"]
            tx["is_qualifying_rejection"] = cls_result["is_qualifying_rejection"]
            tx["classification_reason"] = cls_result["reason"]
            if cls_result["is_qualifying_rejection"]:
                qualifying_rejected_count += 1

        save_transactions(db_path, batch_id, row_num, extracted_rows)

        row_status = "SUCCESS" if extracted_rows else "NO_RECORDS"
        record_row_result(
            db_path,
            batch_id,
            row_num,
            consumer_num,
            bank,
            search_date,
            row_status,
            len(extracted_rows),
            qualifying_rejected_count,
        )
        processed_row_numbers.add(row_num)

        if _check_cancellation(stop_check):
            log_event(logger, 30, "[OTC] Automation stopped by user. Checkpoint preserved.")
            if on_message:
                on_message("[OTC] Automation stopped by user.")
            break

    # Final reporting
    all_txs = get_all_batch_transactions(db_path, batch_id)
    target_output_dir = output_dir if output_dir else resolve_app_path(
        config.get("directories", {}).get("output_dir", "output")
    )

    report_path = generate_otc_rejected_report(
        output_dir=target_output_dir,
        all_transactions=all_txs,
    )

    is_complete = len(processed_row_numbers) == total_records
    final_status = "COMPLETED" if is_complete else "STOPPED"
    update_batch_status(db_path, batch_id, final_status)

    log_event(logger, 20, f"Batch {batch_id} finalized with status '{final_status}'. Report: {report_path}")

    if not keep_browser_open:
        close_browser_session()

    return report_path
