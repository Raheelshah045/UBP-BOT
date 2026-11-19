"""Checkpoint and persistence management using SQLite.

Ensures reliable batch resume, tracking row completion, saving extracted transactions,
and maintaining file-level deduplication history.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Create or connect to the SQLite checkpoint database.

    Args:
        db_path: Destination path for the SQLite database file.

    Returns:
        sqlite3.Connection: Connected database object with row factory enabled.
    """
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
    """Initialize database tables for batch tracking, processed rows, and file history.

    Args:
        db_path: File path of the SQLite database.
    """
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
            transactions_count INTEGER NOT NULL DEFAULT 0,
            rejected_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            processed_at TEXT NOT NULL,
            PRIMARY KEY (batch_id, row_number)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS extracted_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            consumer_number TEXT NOT NULL,
            bank_service TEXT NOT NULL,
            date TEXT NOT NULL,
            transaction_date TEXT,
            transaction_time TEXT,
            rrn TEXT,
            auth_id TEXT,
            amount TEXT,
            status TEXT,
            response_code TEXT,
            response_desc TEXT,
            classification TEXT NOT NULL,
            is_qualifying_rejection INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def is_file_already_completed(db_path: Path, file_hash: str) -> bool:
    """Check whether a file hash has already been successfully processed.

    Args:
        db_path: Database path.
        file_hash: SHA-256 file hash.

    Returns:
        bool: True if previously recorded as COMPLETED.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status FROM file_history WHERE file_hash = ? AND status = 'COMPLETED'", (file_hash,)
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def is_file_already_processed(db_path: Path, file_hash: str) -> bool:
    """Check whether a file hash has already reached a terminal state (COMPLETED or FAILED).

    Args:
        db_path: Database path.
        file_hash: SHA-256 file hash.

    Returns:
        bool: True if previously recorded as COMPLETED or FAILED.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status FROM file_history WHERE file_hash = ? AND status IN ('COMPLETED', 'FAILED')",
        (file_hash,),
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def record_file_history(
    db_path: Path,
    file_hash: str,
    file_name: str,
    original_path: str,
    status: str,
    output_report: Optional[str] = None,
) -> None:
    """Record or update processing history for a specific input file.

    Args:
        db_path: Database path.
        file_hash: SHA-256 hash.
        file_name: Base filename.
        original_path: Original location.
        status: Status code (e.g. COMPLETED, FAILED, IN_PROGRESS).
        output_report: Generated report filename or path if any.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO file_history
        (file_hash, file_name, original_path, status, output_report, processed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            file_hash,
            file_name,
            original_path,
            status,
            output_report or "",
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def clear_file_history_for_reprocess(db_path: Path, file_hash: str) -> None:
    """Remove file history entry to allow explicit reprocessing.

    Args:
        db_path: Database path.
        file_hash: SHA-256 hash to delete.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM file_history WHERE file_hash = ?", (file_hash,))
    conn.commit()
    conn.close()


def register_batch(db_path: Path, batch_id: str, input_file: str) -> None:
    """Register a new or resuming processing batch.

    Args:
        db_path: Path to database.
        batch_id: Unique batch identifier.
        input_file: Original input spreadsheet path.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO batches (batch_id, input_file, created_at, status)
        VALUES (?, ?, ?, 'IN_PROGRESS')
        """,
        (batch_id, input_file, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_processed_row_numbers(db_path: Path, batch_id: str) -> List[int]:
    """Retrieve all successfully processed row numbers for a given batch.

    Args:
        db_path: Path to database.
        batch_id: Batch identifier.

    Returns:
        List[int]: List of already processed input row numbers.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT row_number FROM processed_rows
        WHERE batch_id = ? AND status IN ('SUCCESS', 'NO_RECORD')
        """,
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
    transactions_count: int,
    rejected_count: int,
    error_message: Optional[str] = None,
) -> None:
    """Record completion status of an individual input row.

    Args:
        db_path: Path to database.
        batch_id: Batch identifier.
        row_number: 1-based spreadsheet row number.
        consumer_number: Consumer number.
        bank_service: Bank name.
        date: Search date string.
        status: Processing outcome (e.g. SUCCESS, FAILED, NO_RECORD).
        transactions_count: Total transactions returned.
        rejected_count: Qualifying rejected transactions count.
        error_message: Optional error description if failed.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO processed_rows
        (batch_id, row_number, consumer_number, bank_service, date, status,
         transactions_count, rejected_count, error_message, processed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    db_path: Path,
    batch_id: str,
    row_number: int,
    input_consumer: str,
    input_bank: str,
    input_date: str,
    transactions: List[Dict[str, Any]],
) -> None:
    """Save extracted transactions linked to their originating input row.

    Args:
        db_path: Path to database.
        batch_id: Batch identifier.
        row_number: Originating spreadsheet row index.
        input_consumer: Consumer number from input file.
        input_bank: Bank/Service from input file.
        input_date: Date from input file.
        transactions: List of parsed transaction dictionaries.
    """
    if not transactions:
        return

    conn = get_connection(db_path)
    cursor = conn.cursor()

    for item in transactions:
        cursor.execute(
            """
            INSERT INTO extracted_transactions (
                batch_id, row_number, consumer_number, bank_service, date,
                transaction_date, transaction_time, rrn, auth_id, amount,
                status, response_code, response_desc, classification,
                is_qualifying_rejection, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                row_number,
                input_consumer,
                input_bank,
                input_date,
                item.get("transaction_date", ""),
                item.get("transaction_time", ""),
                item.get("rrn", ""),
                item.get("auth_id", ""),
                item.get("amount", ""),
                item.get("status", ""),
                item.get("response_code", ""),
                item.get("response_desc") or item.get("response_description", ""),
                item.get("classification", ""),
                1 if item.get("is_qualifying_rejection") else 0,
                json.dumps(item),
            ),
        )

    conn.commit()
    conn.close()


def get_batch_summary(db_path: Path, batch_id: str) -> Dict[str, Any]:
    """Retrieve full batch extraction results for Excel generation.

    Args:
        db_path: Path to database.
        batch_id: Batch identifier.

    Returns:
        Dict[str, Any]: Complete set of processed rows and transaction records.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM processed_rows WHERE batch_id = ? ORDER BY row_number", (batch_id,)
    )
    rows = [dict(r) for r in cursor.fetchall()]

    cursor.execute(
        "SELECT * FROM extracted_transactions WHERE batch_id = ? ORDER BY row_number, id",
        (batch_id,),
    )
    transactions = [dict(t) for t in cursor.fetchall()]

    conn.close()
    return {"rows": rows, "transactions": transactions}
