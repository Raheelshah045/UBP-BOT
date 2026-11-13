"""Unit tests for Excel report generation containing only rejected transactions."""

from pathlib import Path

import openpyxl

from src.excel_reporter import generate_excel_report


def test_excel_report_lists_only_rejected_transactions_and_excludes_successful_and_pending(
    tmp_path: Path,
) -> None:
    """Verify workbook lists only transactions rejected as per their status."""
    output_dir = tmp_path / "reports"

    input_records = [
        {"row_number": 2, "consumer_number": "1001", "bank_service": "UBL", "date": "2026-11-10"},
        {"row_number": 3, "consumer_number": "1002", "bank_service": "UBL", "date": "2026-11-10"},
        {"row_number": 4, "consumer_number": "1003", "bank_service": "UBL", "date": "2026-11-10"},
    ]

    processed_rows = [
        {
            "row_number": 2,
            "consumer_number": "1001",
            "bank_service": "UBL",
            "date": "2026-11-10",
            "status": "SUCCESS",
        },
        {
            "row_number": 3,
            "consumer_number": "1002",
            "bank_service": "UBL",
            "date": "2026-11-10",
            "status": "SUCCESS",
        },
        {
            "row_number": 4,
            "consumer_number": "1003",
            "bank_service": "UBL",
            "date": "2026-11-10",
            "status": "SUCCESS",
        },
    ]

    transactions = [
        # Rejected Transaction 1 (Should be included)
        {
            "row_number": 2,
            "consumer_number": "1001",
            "bank_service": "UBL",
            "date": "2026-11-10",
            "transaction_date": "2026-11-10",
            "transaction_time": "14:22:10",
            "rrn": "RRN901",
            "auth_id": "AUTH901",
            "amount": "1,000.00",
            "status": "Rejected",
            "response_code": "51",
            "response_desc": "Insufficient funds",
            "is_qualifying_rejection": True,
        },
        # Successful Transaction (Must NOT be in report)
        {
            "row_number": 3,
            "consumer_number": "1002",
            "bank_service": "UBL",
            "date": "2026-11-10",
            "transaction_date": "2026-11-10",
            "transaction_time": "10:15:00",
            "rrn": "RRN902",
            "auth_id": "AUTH902",
            "amount": "2,500.00",
            "status": "Approved",
            "response_code": "00",
            "response_desc": "Approved successfully",
            "is_qualifying_rejection": False,
        },
        # Pending Transaction (Must NOT be in report)
        {
            "row_number": 4,
            "consumer_number": "1003",
            "bank_service": "UBL",
            "date": "2026-11-10",
            "transaction_date": "2026-11-10",
            "transaction_time": "11:05:40",
            "rrn": "RRN903",
            "auth_id": "AUTH903",
            "amount": "500.00",
            "status": "Pending",
            "response_code": "01",
            "response_desc": "Refer to issuer",
            "is_qualifying_rejection": False,
        },
    ]

    report_path = generate_excel_report(output_dir, input_records, processed_rows, transactions)
    assert report_path.exists()
    assert report_path.name == "OTC_Rejected_Transactions.xlsx"

    wb = openpyxl.load_workbook(report_path)
    assert "OTC Rejected Transactions" in wb.sheetnames
    assert len(wb.sheetnames) == 1  # Exactly one single sheet for rejected transaction details

    rej_sheet = wb["OTC Rejected Transactions"]
    assert rej_sheet.freeze_panes == "A2"
    # Row 1 is header, Row 2 is the ONLY rejected transaction
    assert rej_sheet.max_row == 2
    assert rej_sheet.cell(row=2, column=10).value == "Rejected"
    assert rej_sheet.cell(row=2, column=11).value == "51"
    assert rej_sheet.cell(row=2, column=12).value == "Insufficient funds"

    # Confirm neither the approved nor pending RRNs are present in the sheet
    all_values = [cell.value for row in rej_sheet.iter_rows() for cell in row]
    assert "RRN902" not in all_values  # Approved transaction excluded
    assert "RRN903" not in all_values  # Pending transaction excluded
