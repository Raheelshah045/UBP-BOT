"""End-to-end integration test running browser automation against the local mock portal."""

import threading
import time
from pathlib import Path
from typing import Generator

import openpyxl
import pytest
from playwright.sync_api import sync_playwright

from mock_portal.app import app
from src.auth_manager import check_is_authenticated
from src.classifier import classify_transaction
from src.excel_reporter import generate_excel_report
from src.portal_navigator import navigate_to_check_bill_status
from src.search_service import execute_transaction_search
from src.table_extractor import extract_all_transactions


@pytest.fixture(scope="module", autouse=True)
def run_mock_server() -> Generator[None, None, None]:
    """Start local mock OTC portal in a daemon thread for integration testing."""
    server_thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=8080, debug=False, use_reloader=False),
        daemon=True,
    )
    server_thread.start()
    time.sleep(1.5)
    yield


def test_end_to_end_login_navigation_search_and_report_generation(tmp_path: Path) -> None:
    """Verify full workflow: login, navigation, multi-transaction search, and Excel export."""
    login_url = "http://127.0.0.1:8080/login"
    check_bill_url = "http://127.0.0.1:8080/bps/check-bill-status"
    selectors = {
        "login": {
            "auth_indicator": "#userProfile",
            "session_expired_indicator": "#sessionExpiredAlert",
        },
        "navigation": {"bps_menu": "#navBps", "check_bill_status_link": "#navCheckBillStatus"},
        "search": {
            "bank_select": "#bankSelect",
            "consumer_input": "#consumerNumberInput",
            "from_date_input": "#fromDateInput",
            "to_date_input": "#toDateInput",
            "search_button": "#btnSearch",
        },
        "results": {
            "table": "#transactionsTable",
            "rows": "#transactionsTable tbody tr",
            "loading_indicator": "#loadingSpinner",
            "no_record_message": "#noRecordsAlert",
            "pagination_next": "#btnNextPage",
        },
    }
    bank_mapping = {"HBL": "Habib Bank Limited (HBL)"}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Step 1: Open Login and submit credentials
        page.goto(login_url)
        page.fill("#username", "bank_operator")
        page.fill("#password", "Password@123")
        page.fill("#captcha", "7X9K2")
        page.fill("#otp", "123456")
        page.click("#btnLogin")

        assert check_is_authenticated(page, selectors) is True

        # Step 2: Navigate to Check Bill Status
        nav_success = navigate_to_check_bill_status(page, selectors, check_bill_url)
        assert nav_success is True

        # Step 3: Execute search for consumer with multiple records (Approved + Qualifying Rejected)
        consumer_num = "10012345678901"
        search_date = "2026-11-10"
        search_ok = execute_transaction_search(
            page=page,
            selectors=selectors,
            bank_name="HBL",
            consumer_number=consumer_num,
            search_date=search_date,
            bank_mapping=bank_mapping,
        )
        assert search_ok is True

        # Step 4: Extract results
        extracted = extract_all_transactions(page, selectors)
        assert len(extracted) == 2

        # Step 5: Classify records
        classified = []
        for item in extracted:
            cls = classify_transaction(item["status"], item["response_code"])
            item["classification"] = cls["classification"]
            item["is_qualifying_rejection"] = cls["is_qualifying_rejection"]
            classified.append(item)

        qualifying = [t for t in classified if t["is_qualifying_rejection"]]
        approved = [t for t in classified if t["classification"] == "Approved"]
        assert len(qualifying) == 1
        assert len(approved) == 1
        assert qualifying[0]["response_code"] == "51"

        # Step 6: Generate Excel report
        out_dir = tmp_path / "e2e_output"
        input_recs = [
            {
                "row_number": 2,
                "consumer_number": consumer_num,
                "bank_service": "HBL",
                "date": search_date,
            }
        ]
        proc_rows = [
            {
                "row_number": 2,
                "consumer_number": consumer_num,
                "bank_service": "HBL",
                "date": search_date,
                "status": "SUCCESS",
                "transactions_count": 2,
                "rejected_count": 1,
                "processed_at": "2026-11-11T22:30:00",
            }
        ]

        report_path = generate_excel_report(out_dir, input_recs, proc_rows, classified)
        assert report_path.exists()

        wb = openpyxl.load_workbook(report_path)
        assert "OTC Rejected Transactions" in wb.sheetnames
        rej_sheet = wb["OTC Rejected Transactions"]
        # Exactly 1 qualifying rejection row
        assert rej_sheet.max_row == 2
        assert rej_sheet.cell(row=2, column=10).value == "Rejected"
        assert rej_sheet.cell(row=2, column=11).value == "51"

        browser.close()
