"""Excel report generation module for Phase 1.

Generates two independent banking-grade Excel outputs:
1. OTC_Rejected_Transactions.xlsx (strict exclusion of codes 95 and 98)
2. GNB_Rejected_Transactions.xlsx
"""

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HEADER_FILL_OTC = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
HEADER_FILL_GNB = PatternFill(start_color="0F5132", end_color="0F5132", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
THIN_SIDE = Side(border_style="thin", color="D3D3D3")
CELL_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
REJECT_STATUS_FILL = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
REJECT_STATUS_FONT = Font(name="Calibri", size=10, bold=True, color="991B1B")

OTC_REPORT_FILENAME = "OTC_Rejected_Transactions.xlsx"
GNB_REPORT_FILENAME = "GNB_Rejected_Transactions.xlsx"

OTC_HEADERS = [
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

GNB_HEADERS = [
    "Sr. No.",
    "Transaction ID",
    "Account / Consumer",
    "Transaction Date",
    "Transaction Time",
    "Amount (PKR)",
    "Status",
    "Failure Reason",
]


def sanitize_cell_value(val: Any) -> Any:
    """Sanitize string values to prevent Excel formula injection (CSV/formula injection).

    Prepends a single quote to any string starting with '=', '+', '-', '@', tab, carriage return,
    or with leading whitespace preceding any of these characters.
    """
    if isinstance(val, str) and val:
        stripped = val.lstrip()
        if stripped and stripped[0] in ("=", "+", "-", "@", "\t", "\r"):
            return f"'{val}"
    return val


def save_workbook_safely(workbook: openpyxl.Workbook, target_path: Path) -> Path:
    """Safely save workbook with atomic replacement and backup of existing report."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        backup_path = target_path.with_name(f"{target_path.stem}_prev{target_path.suffix}")
        try:
            shutil.copy2(str(target_path), str(backup_path))
        except Exception:
            pass

    temp_path = target_path.with_name(f".tmp_{target_path.name}")
    try:
        workbook.save(temp_path)
        if target_path.exists():
            target_path.unlink()
        temp_path.rename(target_path)
    except Exception:
        workbook.save(target_path)
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
    return target_path


def apply_header_styling(worksheet: Any, num_columns: int, header_fill: PatternFill) -> None:
    """Apply professional header styling, freeze panes, and filters.

    Args:
        worksheet: Target worksheet.
        num_columns: Number of headers.
        header_fill: Color fill for header cells.
    """
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = f"A1:{get_column_letter(num_columns)}1"

    for col_idx in range(1, num_columns + 1):
        cell = worksheet.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = CELL_BORDER

    worksheet.row_dimensions[1].height = 28


def autofit_columns(worksheet: Any) -> None:
    """Dynamically adjust worksheet column widths based on contents."""
    for col in worksheet.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        worksheet.column_dimensions[col_letter].width = max(max_len + 4, 12)


def is_otc_qualifying_rejection(transaction: Dict[str, Any]) -> bool:
    """Check if OTC transaction is rejected and NOT excluded by Rule 95 or 98.

    Args:
        transaction: Transaction dictionary.

    Returns:
        bool: True if transaction is a qualifying rejection.
    """
    code = str(transaction.get("response_code", "")).strip()
    # Critical rule: Codes 95 and 98 must NEVER be extracted
    if code in ("95", "98"):
        return False

    status = str(transaction.get("status", "")).strip().upper()
    return (
        "REJECT" in status
        or "DECLIN" in status
        or "FAIL" in status
        or "UNSUCCESS" in status
        or bool(transaction.get("is_qualifying_rejection"))
    )


def generate_otc_rejected_report(
    output_dir: Path,
    transactions: List[Dict[str, Any]],
    filename: Optional[str] = None,
) -> Path:
    """Generate separate OTC_Rejected_Transactions.xlsx report.

    Args:
        output_dir: Destination folder.
        transactions: List of OTC extracted transactions.
        filename: Optional custom filename.

    Returns:
        Path: Path to saved OTC report.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / (filename or OTC_REPORT_FILENAME)

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "OTC Rejected Transactions"
    sheet.append(OTC_HEADERS)

    # Filter transactions: only qualifying rejected, strictly no 95/98
    qualifying = [t for t in transactions if is_otc_qualifying_rejection(t)]

    # Deduplicate by (Consumer Number, RRN, Date, Time)
    seen_keys = set()
    row_count = 0
    for t in qualifying:
        c_num = str(t.get("consumer_number", "")).strip()
        bank_val = t.get("bank_service", "")
        tx_date = t.get("transaction_date", "") or t.get("date", "")
        tx_time = t.get("transaction_time", "")
        rrn_val = str(t.get("rrn", "")).strip()
        auth_val = t.get("auth_id", "")
        amount_val = t.get("amount", "")
        status_val = t.get("status", "Rejected")
        resp_code_val = str(t.get("response_code", "")).strip()
        resp_desc_val = t.get("response_description") or t.get("response_desc") or ""
        cls_reason = t.get("classification_reason") or f"Rejected (Code {resp_code_val})"

        dedup_key = (c_num, rrn_val, str(tx_date).strip(), str(tx_time).strip())
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)
        row_count += 1

        sheet.append([
            sanitize_cell_value(val)
            for val in [
                row_count,
                t.get("row_number", ""),
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
        ])

    apply_header_styling(sheet, len(OTC_HEADERS), HEADER_FILL_OTC)

    # Format data cells
    for row in sheet.iter_rows(min_row=2, max_col=len(OTC_HEADERS)):
        for col_idx, cell in enumerate(row, 1):
            cell.border = CELL_BORDER
            if col_idx == 9:
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in (12, 13):
                cell.alignment = Alignment(horizontal="left", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="center", vertical="center")

            if col_idx == 10:
                cell.fill = REJECT_STATUS_FILL
                cell.font = REJECT_STATUS_FONT

    autofit_columns(sheet)
    return save_workbook_safely(workbook, report_path)


def generate_excel_report(
    output_dir: Path,
    *args: Any,
    **kwargs: Any,
) -> Path:
    """Backward compatibility wrapper for legacy callers."""
    # Find transactions list among args or kwargs
    transactions: List[Dict[str, Any]] = []
    if "transactions" in kwargs:
        transactions = kwargs["transactions"]
    elif len(args) == 1 and isinstance(args[0], list):
        transactions = args[0]
    elif len(args) >= 3 and isinstance(args[2], list):
        # Old signature: (output_dir, input_records, processed_rows, transactions)
        transactions = args[2]
    elif args and isinstance(args[-1], list):
        transactions = args[-1]

    filename = kwargs.get("filename")
    return generate_otc_rejected_report(output_dir, transactions, filename=filename)



def generate_gnb_rejected_report(
    output_dir: Path,
    transactions: List[Dict[str, Any]],
    filename: Optional[str] = None,
) -> Path:
    """Generate separate GNB_Rejected_Transactions.xlsx report.

    Args:
        output_dir: Destination folder.
        transactions: List of GNB rejected transaction dictionaries.
        filename: Optional custom filename.

    Returns:
        Path: Path to saved GNB report.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / (filename or GNB_REPORT_FILENAME)

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "GNB Rejected Transactions"
    sheet.append(GNB_HEADERS)

    seen_ids = set()
    row_count = 0
    for t in transactions:
        tx_id = str(t.get("transaction_id", "")).strip()
        account_val = str(t.get("account_consumer", "") or t.get("consumer_number", "")).strip()
        tx_date = t.get("transaction_date", "") or t.get("date", "")
        tx_time = t.get("transaction_time", "") or t.get("time", "")
        amount_val = t.get("amount", "")
        status_val = t.get("status", "Rejected")
        reason_val = t.get("failure_reason", "") or t.get("reason", "Rejected in GNB")

        dedup_key = (tx_id, account_val, str(tx_date).strip())
        if tx_id and dedup_key in seen_ids:
            continue
        if tx_id:
            seen_ids.add(dedup_key)
        row_count += 1

        sheet.append([
            sanitize_cell_value(val)
            for val in [
                row_count,
                tx_id,
                account_val,
                tx_date,
                tx_time,
                amount_val,
                status_val,
                reason_val,
            ]
        ])

    apply_header_styling(sheet, len(GNB_HEADERS), HEADER_FILL_GNB)

    for row in sheet.iter_rows(min_row=2, max_col=len(GNB_HEADERS)):
        for col_idx, cell in enumerate(row, 1):
            cell.border = CELL_BORDER
            if col_idx == 6:
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in (2, 3):
                cell.alignment = Alignment(horizontal="left", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="center", vertical="center")

            if col_idx == 7:
                cell.fill = REJECT_STATUS_FILL
                cell.font = REJECT_STATUS_FONT

    autofit_columns(sheet)
    return save_workbook_safely(workbook, report_path)

