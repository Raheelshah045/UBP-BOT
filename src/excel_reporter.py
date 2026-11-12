"""Excel report generation module for the OTC Bot.

Creates a single consolidated banking-grade report containing only Rejected Transaction Details.
"""

from pathlib import Path
from typing import Any, Dict, List

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
THIN_SIDE = Side(border_style="thin", color="D3D3D3")
CELL_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
REJECT_STATUS_FILL = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
REJECT_STATUS_FONT = Font(name="Calibri", size=10, bold=True, color="991B1B")

REPORT_FILENAME = "Rejected_Transaction_Details.xlsx"
SHEET_TITLE = "Rejected Transaction Details"

HEADERS = [
    "Sr. No.",
    "Input Row Number",
    "Consumer Number",
    "Bank / Service",
    "Transaction Date",
    "Transaction Time",
    "RRN",
    "Authorization ID",
    "Transaction Amount (PKR)",
    "Transaction Status",
    "Response Code",
    "Response Description",
    "Classification Reason",
]


def apply_header_styling(worksheet: Any, num_columns: int) -> None:
    """Apply styling, freeze panes, and filters to the header row.

    Args:
        worksheet: OpenPyXL worksheet object.
        num_columns: Number of populated columns.
    """
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = f"A1:{get_column_letter(num_columns)}1"

    for col_idx in range(1, num_columns + 1):
        cell = worksheet.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = CELL_BORDER

    worksheet.row_dimensions[1].height = 28


def autofit_columns(worksheet: Any) -> None:
    """Adjust column widths dynamically according to cell contents.

    Args:
        worksheet: OpenPyXL worksheet to size.
    """
    for col in worksheet.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        worksheet.column_dimensions[col_letter].width = max(max_len + 4, 12)


def is_rejected_transaction(transaction: Dict[str, Any]) -> bool:
    """Determine whether a transaction has been rejected as per its status.

    Args:
        transaction: Transaction dictionary from search extraction.

    Returns:
        bool: True if transaction status represents a rejection.
    """
    status_str = str(transaction.get("status", "")).strip().upper()
    return (
        "REJECT" in status_str
        or "DECLIN" in status_str
        or "FAIL" in status_str
        or "UNSUCCESS" in status_str
        or bool(transaction.get("is_qualifying_rejection"))
    )


def generate_excel_report(
    output_dir: Path,
    input_records: List[Dict[str, Any]],
    processed_rows: List[Dict[str, Any]],
    transactions: List[Dict[str, Any]],
) -> Path:
    """Compile and save a single consolidated Excel file for Rejected Transaction Details.

    Merges with any existing rejected report in the output folder to maintain exactly ONE
    master output file across all batches.

    Args:
        output_dir: Destination directory.
        input_records: Initial raw input records.
        processed_rows: Recorded row audit status objects.
        transactions: All extracted transaction items from the current batch.

    Returns:
        Path: Full path to the single output Excel workbook.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / REPORT_FILENAME

    # Read existing entries if the single output file already exists
    existing_keys = set()
    all_rows: List[List[Any]] = []

    if report_path.exists():
        try:
            prev_wb = openpyxl.load_workbook(report_path)
            prev_sheet = prev_wb.active
            for row in prev_sheet.iter_rows(min_row=2, values_only=True):
                if not row or not any(row):
                    continue
                # Extract key: (Consumer Number, RRN, Date, Time)
                c_num = str(row[2]).strip() if len(row) > 2 else ""
                r_date = str(row[4]).strip() if len(row) > 4 else ""
                r_time = str(row[5]).strip() if len(row) > 5 else ""
                r_rrn = str(row[6]).strip() if len(row) > 6 else ""
                key = (c_num, r_rrn, r_date, r_time)
                if key not in existing_keys:
                    existing_keys.add(key)
                    # Convert row to mutable list and strip previous Sr No
                    row_list = list(row)
                    all_rows.append(row_list[1:])  # Keep everything except Sr. No.
            prev_wb.close()
        except Exception:
            all_rows = []
            existing_keys = set()

    # Append new qualifying rejected transactions from current batch
    new_rejected = [t for t in transactions if is_rejected_transaction(t)]
    for item in new_rejected:
        c_num = str(item.get("consumer_number", "")).strip()
        bank_val = item.get("bank_service", "")
        tx_date = item.get("transaction_date", "") or item.get("date", "")
        tx_time = item.get("transaction_time", "")
        rrn_val = item.get("rrn", "")
        auth_val = item.get("auth_id", "")
        amount_val = item.get("amount", "")
        status_val = item.get("status", "REJECTED")
        resp_code_val = str(item.get("response_code", "")).strip()
        resp_desc_val = (
            item.get("response_description")
            or item.get("response_desc")
            or ""
        )
        cls_reason = (
            item.get("classification_reason")
            or item.get("classification")
            or f"Rejected Transaction (Code {resp_code_val})"
        )

        key = (c_num, str(rrn_val).strip(), str(tx_date).strip(), str(tx_time).strip())
        if key not in existing_keys:
            existing_keys.add(key)
            all_rows.append(
                [
                    item.get("row_number", ""),
                    c_num,
                    bank_val,
                    tx_date,
                    tx_time,
                    rrn_val,
                    auth_val,
                    amount_val,
                    status_val,
                    resp_code_val,
                    resp_desc_val,
                    cls_reason,
                ]
            )

    # Build single workbook with exactly one sheet
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = SHEET_TITLE

    # Add header
    sheet.append(HEADERS)

    # Append all rows with continuous Sr. No.
    for sr_no, row_data in enumerate(all_rows, start=1):
        sheet.append([sr_no] + row_data)

    apply_header_styling(sheet, len(HEADERS))

    # Apply data styling
    for row in sheet.iter_rows(min_row=2, max_col=len(HEADERS)):
        for col_idx, cell in enumerate(row, 1):
            cell.border = CELL_BORDER
            # Alignments: Amount right-aligned, descriptions left-aligned, others centered
            if col_idx == 9:
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in (12, 13):
                cell.alignment = Alignment(horizontal="left", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="center", vertical="center")

            # Highlight status column in red
            if col_idx == 10:
                cell.fill = REJECT_STATUS_FILL
                cell.font = REJECT_STATUS_FONT

    autofit_columns(sheet)
    workbook.save(report_path)
    return report_path
