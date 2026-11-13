"""Integration test for Phase 1 dual system extraction (OTC & GNB)."""

import threading
import time
from pathlib import Path
from typing import Generator

import openpyxl
import pytest

from mock_portal.app import app
from src.excel_reporter import generate_gnb_rejected_report
from src.gnb_client import run_gnb_extraction_pipeline


@pytest.fixture(scope="module", autouse=True)
def run_mock_server() -> Generator[None, None, None]:
    """Start local mock portal with both OTC and GNB endpoints."""
    server_thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=8080, debug=False, use_reloader=False),
        daemon=True,
    )
    server_thread.start()
    time.sleep(1.5)
    yield


def test_gnb_extraction_and_excel_generation(tmp_path: Path) -> None:
    """Verify autonomous GNB login, table extraction, and Excel generation."""
    config = {
        "gnb": {
            "login_url": "http://127.0.0.1:8080/gnb/login",
            "rejected_transactions_url": "http://127.0.0.1:8080/gnb/rejected-transactions",
            "username": "gnb_admin",
            "password": "gnb_pass",
            "timeout_ms": 15000,
        },
        "gnb_selectors": {
            "login": {
                "username_input": "#gnb-username",
                "password_input": "#gnb-password",
                "submit_button": "#gnb-login-btn",
                "auth_indicator": "#gnb-dashboard",
            },
            "transactions": {
                "table": "#gnb-rejected-table",
                "rows": "#gnb-rejected-table tbody tr",
            },
        },
        "browser": {
            "headless": True,
            "browser_type": "chromium",
            "slow_mo_ms": 0,
            "user_data_dir": str(tmp_path / "gnb_profile"),
        },
    }

    transactions = run_gnb_extraction_pipeline(config, keep_browser_open=False)
    assert len(transactions) == 3

    report = generate_gnb_rejected_report(tmp_path, transactions)
    assert report.name == "GNB_Rejected_Transactions.xlsx"
    assert report.exists()

    wb = openpyxl.load_workbook(report)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))
    wb.close()

    assert len(rows) == 4  # Header + 3 data rows
    assert rows[1][1] == "GNB-TX-9011"
    assert rows[2][1] == "GNB-TX-9012"
    assert rows[3][1] == "GNB-TX-9013"
