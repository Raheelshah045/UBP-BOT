"""Unit tests for the portable system diagnostics module."""

from pathlib import Path
from typing import Any, Dict

from src.diagnostics import (
    check_dependencies,
    check_directory_permissions,
    check_python_environment,
    format_diagnostics_report,
    run_full_system_diagnostics,
)


def test_python_environment_inspection() -> None:
    """Verify python environment check reports valid platform and architecture."""
    res = check_python_environment()
    assert "is_64bit" in res
    assert "python_version" in res
    assert res["status"] in ("PASS", "WARN")


def test_dependencies_check() -> None:
    """Verify dependencies check verifies all installed packages."""
    res = check_dependencies()
    assert res["status"] == "PASS"
    assert "pandas" in res["versions"]
    assert "playwright" in res["versions"]
    assert "openpyxl" in res["versions"]


def test_directory_permissions_check() -> None:
    """Verify directory permissions check confirms user write access."""
    res = check_directory_permissions()
    assert res["status"] == "PASS"
    assert len(res["failures"]) == 0


def test_full_system_diagnostics_and_report_formatting(tmp_path: Path) -> None:
    """Verify end-to-end diagnostics execution and readable report output."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text('{"portal": {"login_url": "http://127.0.0.1:8080/login"}}', encoding="utf-8")

    results: Dict[str, Any] = run_full_system_diagnostics(cfg_file)
    assert results["overall_status"] in ("PASS", "WARN")

    report_str = format_diagnostics_report(results)
    assert "Pre-flight Diagnostics" in report_str
    assert "Runtime Environment" in report_str
    assert "Permissions" in report_str
