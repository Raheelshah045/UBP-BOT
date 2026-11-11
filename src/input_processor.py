"""Input file processing module for the OTC Bot.

Handles parsing, validating, and structuring input Excel/CSV records with flexible header mapping.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

REQUIRED_COLUMNS = ["Consumer Number", "Bank / Service", "Date"]


def standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Map flexible header variants to standard canonical column names.

    Args:
        df: Raw pandas DataFrame with original spreadsheet column headers.

    Returns:
        pd.DataFrame: Renamed DataFrame with standardized canonical headers.
    """
    rename_map: Dict[Any, str] = {}
    for col in df.columns:
        c = str(col).strip().lower().replace("_", " ")
        if "consumer" in c:
            rename_map[col] = "Consumer Number"
        elif "bank" in c or "biller" in c or "service" in c:
            rename_map[col] = "Bank / Service"
        elif "date" in c:
            rename_map[col] = "Date"
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

    Args:
        file_path: Path to the target spreadsheet file.

    Returns:
        pd.DataFrame: Loaded tabular data with standardized columns.

    Raises:
        ValueError: If the file type is unsupported or reading fails.
    """
    ext = file_path.suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
    elif ext in [".xlsx", ".xls"]:
        df = pd.read_excel(file_path, dtype=str, keep_default_na=False)
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


def process_input_file(
    file_path: Path, valid_banks: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Process an input Excel or CSV file into validated row records.

    Preserves row order, duplicate entries, leading zeros, and original row numbers.

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
        raw_bank = str(row.get("Bank / Service", "")).strip()
        raw_date = row.get("Date")

        normalized_date = normalize_date_string(raw_date)
        is_valid = True
        error_reasons: List[str] = []

        if not raw_consumer:
            is_valid = False
            error_reasons.append("Consumer Number is empty")

        if not raw_bank:
            is_valid = False
            error_reasons.append("Bank / Service is empty")
        elif valid_banks and raw_bank.upper() not in [b.upper() for b in valid_banks]:
            error_reasons.append(f"Bank '{raw_bank}' not in configured portal banks list")

        if not normalized_date:
            is_valid = False
            error_reasons.append(f"Invalid date format: '{raw_date}'")

        records.append(
            {
                "row_number": spreadsheet_row_num,
                "consumer_number": raw_consumer,
                "bank_service": raw_bank,
                "date": normalized_date if normalized_date else str(raw_date),
                "is_valid": is_valid,
                "validation_errors": error_reasons,
            }
        )

    return records
