"""Unit tests for file stability, temporary file filtering, hashing, and moving."""

from pathlib import Path

from src.file_detector import (
    compute_file_sha256,
    is_file_locked_or_changing,
    is_temporary_file,
    move_file_safely,
    scan_directory_for_candidate_files,
    validate_file_structure,
)


def test_temporary_office_and_temp_files_are_ignored() -> None:
    """Verify that files starting with ~$ or ending in .tmp are recognized as temporary."""
    assert is_temporary_file(Path("~$sample_data.xlsx")) is True
    assert is_temporary_file(Path(".~lock.data.csv")) is True
    assert is_temporary_file(Path("data.tmp")) is True
    assert is_temporary_file(Path("valid_input.csv")) is False
    assert is_temporary_file(Path("sample_transactions.xlsx")) is False


def test_sha256_hash_computation_detects_identical_contents(tmp_path: Path) -> None:
    """Verify that files with identical contents yield the same SHA-256 hash."""
    file1 = tmp_path / "file1.csv"
    file2 = tmp_path / "file2.csv"
    content = "Consumer Number,Bank / Service,Date\n1001,HBL,2026-11-10\n"
    file1.write_text(content, encoding="utf-8")
    file2.write_text(content, encoding="utf-8")

    assert compute_file_sha256(file1) == compute_file_sha256(file2)


def test_file_stability_verification_recognizes_stable_file(tmp_path: Path) -> None:
    """Verify stable file completes checks without reporting locked or changing."""
    stable_file = tmp_path / "stable.csv"
    stable_file.write_text(
        "Consumer Number,Bank / Service,Date\n1001,HBL,2026-11-10\n", encoding="utf-8"
    )

    is_unstable = is_file_locked_or_changing(
        stable_file, interval_seconds=0.05, required_stable_checks=2
    )
    assert is_unstable is False


def test_structure_validation_detects_missing_headers_and_empty_files(tmp_path: Path) -> None:
    """Verify that missing mandatory headers are caught by structural validator."""
    bad_file = tmp_path / "bad_headers.csv"
    bad_file.write_text("Account,Bank,Date\n1001,HBL,2026-11-10\n", encoding="utf-8")
    result = validate_file_structure(bad_file)
    assert result["is_valid"] is False
    assert "Missing mandatory columns" in str(result["error"])

    valid_file = tmp_path / "good.csv"
    valid_file.write_text(
        "Consumer Number,Bank / Service,Date\n1001,HBL,2026-11-10\n", encoding="utf-8"
    )
    result_ok = validate_file_structure(valid_file)
    assert result_ok["is_valid"] is True
    assert result_ok["row_count"] == 1


def test_safe_file_movement_avoids_collisions_and_preserves_original_data(tmp_path: Path) -> None:
    """Verify moving files safely moves between folders and renames on collision."""
    source_dir = tmp_path / "input"
    target_dir = tmp_path / "processing"
    source_dir.mkdir()
    target_dir.mkdir()

    src_file = source_dir / "batch.csv"
    src_file.write_text("test_data", encoding="utf-8")

    # First move
    dest1 = move_file_safely(src_file, target_dir)
    assert dest1.exists()
    assert dest1.name == "batch.csv"
    assert not src_file.exists()

    # Create new file with same name and move again -> collision avoidance
    src_file2 = source_dir / "batch.csv"
    src_file2.write_text("test_data_2", encoding="utf-8")
    dest2 = move_file_safely(src_file2, target_dir)
    assert dest2.exists()
    assert dest2.name != "batch.csv"
    assert "batch_" in dest2.name


def test_scan_directory_discovers_all_valid_candidate_extensions(tmp_path: Path) -> None:
    """Verify directory scanner picks up .xlsx, .xls, and .csv files while ignoring temp files."""
    (tmp_path / "f1.csv").write_text("c1", encoding="utf-8")
    (tmp_path / "f2.xlsx").write_text("c2", encoding="utf-8")
    (tmp_path / "f3.xls").write_text("c3", encoding="utf-8")
    (tmp_path / "~$f1.csv").write_text("temp", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")

    candidates = scan_directory_for_candidate_files(tmp_path)
    candidate_names = [p.name for p in candidates]
    assert "f1.csv" in candidate_names
    assert "f2.xlsx" in candidate_names
    assert "f3.xls" in candidate_names
    assert "~$f1.csv" not in candidate_names
    assert "notes.txt" not in candidate_names


def test_validate_file_structure_accepts_new_otc_format_without_bank_column(tmp_path: Path) -> None:
    """Verify OTC files without an explicit Bank column validate successfully."""
    import openpyxl

    test_otc = tmp_path / "OTC_Daily_Report.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Date", "Description", "Consumer #"])
    ws.append(["2026-11-12", "Payment", "00123456789"])
    wb.save(test_otc)

    val = validate_file_structure(test_otc)
    assert val["is_valid"] is True
    assert val["error"] is None
    assert val["row_count"] == 1
