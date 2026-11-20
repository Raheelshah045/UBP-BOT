"""Regression test suite for Phase 1 Enterprise readiness."""

from pathlib import Path

from src.ubp_bot.core.file_detector import compute_file_sha256
from src.ubp_bot.core.pipeline import (
    init_checkpoint_db,
    is_file_already_completed,
    record_file_history,
)
from src.ubp_bot.portals.otc_client import classify_transaction
from src.ubp_bot.services.excel_reporter import sanitize_cell_value


def test_regression_codes_95_98_across_statuses():
    """Verify response codes 95 and 98 are NEVER classified as qualifying rejections."""
    statuses = ["REJECTED", "DECLINED", "FAILED", "UNSUCCESSFUL", "ERROR", "REJECT"]
    for st in statuses:
        for code in ["95", "98"]:
            res = classify_transaction(status=st, response_code=code)
            assert res["is_qualifying_rejection"] is False, f"Code {code} with status {st} must not qualify"
            assert res["classification"] == "Excluded Rejection"


def test_regression_formula_injection_defense():
    """Verify formula injection defenses against all dangerous characters."""
    dangerous = ["=SUM(A1:A10)", "+cmd.exe", "-10+20", "@evil_macro", "\t=A1", "\r=B2"]
    for item in dangerous:
        sanitized = sanitize_cell_value(item)
        assert sanitized.startswith("'"), f"Failed to sanitize formula injection: {item}"


def test_regression_file_hash_idempotency(tmp_path: Path):
    """Verify file duplicate prevention and idempotency."""
    db_path = tmp_path / "checkpoint.db"
    init_checkpoint_db(db_path)

    sample_file = tmp_path / "sample.xlsx"
    sample_file.write_text("Dummy content for SHA256", encoding="utf-8")

    f_hash = compute_file_sha256(sample_file)
    assert not is_file_already_completed(db_path, f_hash)

    record_file_history(db_path, f_hash, sample_file.name, str(sample_file), "COMPLETED", "out.xlsx")
    assert is_file_already_completed(db_path, f_hash)
