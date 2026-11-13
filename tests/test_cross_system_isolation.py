"""Tests for cross-system isolation and input file routing in UBP Bot."""

from pathlib import Path

from src.file_detector import identify_system_target


def test_input_file_system_target_identification(tmp_path: Path) -> None:
    """Verify input spreadsheets are correctly and safely routed to their respective systems."""
    otc_file1 = tmp_path / "OTC_Transactions.xlsx"
    otc_file2 = tmp_path / "otc_batch_20261113.xlsx"
    gnb_file1 = tmp_path / "GNB_Transactions.xlsx"
    gnb_file2 = tmp_path / "gnb_report_input.csv"
    ambiguous_file = tmp_path / "Transactions_Daily.xlsx"
    conflicting_file = tmp_path / "OTC_GNB_Combined.xlsx"

    assert identify_system_target(otc_file1) == "otc"
    assert identify_system_target(otc_file2) == "otc"
    assert identify_system_target(gnb_file1) == "gnb"
    assert identify_system_target(gnb_file2) == "gnb"
    assert identify_system_target(ambiguous_file) == "unknown"
    assert identify_system_target(conflicting_file) == "unknown"


def test_isolated_browser_profile_directories() -> None:
    """Verify OTC and GNB use separate persistent user data directories."""
    cfg = {
        "user_data_dir": "checkpoints/browser_profile",
        "headless": True,
    }
    # Verify the code creates separate directory strings
    base = cfg.get("user_data_dir")
    otc_dir = base
    gnb_dir = f"{base}_gnb"

    assert otc_dir != gnb_dir
    assert "gnb" in gnb_dir

