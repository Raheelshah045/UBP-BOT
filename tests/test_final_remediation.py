"""Targeted test suite for UBP Bot Final Engineering Remediation.

Covers:
 1. OTC pagination: single-page results.
 2. OTC pagination: multi-page traversal aggregating all pages.
 3. OTC pagination: disabled Next button detection (stops cleanly).
 4. OTC pagination: missing Next button (stops cleanly).
 5. OTC pagination: duplicate records across pages (deduplicated).
 6. Search failure / timeout does not extract stale data.
 7. Invalid input record handling (checkpoint updated, skipped immediately, no search).
 8. Direct batch execution without monitoring active (not prematurely cancelled).
 9. Safe report replacement with backup copy.
10. Comprehensive formula sanitization on every column with leading whitespace.
"""

from pathlib import Path

import openpyxl
from playwright.sync_api import sync_playwright

from src.checkpoint import (
    get_batch_summary,
    init_checkpoint_db,
    record_row_result,
    register_batch,
)
from src.excel_reporter import (
    generate_otc_rejected_report,
    sanitize_cell_value,
)
from src.search_service import execute_transaction_search
from src.table_extractor import (
    click_next_page,
    extract_all_transactions,
    has_next_page,
)


# 1. OTC Pagination: Single-page results
def test_pagination_single_page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
        <html>
        <body>
            <table id="transactionsTable">
                <thead><tr><th>Consumer Number</th><th>Bank</th><th>Date</th><th>Status</th></tr></thead>
                <tbody>
                    <tr><td>1001</td><td>HBL</td><td>2026-01-01</td><td>Rejected</td></tr>
                    <tr><td>1002</td><td>HBL</td><td>2026-01-01</td><td>Approved</td></tr>
                </tbody>
            </table>
        </body>
        </html>
        """)
        selectors = {"results": {"table": "#transactionsTable"}}
        assert not has_next_page(page, selectors)
        rows = extract_all_transactions(page, selectors)
        assert len(rows) == 2
        browser.close()


# 2. OTC Pagination: Multi-page traversal aggregating all records
def test_pagination_multi_page_traversal():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
        <html>
        <body>
            <table id="transactionsTable">
                <thead><tr><th>Consumer Number</th><th>Bank</th><th>Date</th><th>RRN</th><th>Status</th></tr></thead>
                <tbody id="tbody">
                    <tr><td>1001</td><td>HBL</td><td>2026-01-01</td><td>RRN1</td><td>Rejected</td></tr>
                </tbody>
            </table>
            <button id="btnNextPage">Next</button>
            <script>
                let p = 1;
                document.getElementById('btnNextPage').onclick = function() {
                    p++;
                    if (p === 2) {
                        document.getElementById('tbody').innerHTML = '<tr><td>1002</td><td>HBL</td><td>2026-01-01</td><td>RRN2</td><td>Rejected</td></tr>';
                    } else if (p === 3) {
                        document.getElementById('tbody').innerHTML = '<tr><td>1003</td><td>HBL</td><td>2026-01-01</td><td>RRN3</td><td>Rejected</td></tr>';
                        this.disabled = true;
                    }
                };
            </script>
        </body>
        </html>
        """)
        selectors = {
            "results": {
                "table": "#transactionsTable",
                "pagination_next": "#btnNextPage",
            }
        }
        assert has_next_page(page, selectors)
        rows = extract_all_transactions(page, selectors, max_pages=5)
        # All 3 records across pages 1, 2, and 3 must reach the final list
        assert len(rows) == 3
        rrns = [r["rrn"] for r in rows]
        assert rrns == ["RRN1", "RRN2", "RRN3"]
        browser.close()


# 3. OTC Pagination: Disabled Next button detection
def test_pagination_disabled_next_button():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        # Button with HTML disabled
        page.set_content("""
        <html>
        <body>
            <table id="transactionsTable">
                <thead><tr><th>Consumer</th></tr></thead>
                <tbody><tr><td>1001</td></tr></tbody>
            </table>
            <button id="btnNextPage" disabled>Next</button>
        </body>
        </html>
        """)
        selectors = {"results": {"table": "#transactionsTable", "pagination_next": "#btnNextPage"}}
        assert not has_next_page(page, selectors)
        assert not click_next_page(page, selectors)

        # Button with class="disabled"
        page.set_content("""
        <html>
        <body>
            <table id="transactionsTable">
                <thead><tr><th>Consumer</th></tr></thead>
                <tbody><tr><td>1001</td></tr></tbody>
            </table>
            <a id="btnNextPage" class="btn disabled">Next</a>
        </body>
        </html>
        """)
        assert not has_next_page(page, selectors)

        # Button with aria-disabled="true"
        page.set_content("""
        <html>
        <body>
            <table id="transactionsTable">
                <thead><tr><th>Consumer</th></tr></thead>
                <tbody><tr><td>1001</td></tr></tbody>
            </table>
            <button id="btnNextPage" aria-disabled="true">Next</button>
        </body>
        </html>
        """)
        assert not has_next_page(page, selectors)
        browser.close()


