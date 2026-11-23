"""Unit tests for dynamic input/output directory validation, persistence, and permissions."""

import json
from pathlib import Path

from src.ubp_bot.core.config import (
    has_valid_directory_configuration,
    safe_int_setting,
    validate_portal_endpoint,
    update_configured_directories,
    validate_directory_permissions,
)


def test_validate_directory_permissions_success(tmp_path: Path):
    """Verify that a standard temporary directory passes read/write validation."""
    valid_dir = tmp_path / "test_valid"
    valid_dir.mkdir(parents=True, exist_ok=True)

    is_valid, msg = validate_directory_permissions(valid_dir)
    assert is_valid is True
    assert "Valid Read/Write" in msg


def test_validate_directory_permissions_creates_missing(tmp_path: Path):
    """Verify that a non-existent directory is automatically created and validated."""
    missing_dir = tmp_path / "nested" / "created_dir"
    assert not missing_dir.exists()

    is_valid, msg = validate_directory_permissions(missing_dir)
    assert is_valid is True
    assert missing_dir.exists()


def test_has_valid_directory_configuration_detects_empty(tmp_path: Path):
    """Verify that empty or missing directories return False without silent default fallback."""
    cfg = {"directories": {"input_dir": "", "output_dir": ""}}
    is_valid, reason = has_valid_directory_configuration(cfg)
    assert is_valid is False
    assert "not configured" in reason.lower()


def test_update_configured_directories_persists_safely(tmp_path: Path):
    """Verify update_configured_directories persists changes to config.json and validates them."""
    cfg_file = tmp_path / "config.json"
    initial_data = {
        "directories": {
            "input_dir": str(tmp_path / "old_in"),
            "output_dir": str(tmp_path / "old_out"),
        }
    }
    with cfg_file.open("w", encoding="utf-8") as f:
        json.dump(initial_data, f)

    new_in = tmp_path / "new_input"
    new_out = tmp_path / "new_output"
    new_in.mkdir()
    new_out.mkdir()

    updated_cfg = update_configured_directories(new_in, new_out, cfg_file)
    assert updated_cfg["directories"]["input_dir"] == str(new_in.resolve())
    assert updated_cfg["directories"]["output_dir"] == str(new_out.resolve())

    # Read back from disk to confirm persistence
    with cfg_file.open("r", encoding="utf-8") as f:
        reloaded = json.load(f)
    assert reloaded["directories"]["input_dir"] == str(new_in.resolve())
    assert reloaded["directories"]["output_dir"] == str(new_out.resolve())



def test_safe_int_setting_uses_default_for_blank_values():
    """Blank persisted settings must not crash runtime startup."""
    assert safe_int_setting("", 300) == 300
    assert safe_int_setting(None, 300) == 300
    assert safe_int_setting("not-a-number", 300) == 300
    assert safe_int_setting("45", 300) == 45


def test_validate_portal_endpoint_rejects_local_development_urls():
    """The live OTC endpoint must never silently point at the local dashboard."""
    assert validate_portal_endpoint("http://127.0.0.1:5173/")[0] is False
    assert validate_portal_endpoint("http://localhost:5173/")[0] is False
    assert validate_portal_endpoint("https://SET-APPROVED-OTC-PORTAL-URL")[0] is False
    assert validate_portal_endpoint("https://otc.example.com/login")[0] is True
