"""Integration tests for dual-system pipeline and cross-system data isolation."""

from pathlib import Path

import openpyxl

from src.ubp_bot.core.file_detector import identify_system_target
from src.ubp_bot.services.excel_reporter import (
    generate_gnb_rejected_report,
    generate_otc_rejected_report,
)


def test_file_system_routing():
    """Verify input file target system identification."""
    p_otc = Path("C:/data/input/OTC_Daily_Transactions.xlsx")
    p_gnb = Path("C:/data/input/GNB_Rejections_Batch1.xlsx")
    p_unknown = Path("C:/data/input/Random_Spreadsheet.xlsx")

    assert identify_system_target(p_otc) == "otc"
    assert identify_system_target(p_gnb) == "gnb"
    assert identify_system_target(p_unknown) == "unknown"


def test_dual_system_report_isolation(tmp_path: Path):
    """Verify that OTC and GNB generate independent, non-conflicting reports."""
    otc_records = [
        {
            "input_row_number": 2,
            "consumer_number": "10012345678901",
            "bank_service": "HBL",
            "transaction_date": "2026-11-10",
            "status": "REJECTED",
            "response_code": "51",
            "response_description": "Insufficient Funds",
            "classification": "Rejected",
            "is_qualifying_rejection": True,
        }
    ]

    gnb_records = [
        {
            "transaction_id": "GNB-98765",
            "account_consumer": "PK000123456789",
            "transaction_date": "2026-11-10",
            "status": "FAILED",
            "failure_reason": "Account Dormant",
        }
    ]

    otc_report = generate_otc_rejected_report(tmp_path, otc_records)
    gnb_report = generate_gnb_rejected_report(tmp_path, gnb_records)

    assert otc_report.exists()
    assert gnb_report.exists()
    assert otc_report.name == "OTC_Rejected_Transactions.xlsx"
    assert gnb_report.name == "GNB_Rejected_Transactions.xlsx"

    # Verify OTC contents do not contain GNB transaction IDs
    wb_otc = openpyxl.load_workbook(otc_report)
    sheet_otc = wb_otc["OTC Rejected Transactions"]
    assert sheet_otc.cell(row=2, column=3).value == "10012345678901"
    for row in sheet_otc.iter_rows(values_only=True):
        assert "GNB-98765" not in [str(c) for c in row if c]

    # Verify GNB contents do not contain OTC consumer numbers
    wb_gnb = openpyxl.load_workbook(gnb_report)
    sheet_gnb = wb_gnb["GNB Rejected Transactions"]
    assert sheet_gnb.cell(row=2, column=2).value == "GNB-98765"
    for row in sheet_gnb.iter_rows(values_only=True):
        assert "10012345678901" not in [str(c) for c in row if c]
