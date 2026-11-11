"""Configuration module for loading and retrieving runtime settings.

Provides functions to read, validate, and access application settings and paths.
"""

import json
from pathlib import Path
from typing import Any, Dict


def get_default_config_path() -> Path:
    """Return the default configuration file path.

    Returns:
        Path: Path to config.json located at the project root or config directory.
    """
    root_cfg = Path(__file__).resolve().parent.parent / "config.json"
    if root_cfg.exists():
        return root_cfg
    config_dir_cfg = Path(__file__).resolve().parent.parent / "config" / "config.json"
    return config_dir_cfg


def ensure_workspace_directories(base_dir: Path | None = None) -> Dict[str, Path]:
    """Ensure all mandatory runtime directories exist.

    Args:
        base_dir: Optional root directory path. Defaults to project root.

    Returns:
        Dict[str, Path]: Mapping of directory identifiers to initialized Path objects.
    """
    root = base_dir if base_dir is not None else Path(__file__).resolve().parent.parent
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
