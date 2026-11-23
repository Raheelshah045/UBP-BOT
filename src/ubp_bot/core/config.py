"""Configuration and dynamic directory management for UBP Bot.

Provides functions to read, validate, and persist runtime settings.
Supports dynamic input/output directories with read/write permission verification,
preventing silent fallback to predefined directories.
"""

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from src.ubp_bot.security.secret_manager import (
    load_env_file,
    sanitize_config_for_storage,
)


def get_application_root() -> Path:
    """Return the absolute root directory of the application.

    Works consistently in development environments and when compiled as a
    portable frozen binary (PyInstaller).

    Returns:
        Path: Resolved application root folder.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    if os.environ.get("APP_DIR"):
        return Path(os.environ["APP_DIR"]).resolve()
    here = Path(__file__).resolve()
    # Handle both src/ubp_bot/core/config.py (3 levels up to root) and src/config.py
    if here.parent.name == "core" and here.parent.parent.name == "ubp_bot":
        return here.parent.parent.parent.parent
    if here.parent.name == "src":
        return here.parent.parent
    return here.parent.parent


def initialize_environment() -> None:
    """Initialize critical runtime environment variables before subsystem imports."""
    if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
        local_browsers = resolve_app_path("browsers")
        if local_browsers.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(local_browsers)


def resolve_app_path(relative_or_absolute: str | Path) -> Path:
    """Resolve a path relative to the application root if not already absolute.

    Args:
        relative_or_absolute: File or folder path string or Path object.

    Returns:
        Path: Absolute resolved path.
    """
    p = Path(relative_or_absolute)
    if p.is_absolute():
        return p
    return (get_application_root() / p).resolve()


def get_default_config_path() -> Path:
    """Return the canonical configuration file path (config/config.json)."""
    return get_application_root() / "config" / "config.json"


def validate_directory_permissions(path: Path | str) -> Tuple[bool, str]:
    """Validate that a directory exists (or can be created) and has read/write permissions.

    Args:
        path: Path to target directory.

    Returns:
        Tuple[bool, str]: (is_valid, status_or_error_message)
    """
    target = Path(path).resolve()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return False, f"Cannot create directory: {exc}"

    if not target.is_dir():
        return False, f"Path exists but is not a directory: {target}"

    # Verify read access
    try:
        list(target.iterdir())
    except PermissionError:
        return False, f"Directory read permission denied: {target}"
    except Exception as exc:
        return False, f"Directory read access failure: {exc}"

    # Verify write access with atomic probe file (use uuid to avoid race conditions)
    probe_file = target / f".perm_probe_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    try:
        with probe_file.open("w", encoding="utf-8") as f:
            f.write("ubp_bot_probe")
        probe_file.unlink(missing_ok=True)
    except PermissionError:
        return False, f"Directory write permission denied: {target}"
    except Exception as exc:
        return False, f"Directory write access failure: {exc}"

    return True, "Valid Read/Write"


def has_valid_directory_configuration(config: Dict[str, Any]) -> Tuple[bool, str]:
    """Check if input and output directories are explicitly configured and valid.

    Args:
        config: Application configuration dictionary.

    Returns:
        Tuple[bool, str]: (is_valid, description_or_reason)
    """
    dirs_cfg = config.get("directories", {})
    input_str = dirs_cfg.get("input_dir")
    output_str = dirs_cfg.get("output_dir")

    if not input_str or not str(input_str).strip():
        return False, "Input directory is not configured."
    if not output_str or not str(output_str).strip():
        return False, "Output directory is not configured."

    in_valid, in_reason = validate_directory_permissions(resolve_app_path(input_str))
    if not in_valid:
        return False, f"Invalid Input Directory: {in_reason}"

    out_valid, out_reason = validate_directory_permissions(resolve_app_path(output_str))
    if not out_valid:
        return False, f"Invalid Output Directory: {out_reason}"

    return True, "Directories Configured and Valid"


def ensure_workspace_directories(
    base_dir: Optional[Path] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Path]:
    """Ensure all mandatory runtime directories exist.

    Uses configured dynamic directories if present in config, otherwise defaults
    to application root paths for internal state (processing, completed, failed, logs, checkpoints).

    Args:
        base_dir: Optional root directory path. Defaults to application root.
        config: Optional configuration dictionary to extract custom directory overrides.

    Returns:
        Dict[str, Path]: Mapping of directory identifiers to initialized Path objects.
    """
    root = base_dir if base_dir is not None else get_application_root()
    dirs_cfg = config.get("directories", {}) if config else {}

    input_path = (
        resolve_app_path(dirs_cfg["input_dir"])
        if dirs_cfg.get("input_dir")
        else root / "input"
    )
    output_path = (
        resolve_app_path(dirs_cfg["output_dir"])
        if dirs_cfg.get("output_dir")
        else root / "output"
    )
    completed_path = (
        resolve_app_path(dirs_cfg["completed_dir"])
        if dirs_cfg.get("completed_dir")
        else root / "completed"
    )
    failed_path = (
        resolve_app_path(dirs_cfg["failed_dir"])
        if dirs_cfg.get("failed_dir")
        else root / "failed"
    )
    processing_path = (
        resolve_app_path(dirs_cfg["processing_dir"])
        if dirs_cfg.get("processing_dir")
        else root / "processing"
    )
    logs_path = (
        resolve_app_path(dirs_cfg["logs_dir"])
        if dirs_cfg.get("logs_dir")
        else root / "logs"
    )
    checkpoints_path = root / "checkpoints"
    config_dir_path = root / "config"

    mapping: Dict[str, Path] = {
        "input": input_path,
        "output": output_path,
        "completed": completed_path,
        "failed": failed_path,
        "processing": processing_path,
        "logs": logs_path,
        "checkpoints": checkpoints_path,
        "config": config_dir_path,
    }

    for name, dir_path in mapping.items():
        dir_path.mkdir(parents=True, exist_ok=True)

    return mapping



def safe_int_setting(value: Any, default: int, minimum: int = 1) -> int:
    """Parse an optional integer setting without crashing on blank or malformed values."""
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return max(minimum, default)
    return max(minimum, parsed)


def validate_portal_endpoint(url: str) -> Tuple[bool, str]:
    """Validate an operator-supplied HTTP(S) portal URL and reject local development URLs."""
    from urllib.parse import urlparse

    candidate = (url or "").strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False, "Enter a complete HTTP or HTTPS portal URL."
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost"):
        return False, "Localhost URLs are not valid live banking portal endpoints."
    if "SET-APPROVED-" in candidate.upper():
        return False, "Replace the endpoint placeholder with the IT-approved portal URL."
    return True, "Valid portal endpoint."

def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load configuration dictionary from a JSON file.

    Loads base settings from config.json and overrides credentials from environment
    or local .env if present.

    Args:
        config_path: Optional explicit path to configuration file.

    Returns:
        Dict[str, Any]: Parsed configuration values.

    Raises:
        FileNotFoundError: If the specified config file does not exist.
    """
    target_path = config_path if config_path is not None else get_default_config_path()
    if not target_path.exists():
        raise FileNotFoundError(f"Configuration file not found at: {target_path}")

    # Load local .env without exposing credentials in logs
    env_file = get_application_root() / ".env"
    load_env_file(env_file)

    with target_path.open("r", encoding="utf-8") as file_handle:
        data: Dict[str, Any] = json.load(file_handle)

    # Secure environment variable overrides
    if "GNB_USERNAME" in os.environ:
        data.setdefault("gnb", {})["username"] = os.environ["GNB_USERNAME"]
    if "GNB_PASSWORD" in os.environ:
        data.setdefault("gnb", {})["password"] = os.environ["GNB_PASSWORD"]
    if "GNB_LOGIN_URL" in os.environ:
        data.setdefault("gnb", {})["login_url"] = os.environ["GNB_LOGIN_URL"]
    if "GNB_REJECTED_TRANSACTIONS_URL" in os.environ:
        data.setdefault("gnb", {})["rejected_transactions_url"] = os.environ["GNB_REJECTED_TRANSACTIONS_URL"]

    return data


