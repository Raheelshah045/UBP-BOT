"""Regression tests for canonical configuration and frozen execution paths."""

import json
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import openpyxl

from src.config import (
    get_application_root,
    get_default_config_path,
    load_config,
    save_config,
)


def test_canonical_config_path_in_source_execution() -> None:
    """Verify source execution resolves canonical config/config.json without root duplicates."""
    cfg_path = get_default_config_path()
    assert cfg_path.name == "config.json"
    assert cfg_path.parent.name == "config"
    assert cfg_path.is_file(), f"Canonical configuration missing at: {cfg_path}"

    # Verify no duplicate root-level config.json exists
    root_cfg = cfg_path.parent.parent / "config.json"
    assert not root_cfg.exists(), "Duplicate root-level config.json must not exist in repository"


def test_canonical_config_path_in_frozen_execution(tmp_path: Path) -> None:
    """Verify frozen (PyInstaller executable) execution resolves config/config.json."""
    fake_exe = tmp_path / "UBP-Bot.exe"
    fake_exe.touch()

    # Create canonical config in temporary directory simulating frozen bundle
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = cfg_dir / "config.json"
    cfg_file.write_text('{"portal": {"login_url": "http://127.0.0.1:9999/"}}', encoding="utf-8")

    with patch.object(sys, "frozen", True, create=True), patch.object(
        sys, "executable", str(fake_exe)
    ):
        resolved_root = get_application_root()
        assert resolved_root == tmp_path

        resolved_cfg = get_default_config_path()
        assert resolved_cfg == cfg_file
        assert resolved_cfg.is_file()

        loaded: Dict[str, Any] = load_config()
        assert loaded.get("portal", {}).get("login_url") == "http://127.0.0.1:9999/"

        # Ensure no root config.json is created
        assert not (tmp_path / "config.json").exists()


def test_save_config_persists_to_canonical_location_without_creating_root_config(
    tmp_path: Path,
) -> None:
    """Verify save_config writes to canonical location and never recreates root config.json."""
    fake_exe = tmp_path / "UBP-Bot.exe"
    fake_exe.touch()
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)

    test_data = {
        "portal": {"login_url": "http://127.0.0.1:5173/"},
        "gnb": {"username": "ops_user", "password": "SecretPasswordToScrub"},
    }

    with patch.object(sys, "frozen", True, create=True), patch.object(
        sys, "executable", str(fake_exe)
    ):
        save_config(test_data)

        canonical_path = tmp_path / "config" / "config.json"
        assert canonical_path.is_file()

        with canonical_path.open("r", encoding="utf-8") as f:
            saved = json.load(f)

        assert saved["gnb"]["username"] == "ops_user"
        assert saved["gnb"]["password"] == ""

        # Assert no sibling root config was created
        assert not (tmp_path / "config.json").exists()


def test_sample_input_relocation_and_structure() -> None:
    """Verify sample_input.xlsx has been relocated to tests/fixtures and is valid."""
    app_root = get_application_root()
    fixture_path = app_root / "tests" / "fixtures" / "sample_input.xlsx"
    assert fixture_path.is_file(), f"Sample input fixture missing at: {fixture_path}"

    # Verify input/ live directory does NOT contain the sample file
    live_input_path = app_root / "input" / "sample_input.xlsx"
    assert not live_input_path.exists(), "sample_input.xlsx must not reside in live input/ directory"

    wb = openpyxl.load_workbook(fixture_path)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))
    assert len(rows) > 1, "Fixture spreadsheet must contain headers and data rows"
    headers = [str(cell).strip().lower() for cell in rows[0]]
    assert any("consumer" in h for h in headers)