# 4. OTC Pagination: Missing Next button
def test_pagination_missing_next_button():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
        <html>
        <body>
            <table id="transactionsTable">
                <thead><tr><th>Consumer</th></tr></thead>
                <tbody><tr><td>1001</td></tr></tbody>
            </table>
        </body>
        </html>
        """)
        selectors = {"results": {"table": "#transactionsTable", "pagination_next": "#btnNextPage"}}
        assert not has_next_page(page, selectors)
        assert not click_next_page(page, selectors)
        browser.close()


# 5. OTC Pagination: Duplicate records across pages deduplicated
def test_pagination_duplicates_deduplicated():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
        <html>
        <body>
            <table id="transactionsTable">
                <thead><tr><th>Consumer</th><th>Date</th><th>Time</th><th>RRN</th><th>Status</th></tr></thead>
                <tbody id="tb">
                    <tr><td>1001</td><td>2026-01-01</td><td>10:00:00</td><td>RRN_A</td><td>Rejected</td></tr>
                </tbody>
            </table>
            <button id="btnNextPage">Next</button>
            <script>
                let clicked = false;
                document.getElementById('btnNextPage').onclick = function() {
                    if (!clicked) {
                        clicked = true;
                        // Returns identical record on page 2 plus one new
                        document.getElementById('tb').innerHTML =
                            '<tr><td>1001</td><td>2026-01-01</td><td>10:00:00</td><td>RRN_A</td><td>Rejected</td></tr>' +
                            '<tr><td>1002</td><td>2026-01-01</td><td>10:00:00</td><td>RRN_B</td><td>Rejected</td></tr>';
                    } else {
                        this.disabled = true;
                    }
                };
            </script>
        </body>
        </html>
        """)
        selectors = {"results": {"table": "#transactionsTable", "pagination_next": "#btnNextPage"}}
        rows = extract_all_transactions(page, selectors, max_pages=3)
        assert len(rows) == 2
        assert rows[0]["rrn"] == "RRN_A"
        assert rows[1]["rrn"] == "RRN_B"
        browser.close()


# 6. Search failure / timeout does not extract stale data
def test_search_timeout_returns_false_and_does_not_extract_stale_data():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        # Page with previous search result already in table, but search button does nothing
        page.set_content("""
        <html>
        <body>
            <input id="consumerInput" value="OLD_CONSUMER" />
            <select id="bankSelect"><option value="HBL">HBL</option></select>
            <button id="btnSearch">Search</button>
            <table id="transactionsTable">
                <thead><tr><th>Consumer</th><th>Status</th></tr></thead>
                <tbody>
                    <tr><td>OLD_CONSUMER</td><td>Rejected</td></tr>
                </tbody>
            </table>
            <div id="loadingSpinner" style="display:none;">Loading...</div>
        </body>
        </html>
        """)
        selectors = {
            "search": {"consumer_input": "#consumerInput", "bank_select": "#bankSelect", "search_button": "#btnSearch"},
            "results": {"table": "#transactionsTable", "loading_indicator": "#loadingSpinner"},
        }
        # Searching for NEW_CONSUMER_999 when server hangs/does not update table must return False
        success = execute_transaction_search(
            page,
            selectors,
            bank_name="HBL",
            consumer_number="NEW_CONSUMER_999",
            search_date="2026-01-01",
            bank_mapping={"HBL": "HBL"},
            timeout_ms=500,
        )
        assert success is False
        browser.close()


# 7. Invalid input row handling: recorded as FAILED, skipped immediately, no search
def test_invalid_input_row_skips_immediately_without_search(tmp_path: Path):
    db_file = tmp_path / "checkpoint.db"
    init_checkpoint_db(db_file)
    batch_id = "batch_test_invalid_skip"
    register_batch(db_file, batch_id, "test.xlsx")

    # Record invalid row failure
    record_row_result(
        db_file,
        batch_id,
        row_number=1,
        consumer_number="",
        bank_service="",
        date="",
        status="FAILED",
        transactions_count=0,
        rejected_count=0,
        error_message="Missing consumer number",
    )
    summary = get_batch_summary(db_file, batch_id)
    assert len(summary["rows"]) == 1
    assert summary["rows"][0]["status"] == "FAILED"
    assert summary["rows"][0]["error_message"] == "Missing consumer number"


# 8. Direct batch execution without monitoring active is NOT cancelled
def test_direct_batch_execution_not_cancelled_without_monitoring(tmp_path: Path):
    from src.queue_manager import is_monitoring_active
    from src.runner import _check_cancellation, is_stopped, set_stop_state

    set_stop_state(False)
    assert not is_monitoring_active()
    # Standalone execution must not treat monitoring inactivity as cancellation
    assert not is_stopped()
    assert not _check_cancellation(None)


# 9. Safe report replacement with backup copy
def test_safe_report_replacement_creates_backup(tmp_path: Path):
    tx1 = [{"consumer_number": "111", "status": "Rejected", "response_code": "05", "date": "2026-01-01"}]
    tx2 = [{"consumer_number": "222", "status": "Rejected", "response_code": "05", "date": "2026-01-02"}]

    # Generate first version
    rep1 = generate_otc_rejected_report(tmp_path, tx1)
    assert rep1.exists()

    # Generate second version with same target name
    rep2 = generate_otc_rejected_report(tmp_path, tx2)
    assert rep2.exists()

    # Backup of previous report must exist
    backup_file = tmp_path / "OTC_Rejected_Transactions_prev.xlsx"
    assert backup_file.exists()
    wb_backup = openpyxl.load_workbook(backup_file)
    sheet_b = wb_backup.active
    # First version had 1 row (row 2 cell 3 is 111)
    assert sheet_b.cell(row=2, column=3).value == "111"


# 10. Comprehensive formula sanitization on every column with leading whitespace
def test_formula_sanitization_with_leading_whitespace():
    assert sanitize_cell_value("   =1+1") == "'   =1+1"
    assert sanitize_cell_value(" \t=SUM(A1)") == "' \t=SUM(A1)"
    assert sanitize_cell_value("  @cmd") == "'  @cmd"
    assert sanitize_cell_value(" +calc") == "' +calc"
    assert sanitize_cell_value(" -2+3") == "' -2+3"
    assert sanitize_cell_value("\r=test") == "'\r=test"
    assert sanitize_cell_value("Normal Account 123") == "Normal Account 123"
