"""Unit tests for spreadsheet input parsing and validation."""

from pathlib import Path

import pytest

from src.input_processor import normalize_date_string, process_input_file


def test_date_string_normalization_handles_various_valid_formats() -> None:
    """Verify that multiple standard date representations normalize to YYYY-MM-DD."""
    assert normalize_date_string("2026-11-10") == "2026-11-10"
    assert normalize_date_string("10/11/2026") == "2026-11-10"
    assert normalize_date_string("invalid-date-string") is None


def test_input_processing_preserves_leading_zeros_and_duplicate_rows(tmp_path: Path) -> None:
    """Verify leading zeroes in consumer numbers and duplicate rows remain intact."""
    csv_file = tmp_path / "test_input.csv"
    csv_content = (
        "Consumer Number,Bank / Service,Date\n"
        "0012345678901,HBL,2026-11-10\n"
        "0012345678901,HBL,2026-11-10\n"
        "20098765432109,MEEZAN,2026-11-05\n"
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    records = process_input_file(csv_file, valid_banks=["HBL", "MEEZAN"])
    assert len(records) == 3
    assert records[0]["consumer_number"] == "0012345678901"
    assert records[1]["consumer_number"] == "0012345678901"
    assert records[0]["row_number"] == 2
    assert records[1]["row_number"] == 3
    assert records[0]["is_valid"] is True
    assert records[1]["is_valid"] is True


def test_missing_required_headers_raises_value_error(tmp_path: Path) -> None:
    """Verify that missing mandatory headers triggers an immediate ValueError."""
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("Account,Bank,Date\n123,HBL,2026-11-10\n", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        process_input_file(bad_csv)
    assert "missing mandatory columns" in str(excinfo.value)


def test_excel_xlsx_input_processing_preserves_strings_and_leading_zeros(tmp_path: Path) -> None:
    """Verify that native Excel .xlsx files preserve string types and leading zeros."""
    import openpyxl

    xlsx_path = tmp_path / "test_data.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Consumer Number", "Bank / Service", "Date"])
    ws.append(["00098765432109", "MEEZAN", "2026-11-05"])
    wb.save(xlsx_path)

    records = process_input_file(xlsx_path, valid_banks=["MEEZAN"])
    assert len(records) == 1
    assert records[0]["consumer_number"] == "00098765432109"
    assert records[0]["bank_service"] == "MEEZAN"
    assert records[0]["date"] == "2026-11-05"
    assert records[0]["is_valid"] is True


def test_new_otc_format_parses_column_a_and_m_and_defaults_to_ubl() -> None:
    """Verify operational 19-column OTC format defaults to UBL and skips blank rows."""
    sample_file = Path("input/FORMAT FOR OTC.xlsx")
    if not sample_file.is_file():
        pytest.skip("FORMAT FOR OTC.xlsx not present in input folder")

    records = process_input_file(sample_file, valid_banks=["UBL", "HBL"])
    assert len(records) == 3
    assert records[0]["consumer_number"] == "000404650005056022"
    assert records[0]["bank_service"] == "UBL"
    assert records[0]["date"] == "2026-11-12"
    assert records[0]["row_number"] == 2
    assert records[0]["is_valid"] is True

    assert records[1]["consumer_number"] == "0106127661"
    assert records[1]["bank_service"] == "UBL"
    assert records[1]["date"] == "2026-11-12"
    assert records[1]["row_number"] == 3

    assert records[2]["consumer_number"] == "0106127708"
    assert records[2]["bank_service"] == "UBL"
    assert records[2]["date"] == "2026-11-12"
    assert records[2]["row_number"] == 4


def test_synthetic_19_column_otc_format_maps_headers_and_defaults_to_ubl(tmp_path: Path) -> None:
    """Verify dynamic 19-column spreadsheet without bank defaults to UBL."""
    import openpyxl

    xlsx_path = tmp_path / "OTC_Format_Test.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    headers = [
        "Date", "Description", "Stan", "UNIQUE_ID", "ORIG_BRANCH", "ACCOUNT #",
        "Nature", "Amount", "Aging", "Remarks", "Remarks 2", "TRIM",
        "Consumer #", "Key 1", "MATCH", " AMOUNT2", "Narration Trim", "MID", "RIGHT 13",
    ]
    ws.append(headers)
    ws.append(["2026-11-15 00:00:00"] + ["dummy"] * 11 + ["000123456789"] + ["x"] * 6)
    ws.append(["2026-11-15 00:00:00"] + [""] * 18)  # Empty consumer row
    wb.save(xlsx_path)

    records = process_input_file(xlsx_path)
    assert len(records) == 1
    assert records[0]["consumer_number"] == "000123456789"
    assert records[0]["bank_service"] == "UBL"
    assert records[0]["date"] == "2026-11-15"
    assert records[0]["is_valid"] is True
