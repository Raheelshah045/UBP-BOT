"""File detection, stability validation, structure verification, and ingestion module.

Handles detecting newly placed spreadsheet files, verifying read locks and size
stability, computing file hashes for duplicate prevention, and moving files across lifecycle stages.
"""

import hashlib
import io
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

REQUIRED_COLUMNS = ["Consumer Number", "Date"]
GNB_REQUIRED_COLUMNS = ["Transaction ID"]
DEFAULT_OTC_BANK = "UBL"


def standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Map flexible header variants to standard canonical column names."""
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
    """Parse and normalize date input into standard YYYY-MM-DD format."""
    if pd.isna(raw_date):
        return None
    if isinstance(raw_date, (datetime, pd.Timestamp)):
        return raw_date.strftime("%Y-%m-%d")

    date_str = str(raw_date).strip()
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
    """Read an Excel or CSV file ensuring Consumer Numbers are kept as strings."""
    ext = file_path.suffix.lower()

    with file_path.open("rb") as f:
        file_bytes = io.BytesIO(f.read())

    if ext == ".csv":
        df = pd.read_csv(file_bytes, dtype=str, keep_default_na=False)
    elif ext in [".xlsx", ".xls"]:
        engine = "openpyxl" if ext == ".xlsx" else "xlrd"
        try:
            df = pd.read_excel(file_bytes, dtype=str, engine=engine, keep_default_na=False)
        except Exception:
            file_bytes.seek(0)
            df = pd.read_excel(file_bytes, dtype=str, keep_default_na=False)
    else:
        raise ValueError(f"Unsupported file format: {ext}")

    df = standardize_column_names(df)
    if "Consumer Number" in df.columns:
        df["Consumer Number"] = df["Consumer Number"].astype(str).str.strip()
    return df


def validate_input_dataframe(df: pd.DataFrame) -> None:
    """Validate that the input dataframe contains all required headers."""
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
    """Process an input Excel or CSV file into validated row records."""
    df = read_raw_dataframe(file_path)
    target_sys = identify_system_target(file_path)

    if target_sys == "gnb":
        if "Transaction ID" not in df.columns:
            raise ValueError("Input file missing required column for GNB: 'Transaction ID'")
        records: List[Dict[str, Any]] = []
        for idx, row in df.iterrows():
            tx_id = str(row.get("Transaction ID", "")).strip()
            if not tx_id or tx_id.lower() in ("nan", "none"):
                continue
            records.append({
                "row_number": idx + 2,
                "transaction_id": tx_id,
                "account_consumer": str(row.get("Account / Consumer", row.get("Consumer Number", ""))).strip(),
                "date": normalize_date_string(row.get("Date", "")),
            })
        return records

    validate_input_dataframe(df)
    clean_columns = {col: str(col).strip() for col in df.columns}
    df = df.rename(columns=clean_columns)

    records: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        spreadsheet_row_num = idx + 2
        raw_consumer = str(row.get("Consumer Number", "")).strip()
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


def is_temporary_file(file_path: Path) -> bool:
    """Check if the file is an OS or Office temporary/lock file."""
    name = file_path.name
    return name.startswith("~$") or name.startswith(".~") or name.endswith(".tmp")


def compute_file_sha256(file_path: Path) -> str:
    """Calculate the SHA-256 hash of a file for duplicate content detection."""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def is_file_locked_or_changing(
    file_path: Path, interval_seconds: float = 1.0, required_stable_checks: int = 3
) -> bool:
    """Verify whether a file is currently locked by another process or still being written."""
    if not file_path.exists():
        return True

    try:
        last_size = file_path.stat().st_size
    except (OSError, PermissionError):
        return True

    stable_count = 0
    for _ in range(required_stable_checks):
        time.sleep(interval_seconds)
        if not file_path.exists():
            return True
        try:
            current_size = file_path.stat().st_size
            if current_size == last_size and current_size > 0:
                stable_count += 1
            else:
                stable_count = 0
                last_size = current_size

            with file_path.open("rb"):
                pass
        except (OSError, PermissionError):
            return True

    return stable_count < required_stable_checks


def validate_file_structure(file_path: Path) -> Dict[str, Any]:
    """Confirm spreadsheet can be parsed and holds required column headers."""
    try:
        df: pd.DataFrame = read_raw_dataframe(file_path)
        col_names = [str(c).strip() for c in df.columns]
        target_sys = identify_system_target(file_path)
        required = GNB_REQUIRED_COLUMNS if target_sys == "gnb" else REQUIRED_COLUMNS
        missing = [col for col in required if col not in col_names]
        if missing:
            return {
                "is_valid": False,
                "error": f"Missing mandatory columns for {target_sys.upper()}: {', '.join(missing)}",
                "row_count": len(df),
            }
        if len(df) == 0:
            return {
                "is_valid": False,
                "error": "Input spreadsheet contains no transaction rows.",
                "row_count": 0,
            }
        return {"is_valid": True, "error": None, "row_count": len(df)}
    except Exception as exc:
        return {"is_valid": False, "error": str(exc), "row_count": 0}


def scan_directory_for_candidate_files(
    directory_path: Path, supported_extensions: Optional[List[str]] = None
) -> List[Path]:
    """Scan directory and return eligible, non-temporary spreadsheet paths."""
    if not directory_path.exists():
        return []

    exts = (
        [e.lower() for e in supported_extensions]
        if supported_extensions
        else [".xlsx", ".xls", ".csv"]
    )
    candidates: List[Path] = []
    for item in directory_path.iterdir():
        if item.is_file() and not is_temporary_file(item):
            if item.suffix.lower() in exts:
                candidates.append(item)

    candidates.sort(key=lambda p: p.stat().st_mtime)
    return candidates


def identify_system_target(file_path: Path) -> str:
    """Identify whether an input file belongs to OTC, GNB, or is UNKNOWN."""
    stem = file_path.stem.upper()
    if "OTC" in stem and "GNB" not in stem:
        return "otc"
    if "GNB" in stem and "OTC" not in stem:
        return "gnb"
    return "unknown"


def move_file_safely(source_file: Path, target_dir: Path, max_retries: int = 5) -> Path:
    """Move a file to target directory with collision avoidance and atomic lock handling."""
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / source_file.name

    if destination.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = target_dir / f"{source_file.stem}_{timestamp}{source_file.suffix}"

    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            shutil.move(str(source_file), str(destination))
            return destination
        except (PermissionError, OSError) as exc:
            last_error = exc
            time.sleep(0.3 * (attempt + 1))

    try:
        shutil.copy2(str(source_file), str(destination))
        source_file.unlink()
        return destination
    except Exception as exc:
        if destination.exists():
            try:
                destination.unlink()
            except Exception:
                pass
        raise PermissionError(
            f"File '{source_file.name}' is currently in use or open in Excel. "
            f"Please close it so the bot can move it. ({last_error or exc})"
        ) from (last_error or exc)