def save_config(config_data: Dict[str, Any], config_path: Optional[Path] = None) -> None:
    """Save configuration dictionary to a JSON file safely without storing secrets.

    Args:
        config_data: Configuration values to persist.
        config_path: Optional destination path.
    """
    target_path = config_path if config_path is not None else get_default_config_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    sanitized_data = sanitize_config_for_storage(config_data)

    with target_path.open("w", encoding="utf-8") as file_handle:
        json.dump(sanitized_data, file_handle, indent=2)


def update_configured_directories(
    input_dir: str | Path,
    output_dir: str | Path,
    config_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Persist updated dynamic input and output folder paths to configuration.

    Args:
        input_dir: Selected input directory path.
        output_dir: Selected output directory path.
        config_path: Optional path to config file.

    Returns:
        Dict[str, Any]: Updated configuration dictionary.

    Raises:
        ValueError: If either directory fails permission validation.
    """
    in_path = Path(input_dir).resolve()
    out_path = Path(output_dir).resolve()

    in_valid, in_err = validate_directory_permissions(in_path)
    if not in_valid:
        raise ValueError(f"Input directory validation failed: {in_err}")

    out_valid, out_err = validate_directory_permissions(out_path)
    if not out_valid:
        raise ValueError(f"Output directory validation failed: {out_err}")

    config = load_config(config_path)
    dirs_section = config.setdefault("directories", {})
    dirs_section["input_dir"] = str(in_path)
    dirs_section["output_dir"] = str(out_path)

    save_config(config, config_path)
    return config
