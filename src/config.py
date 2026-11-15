"""Configuration module for loading and retrieving runtime settings.

Provides functions to read, validate, and access application settings and paths.
Supports frozen portable binaries (PyInstaller) and standard Python environments.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict


def get_application_root() -> Path:
    """Return the absolute root directory of the application.

    Works consistently in standard development mode and when running as a
    standalone portable binary (e.g. PyInstaller frozen executable).

    Returns:
        Path: Resolved application root folder.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    if os.environ.get("APP_DIR"):
        return Path(os.environ["APP_DIR"]).resolve()
    here = Path(__file__).resolve()
    if here.parent.name == "src" and here.parent.parent.name == "app":
        return here.parent.parent.parent
    return here.parent.parent


def initialize_environment() -> None:
    """Initialize critical runtime environment variables before subsystem imports.

    Sets PLAYWRIGHT_BROWSERS_PATH to the local application 'browsers' directory
    if it exists and is not already defined, preventing Playwright from attempting
    to locate or download browsers to restricted administrator paths.
    """
    if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
        local_browsers = resolve_app_path("browsers")
        if local_browsers.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(local_browsers)


def resolve_app_path(relative_or_absolute: str | Path) -> Path:
    """Resolve a path relative to the portable application root.

    Args:
        relative_or_absolute: File or directory path string or Path object.

    Returns:
        Path: Absolute resolved path.
    """
    p = Path(relative_or_absolute)
    if p.is_absolute():
        return p
    return (get_application_root() / p).resolve()


def get_default_config_path() -> Path:
    """Return the default configuration file path.

    Prefers config/config.json as the authoritative configuration, with fallback
    to root config.json for legacy backwards compatibility.

    Returns:
        Path: Path to config.json located in config/ directory or project root.
    """
    app_root = get_application_root()
    config_dir_cfg = app_root / "config" / "config.json"
    if config_dir_cfg.exists():
        return config_dir_cfg
    root_cfg = app_root / "config.json"
    if root_cfg.exists():
        return root_cfg
    return config_dir_cfg


def ensure_workspace_directories(base_dir: Path | None = None) -> Dict[str, Path]:
    """Ensure all mandatory runtime directories exist.

    Args:
        base_dir: Optional root directory path. Defaults to application root.

    Returns:
        Dict[str, Path]: Mapping of directory identifiers to initialized Path objects.
    """
    root = base_dir if base_dir is not None else get_application_root()
    dir_names = [
        "input",
        "processing",
        "completed",
        "failed",
        "output",
        "logs",
        "checkpoints",
        "config",
    ]
    created: Dict[str, Path] = {}
    for name in dir_names:
        dir_path = root / name
        dir_path.mkdir(parents=True, exist_ok=True)
        created[name] = dir_path
    return created


def load_config(config_path: Path | None = None) -> Dict[str, Any]:
    """Load configuration dictionary from a JSON file.

    Loads base settings from config.json and overrides credentials / secrets
    from environment variables (or local .env file) if present.

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

    # Optionally parse local .env file into os.environ if present without printing contents
    env_file = get_application_root() / ".env"
    if env_file.exists():
        try:
            with env_file.open("r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#") and "=" in stripped:
                        key, val = stripped.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key not in os.environ:
                            os.environ[key] = val
        except Exception:
            pass

    with target_path.open("r", encoding="utf-8") as file_handle:
        data: Dict[str, Any] = json.load(file_handle)

    # Environment variable overrides for sensitive settings
    if "GNB_USERNAME" in os.environ:
        data.setdefault("gnb", {})["username"] = os.environ["GNB_USERNAME"]
    if "GNB_PASSWORD" in os.environ:
        data.setdefault("gnb", {})["password"] = os.environ["GNB_PASSWORD"]
    if "GNB_LOGIN_URL" in os.environ:
        data.setdefault("gnb", {})["login_url"] = os.environ["GNB_LOGIN_URL"]
    if "GNB_REJECTED_TRANSACTIONS_URL" in os.environ:
        data.setdefault("gnb", {})["rejected_transactions_url"] = os.environ["GNB_REJECTED_TRANSACTIONS_URL"]

    return data


def _sanitize_config_for_storage(data: Any) -> Any:
    """Recursively scrub passwords and secrets before writing configuration to disk."""
    if isinstance(data, dict):
        sanitized: Dict[str, Any] = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(s in key_lower for s in ("password", "secret", "token", "api_key")):
                sanitized[key] = ""
            elif isinstance(value, (dict, list)):
                sanitized[key] = _sanitize_config_for_storage(value)
            else:
                sanitized[key] = value
        return sanitized
    elif isinstance(data, list):
        return [_sanitize_config_for_storage(item) for item in data]
    return data


def save_config(config_data: Dict[str, Any], config_path: Path | None = None) -> None:
    """Save configuration dictionary to a JSON file safely without storing secrets.

    Args:
        config_data: Configuration values to persist.
        config_path: Optional destination path.
    """
    target_path = config_path if config_path is not None else get_default_config_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    sanitized_data = _sanitize_config_for_storage(config_data)

    with target_path.open("w", encoding="utf-8") as file_handle:
        json.dump(sanitized_data, file_handle, indent=2)

    # If saving default root or config directory config, synchronize sibling canonical copy
    app_root = get_application_root()
    root_cfg = app_root / "config.json"
    nested_cfg = app_root / "config" / "config.json"
    if config_path is None:
        try:
            if target_path == root_cfg and nested_cfg.parent.exists():
                with nested_cfg.open("w", encoding="utf-8") as fh:
                    json.dump(sanitized_data, fh, indent=2)
            elif target_path == nested_cfg and root_cfg.exists():
                with root_cfg.open("w", encoding="utf-8") as fh:
                    json.dump(sanitized_data, fh, indent=2)
        except Exception:
            pass
