"""Unit tests for Excel reporting, formula injection sanitization, and atomic writes."""

from pathlib import Path

import openpyxl

from src.ubp_bot.services.excel_reporter import (
    generate_gnb_rejected_report,
    generate_otc_rejected_report,
    sanitize_cell_value,
    save_workbook_safely,
)


def test_sanitize_cell_value_formula_injection():
    """Verify prepending quote to formula injection triggers."""
    assert sanitize_cell_value("=1+1") == "'=1+1"
    assert sanitize_cell_value("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert sanitize_cell_value("-5*5") == "'-5*5"
    assert sanitize_cell_value("@SUM(A1:A10)") == "'@SUM(A1:A10)"
    assert sanitize_cell_value("\t=1+1") == "'\t=1+1"
    assert sanitize_cell_value("  =dangerous") == "'  =dangerous"
    # Normal safe values
    assert sanitize_cell_value("UBL") == "UBL"
    assert sanitize_cell_value("10012345678901") == "10012345678901"
    assert sanitize_cell_value(12345) == 12345


def test_generate_otc_rejected_report(tmp_path: Path):
    """Verify OTC rejected report structure and content."""
    txs = [
        {
            "input_row_number": 2,
            "consumer_number": "10012345678901",
            "bank_service": "HBL",
            "transaction_date": "2026-11-10",
            "transaction_time": "14:30:00",
            "rrn": "RRN123456",
            "auth_id": "AUTH999",
            "amount": "1500.00",
            "status": "REJECTED",
            "response_code": "51",
            "response_description": "Insufficient Funds",
            "classification": "Rejected",
            "is_qualifying_rejection": True,
            "classification_reason": "Qualifying rejection with code 51",
        },
        {
            "input_row_number": 3,
            "consumer_number": "20012345678901",
            "bank_service": "UBL",
            "transaction_date": "2026-11-10",
            "status": "REJECTED",
            "response_code": "95",
            "classification": "Excluded Rejection",
            "is_qualifying_rejection": False,
        },
    ]

    out_file = generate_otc_rejected_report(tmp_path, txs)
    assert out_file.exists()
    assert out_file.name == "OTC_Rejected_Transactions.xlsx"

    wb = openpyxl.load_workbook(out_file)
    assert "OTC Rejected Transactions" in wb.sheetnames
    sheet = wb["OTC Rejected Transactions"]

    # Header row (row 1) + exactly 1 qualifying rejection row (row 2)
    assert sheet.max_row == 2
    assert sheet.cell(row=2, column=3).value == "10012345678901"
    assert sheet.cell(row=2, column=11).value == "51"


def test_generate_gnb_rejected_report(tmp_path: Path):
    """Verify GNB rejected report structure and content."""
    txs = [
        {
            "transaction_id": "GNB-TX-9988",
            "account_consumer": "PK36UNIL000000123456",
            "transaction_date": "2026-11-10",
            "transaction_time": "10:15:00",
            "amount": "25000.00",
            "status": "FAILED",
            "failure_reason": "Account Frozen",
        }
    ]

    out_file = generate_gnb_rejected_report(tmp_path, txs)
    assert out_file.exists()
    assert out_file.name == "GNB_Rejected_Transactions.xlsx"

    wb = openpyxl.load_workbook(out_file)
    assert "GNB Rejected Transactions" in wb.sheetnames
    sheet = wb["GNB Rejected Transactions"]
    assert sheet.max_row == 2
    assert sheet.cell(row=2, column=2).value == "GNB-TX-9988"


def test_save_workbook_safely_creates_backup(tmp_path: Path):
    """Verify atomic saving with previous file backup creation."""
    target = tmp_path / "report.xlsx"
    wb1 = openpyxl.Workbook()
    wb1.active.title = "FirstVersion"
    save_workbook_safely(wb1, target)
    assert target.exists()

    wb2 = openpyxl.Workbook()
    wb2.active.title = "SecondVersion"
    save_workbook_safely(wb2, target)

    backup = tmp_path / "report_prev.xlsx"
    assert backup.exists()

    loaded_target = openpyxl.load_workbook(target)
    assert "SecondVersion" in loaded_target.sheetnames

    loaded_backup = openpyxl.load_workbook(backup)
    assert "FirstVersion" in loaded_backup.sheetnames
