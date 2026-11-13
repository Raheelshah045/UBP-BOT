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

    Returns:
        Path: Path to config.json located at the project root or config directory.
    """
    app_root = get_application_root()
    root_cfg = app_root / "config.json"
    if root_cfg.exists():
        return root_cfg
    config_dir_cfg = app_root / "config" / "config.json"
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

    with target_path.open("r", encoding="utf-8") as file_handle:
        data: Dict[str, Any] = json.load(file_handle)
        return data


def save_config(config_data: Dict[str, Any], config_path: Path | None = None) -> None:
    """Save configuration dictionary to a JSON file.

    Args:
        config_data: Configuration values to persist.
        config_path: Optional destination path.
    """
    target_path = config_path if config_path is not None else get_default_config_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as file_handle:
        json.dump(config_data, file_handle, indent=2)
