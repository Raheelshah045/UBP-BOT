"""Input file processing module for the OTC Bot.

Handles parsing, validating, and structuring input Excel/CSV records with flexible header mapping.
"""

import io
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

REQUIRED_COLUMNS = ["Consumer Number", "Date"]
GNB_REQUIRED_COLUMNS = ["Transaction ID"]
DEFAULT_OTC_BANK = "UBL"


def standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Map flexible header variants to standard canonical column names.

    Args:
        df: Raw pandas DataFrame with original spreadsheet column headers.

    Returns:
        pd.DataFrame: Renamed DataFrame with standardized canonical headers.
    """
    rename_map: Dict[Any, str] = {}
    for idx, col in enumerate(df.columns):
        c = str(col).strip().lower().replace("_", " ")
        if "consumer" in c:
            rename_map[col] = "Consumer Number"
        elif "bank" in c or "biller" in c or "service" in c:
            rename_map[col] = "Bank / Service"
        elif "transaction id" in c or "tx id" in c or "txid" in c:
            rename_map[col] = "Transaction ID"
        elif c == "date" or (idx == 0 and "date" in c):
            rename_map[col] = "Date"
        elif "timestamp" in c or "time" in c:
            rename_map[col] = "Timestamp"

    # Positional fallback for Column A (Date) and Column M (Consumer # at index 12)
    mapped_names = list(rename_map.values())
    if "Date" not in mapped_names and len(df.columns) > 0:
        first_col = df.columns[0]
        if "date" in str(first_col).strip().lower():
            rename_map[first_col] = "Date"

    if "Consumer Number" not in mapped_names and len(df.columns) >= 13:
        col_m = df.columns[12]
        if "consumer" in str(col_m).strip().lower() or "#" in str(col_m):
            rename_map[col_m] = "Consumer Number"

    return df.rename(columns=rename_map)


def normalize_date_string(raw_date: Any) -> Optional[str]:
    """Parse and normalize date input into standard YYYY-MM-DD format.

    Args:
        raw_date: Date object, string, or timestamp from spreadsheet.

    Returns:
        Optional[str]: Normalized date string, or None if invalid.
    """
    if pd.isna(raw_date):
        return None
    if isinstance(raw_date, (datetime, pd.Timestamp)):
        return raw_date.strftime("%Y-%m-%d")

    date_str = str(raw_date).strip()
    # Strip time component if present (e.g. '2026-11-09 00:00:00')
    if " " in date_str:
        date_str = date_str.split(" ")[0].strip()

    candidate_formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"]
    for fmt in candidate_formats:
        try:
            parsed = datetime.strptime(date_str, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def read_raw_dataframe(file_path: Path) -> pd.DataFrame:
    """Read an Excel or CSV file ensuring Consumer Numbers are kept as strings.

    Reads the entire file into an in-memory buffer first to avoid leaving open OS file handles
    on disk that could cause Windows PermissionError during file moves.

    Args:
        file_path: Path to the target spreadsheet file.

    Returns:
        pd.DataFrame: Loaded tabular data with standardized columns.

    Raises:
        ValueError: If the file type is unsupported or reading fails.
    """
    ext = file_path.suffix.lower()
    with file_path.open("rb") as f:
        file_buffer = io.BytesIO(f.read())

    if ext == ".csv":
        df = pd.read_csv(file_buffer, dtype=str, keep_default_na=False)
    elif ext in [".xlsx", ".xls"]:
        df = pd.read_excel(file_buffer, dtype=str, keep_default_na=False)
    else:
        raise ValueError(f"Unsupported file format: {ext}. Only .csv, .xlsx, and .xls supported.")

    df = standardize_column_names(df)
    if "Consumer Number" in df.columns:
        df["Consumer Number"] = df["Consumer Number"].astype(str).str.strip()
    return df


def validate_input_dataframe(df: pd.DataFrame) -> None:
    """Validate that the input dataframe contains all required headers.

    Args:
        df: Loaded dataframe to check.

    Raises:
        ValueError: If any mandatory column is missing.
    """
    column_names = [str(c).strip() for c in df.columns]
    missing = [req for req in REQUIRED_COLUMNS if req not in column_names]
    if missing:
        raise ValueError(f"Input file is missing mandatory columns: {', '.join(missing)}")


def _build_row_record(
    row_num: int,
    raw_consumer: str,
    raw_bank: str,
    raw_date: Any,
    valid_banks: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Validate fields and construct a single transaction record dictionary."""
    normalized_date = normalize_date_string(raw_date)
    effective_bank = (
        raw_bank
        if raw_bank and raw_bank.lower() not in ("nan", "none")
        else DEFAULT_OTC_BANK
    )
    is_valid = True
    error_reasons: List[str] = []

    if valid_banks and effective_bank != DEFAULT_OTC_BANK:
        if effective_bank.upper() not in [b.upper() for b in valid_banks]:
            is_valid = False
            error_reasons.append(f"Bank '{effective_bank}' not in configured portal banks list")

    if not normalized_date:
        is_valid = False
        error_reasons.append(f"Invalid date format: '{raw_date}'")

    return {
        "row_number": row_num,
        "consumer_number": raw_consumer,
        "bank_service": effective_bank,
        "date": normalized_date if normalized_date else str(raw_date),
        "is_valid": is_valid,
        "validation_errors": error_reasons,
    }


def process_input_file(
    file_path: Path, valid_banks: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Process an input Excel or CSV file into validated row records.

    Preserves row order, duplicate entries, leading zeros, and original row numbers.
    Defaults bank to UBL when the Bank / Service column is omitted or empty.
    Gracefully skips trailing or blank consumer rows.

    Args:
        file_path: Path to the input file.
        valid_banks: Optional list of acceptable bank/service names.

    Returns:
        List[Dict[str, Any]]: List of dictionary records ready for search processing.
    """
    df = read_raw_dataframe(file_path)
    validate_input_dataframe(df)

    clean_columns = {col: str(col).strip() for col in df.columns}
    df = df.rename(columns=clean_columns)

    records: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        spreadsheet_row_num = idx + 2
        raw_consumer = str(row.get("Consumer Number", "")).strip()

        # Skip empty/blank consumer rows (e.g. trailing empty rows in spreadsheet)
        if not raw_consumer or raw_consumer.lower() in ("nan", "none"):
            continue

        raw_bank = str(row.get("Bank / Service", "")).strip()
        raw_date = row.get("Date")

        records.append(
            _build_row_record(
                row_num=spreadsheet_row_num,
                raw_consumer=raw_consumer,
                raw_bank=raw_bank,
                raw_date=raw_date,
                valid_banks=valid_banks,
            )
        )

    return records
