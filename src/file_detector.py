"""File detection, stability validation, and archival movement module.

Handles detecting newly placed spreadsheet files, verifying read locks and size
stability, computing file hashes for duplicate prevention, and moving files across lifecycle stages.
"""

import hashlib
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.input_processor import REQUIRED_COLUMNS, read_raw_dataframe


def is_temporary_file(file_path: Path) -> bool:
    """Check if the file is an OS or Office temporary/lock file.

    Args:
        file_path: File to inspect.

    Returns:
        bool: True if file is temporary (e.g. starts with ~$ or .tmp).
    """
    name = file_path.name
    return name.startswith("~$") or name.startswith(".~") or name.endswith(".tmp")


def compute_file_sha256(file_path: Path) -> str:
    """Calculate the SHA-256 hash of a file for duplicate content detection.

    Args:
        file_path: Target file path.

    Returns:
        str: Hexadecimal SHA-256 digest string.
    """
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def is_file_locked_or_changing(
    file_path: Path, interval_seconds: float = 1.0, required_stable_checks: int = 3
) -> bool:
    """Verify whether a file is currently locked by another process or still being written.

    Args:
        file_path: Path to the target file.
        interval_seconds: Duration between size checks.
        required_stable_checks: Number of consecutive identical size observations required.

    Returns:
        bool: False if the file is completely stable and unlocked; True if unstable/locked.
    """
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

            # Attempt exclusive test open to verify write lock release
            with file_path.open("rb"):
                pass
        except (OSError, PermissionError):
            return True

    return stable_count < required_stable_checks


def validate_file_structure(file_path: Path) -> Dict[str, Any]:
    """Confirm spreadsheet can be parsed and holds required column headers.

    Args:
        file_path: Target spreadsheet path.

    Returns:
        Dict[str, Any]: Validation summary with is_valid flag, row_count, and error message.
    """
    try:
        df: pd.DataFrame = read_raw_dataframe(file_path)
        col_names = [str(c).strip() for c in df.columns]
        missing = [col for col in REQUIRED_COLUMNS if col not in col_names]
        if missing:
            return {
                "is_valid": False,
                "error": f"Missing mandatory columns: {', '.join(missing)}",
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
    """Scan directory and return eligible, non-temporary spreadsheet paths.

    Args:
        directory_path: Directory to inspect.
        supported_extensions: List of allowed file extensions. Defaults to [.xlsx, .xls, .csv].

    Returns:
        List[Path]: Found candidate files sorted by creation/modification timestamp.
    """
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


def move_file_safely(source_file: Path, target_dir: Path, max_retries: int = 5) -> Path:
    """Move a file to target directory with collision avoidance and atomic lock handling.

    Retries transient OS file locks (e.g. anti-virus scans or recently closed file handles)
    and guarantees the file is completely removed from the source directory.

    Args:
        source_file: Existing file to move.
        target_dir: Destination folder.
        max_retries: Number of retry attempts on transient file lock.

    Returns:
        Path: Final destination path of moved file.

    Raises:
        PermissionError: If file remains locked by an external application (like Excel) after retries.
    """
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

    # If direct shutil.move failed after retries, try copy + unlink
    try:
        shutil.copy2(str(source_file), str(destination))
        source_file.unlink()
        return destination
    except Exception as exc:
        # If unlink failed, remove destination so we do not leave orphaned duplicate copies
        if destination.exists():
            try:
                destination.unlink()
            except Exception:
                pass
        raise PermissionError(
            f"File '{source_file.name}' is currently in use or open in Excel. "
            f"Please close it so the bot can move it. ({last_error or exc})"
        ) from (last_error or exc)
