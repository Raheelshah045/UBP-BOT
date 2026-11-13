"""Tests for Phase 1 GNB System extraction and Excel report generation."""

from pathlib import Path
from typing import Any, Dict, List

import openpyxl

from src.excel_reporter import (
    GNB_HEADERS,
    generate_gnb_rejected_report,
    generate_otc_rejected_report,
    is_otc_qualifying_rejection,
)


def test_rule_95_and_98_exclusion_enforced() -> None:
    """Ensure transaction response codes 95 and 98 are NEVER extracted for OTC."""
    tx_95 = {"status": "Rejected", "response_code": "95", "consumer_number": "1001"}
    tx_98 = {"status": "Rejected", "response_code": "98", "consumer_number": "1002"}
    tx_51 = {"status": "Rejected", "response_code": "51", "consumer_number": "1003"}
    tx_05 = {"status": "Rejected", "response_code": "05", "consumer_number": "1004"}
    tx_00 = {"status": "Approved", "response_code": "00", "consumer_number": "1005"}

    assert not is_otc_qualifying_rejection(tx_95), "Code 95 must NEVER be extracted"
    assert not is_otc_qualifying_rejection(tx_98), "Code 98 must NEVER be extracted"
    assert is_otc_qualifying_rejection(tx_51), "Code 51 should be extracted"
    assert is_otc_qualifying_rejection(tx_05), "Code 05 should be extracted"
    assert not is_otc_qualifying_rejection(tx_00), "Code 00 (Approved) must not be extracted"


def test_otc_separate_report_generation(tmp_path: Path) -> None:
    """Verify OTC report generation excludes codes 95 and 98 and formats cleanly."""
    transactions: List[Dict[str, Any]] = [
        {
            "row_number": 2,
            "consumer_number": "10012345678901",
            "bank_service": "HBL",
            "transaction_date": "2026-11-10",
            "transaction_time": "14:22:10",
            "rrn": "RRN100102",
            "auth_id": "AUTH992",
            "amount": "12,500.00",
            "status": "Rejected",
            "response_code": "51",
            "response_description": "Insufficient funds",
        },
        {
            "row_number": 3,
            "consumer_number": "10012345678901",
            "bank_service": "HBL",
            "transaction_date": "2026-10-10",
            "transaction_time": "11:05:40",
            "rrn": "RRN100103",
            "auth_id": "AUTH993",
            "amount": "5,000.00",
            "status": "Rejected",
            "response_code": "95",
            "response_description": "Timeout / Cancellation",
        },
    ]

    report = generate_otc_rejected_report(tmp_path, transactions)
    assert report.name == "OTC_Rejected_Transactions.xlsx"
    assert report.exists()

    wb = openpyxl.load_workbook(report)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))
    wb.close()

    # Header + exactly 1 row (code 51), code 95 must NOT be present
    assert len(rows) == 2
    assert rows[1][2] == "10012345678901"
    assert rows[1][10] == "51"


def test_gnb_separate_report_generation(tmp_path: Path) -> None:
    """Verify GNB report generates GNB_Rejected_Transactions.xlsx with standard fields."""
    gnb_transactions = [
        {
            "transaction_id": "GNB-TX-9011",
            "account_consumer": "PK90GNB00012345678",
            "transaction_date": "2026-11-12",
            "transaction_time": "11:20:15",
            "amount": "45,000.00",
            "status": "Rejected",
            "failure_reason": "Account Frozen / Inactive",
        },
        {
            "transaction_id": "GNB-TX-9012",
            "account_consumer": "PK90GNB00098765432",
            "transaction_date": "2026-11-12",
            "transaction_time": "14:05:42",
            "amount": "18,250.00",
            "status": "Rejected",
            "failure_reason": "Invalid Routing Code",
        },
    ]

    report = generate_gnb_rejected_report(tmp_path, gnb_transactions)
    assert report.name == "GNB_Rejected_Transactions.xlsx"
    assert report.exists()

    wb = openpyxl.load_workbook(report)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))
    wb.close()

    assert len(rows) == 3
    assert rows[0] == tuple(GNB_HEADERS)
    assert rows[1][1] == "GNB-TX-9011"
    assert rows[2][1] == "GNB-TX-9012"
