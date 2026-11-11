"""Unit tests for SQLite checkpoint and state persistence."""

from pathlib import Path

from src.checkpoint import (
    get_batch_summary,
    get_processed_row_numbers,
    init_checkpoint_db,
    record_row_result,
    register_batch,
    save_transactions,
)


def test_checkpoint_database_lifecycle_and_resume_capability(tmp_path: Path) -> None:
    """Verify batch registration, row completion tracking, and transaction linking."""
    db_file = tmp_path / "test_checkpoint.db"
    init_checkpoint_db(db_file)

    batch_id = "test_batch_001"
    register_batch(db_file, batch_id, "sample.csv")

    record_row_result(
        db_path=db_file,
        batch_id=batch_id,
        row_number=2,
        consumer_number="10012345678901",
        bank_service="HBL",
        date="2026-11-10",
        status="SUCCESS",
        transactions_count=1,
        rejected_count=1,
    )

    processed = get_processed_row_numbers(db_file, batch_id)
    assert processed == [2]

    tx_data = [
        {
            "transaction_date": "2026-11-10",
            "transaction_time": "14:22:10",
            "rrn": "RRN100102",
            "auth_id": "AUTH992",
            "amount": "12,500.00",
            "status": "Rejected",
            "response_code": "51",
            "response_desc": "Insufficient funds",
            "classification": "Rejected",
            "is_qualifying_rejection": True,
        }
    ]
    save_transactions(
        db_path=db_file,
        batch_id=batch_id,
        row_number=2,
        input_consumer="10012345678901",
        input_bank="HBL",
        input_date="2026-11-10",
        transactions=tx_data,
    )

    summary = get_batch_summary(db_file, batch_id)
    assert len(summary["rows"]) == 1
    assert len(summary["transactions"]) == 1
    assert summary["transactions"][0]["rrn"] == "RRN100102"
    assert summary["transactions"][0]["is_qualifying_rejection"] == 1
