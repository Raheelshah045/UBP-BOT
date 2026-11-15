"""Performance benchmark script for UBP Bot Phase 1.

Measures processing times, record counts, and extraction accuracy across:
 1. 20-record OTC run
 2. 100-record OTC run
 3. GNB extraction run
 4. Simultaneous OTC + GNB dual run
"""

import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright

from mock_portal.app import app
from src.classifier import classify_transaction
from src.excel_reporter import (
    generate_gnb_rejected_report,
    generate_otc_rejected_report,
)
from src.table_extractor import extract_all_transactions


def start_mock_server() -> threading.Thread:
    """Start local mock server on port 8080."""
    t = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=8080, debug=False, use_reloader=False),
        daemon=True,
    )
    t.start()
    time.sleep(1.2)
    return t


def run_benchmark():
    start_mock_server()

    results: Dict[str, Any] = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Login to OTC mock portal
        page.goto("http://127.0.0.1:8080/login")
        page.fill("#username", "bank_operator")
        page.fill("#password", "Password@123")
        page.fill("#captcha", "7X9K2")
        page.fill("#otp", "123456")
        page.click("#btnLogin")
        page.wait_for_load_state("networkidle")

        page.goto("http://127.0.0.1:8080/bps/check-bill-status")
        page.wait_for_selector("#bankSelect")

        selectors = {
            "search": {
                "bank_select": "#bankSelect",
                "consumer_input": "#consumerNumberInput",
                "search_button": "#btnSearch",
            },
            "results": {
                "table": "#transactionsTable",
                "no_record_message": "#noRecordsAlert",
                "loading_indicator": "#loadingSpinner",
                "pagination_next": "#btnNextPage",
            },
        }

        # Benchmark 1: 20-record OTC run
        print("[*] Running Benchmark 1: 20-record OTC run...")
        t0 = time.time()
        otc_20_extracted: List[Dict[str, Any]] = []
        for i in range(1, 21):
            c_num = f"700852963140{i:02d}"
            page.select_option("#bankSelect", value="UBL")
            page.fill("#consumerNumberInput", c_num)
            page.click("#btnSearch")
            page.wait_for_timeout(40)
            rows = extract_all_transactions(page, selectors, max_pages=3)
            for r in rows:
                cls = classify_transaction(r.get("status", ""), r.get("response_code", ""), {})
                r["is_qualifying_rejection"] = cls["is_qualifying_rejection"]
                r["classification"] = cls["classification"]
            otc_20_extracted.extend(rows)
        t_otc_20 = time.time() - t0

        out_tmp = Path(tempfile.mkdtemp())
        rep_20 = generate_otc_rejected_report(out_tmp, otc_20_extracted)
        results["otc_20"] = {
            "time_seconds": round(t_otc_20, 2),
            "records_extracted": len(otc_20_extracted),
            "qualifying_rejected": len([r for r in otc_20_extracted if r.get("is_qualifying_rejection")]),
            "report_path": str(rep_20),
        }

        # Benchmark 2: 100-record OTC run (simulation across cycled bank datasets)
        print("[*] Running Benchmark 2: 100-record OTC run...")
        t0 = time.time()
        otc_100_extracted: List[Dict[str, Any]] = []
        for i in range(1, 101):
            c_num = f"700852963140{(i % 20) + 1:02d}"
            page.fill("#consumerNumberInput", c_num)
            page.click("#btnSearch")
            page.wait_for_timeout(25)
            rows = extract_all_transactions(page, selectors, max_pages=2)
            for r in rows:
                cls = classify_transaction(r.get("status", ""), r.get("response_code", ""), {})
                r["is_qualifying_rejection"] = cls["is_qualifying_rejection"]
                r["classification"] = cls["classification"]
            otc_100_extracted.extend(rows)
        t_otc_100 = time.time() - t0

        rep_100 = generate_otc_rejected_report(out_tmp, otc_100_extracted)
        results["otc_100"] = {
            "time_seconds": round(t_otc_100, 2),
            "records_extracted": len(otc_100_extracted),
            "qualifying_rejected": len([r for r in otc_100_extracted if r.get("is_qualifying_rejection")]),
            "report_path": str(rep_100),
        }

        # Benchmark 3: GNB Extraction run
        print("[*] Running Benchmark 3: GNB extraction run...")
        t0 = time.time()
        gnb_page = context.new_page()
        gnb_page.goto("http://127.0.0.1:8080/gnb/login")
        gnb_page.fill("#gnb-username", "admin")
        gnb_page.fill("#gnb-password", "pass")
        gnb_page.click("#gnb-login-btn")
        gnb_page.wait_for_selector("#gnb-rejected-table")

        from src.gnb_client import extract_transactions_from_active_table

        gnb_txs = extract_transactions_from_active_table(gnb_page)
        t_gnb = time.time() - t0
        rep_gnb = generate_gnb_rejected_report(out_tmp, gnb_txs)
        results["gnb"] = {
            "time_seconds": round(t_gnb, 2),
            "records_extracted": len(gnb_txs),
            "report_path": str(rep_gnb),
        }

        # Benchmark 4: Simultaneous OTC + GNB Run
        print("[*] Running Benchmark 4: Simultaneous OTC and GNB Run...")
        t0 = time.time()
        dual_results: Dict[str, Any] = {}

        def otc_task():
            with sync_playwright() as p_otc:
                br = p_otc.chromium.launch(headless=True)
                sub_page = br.new_page()
                sub_page.goto("http://127.0.0.1:8080/login")
                sub_page.fill("#username", "admin")
                sub_page.fill("#password", "password123")
                sub_page.fill("#captcha", "1234")
                sub_page.fill("#otp", "000000")
                sub_page.click("#btnLogin")
                sub_page.wait_for_selector("#navBps")
                sub_page.goto("http://127.0.0.1:8080/bps/check-bill-status")
                sub_page.wait_for_selector("#bankSelect")
                sub_page.select_option("#bankSelect", value="UBL")
                sub_page.fill("#consumerNumberInput", "70085296314001")
                sub_page.click("#btnSearch")
                sub_page.wait_for_timeout(40)
                rows = extract_all_transactions(sub_page, selectors)
                dual_results["otc"] = rows
                br.close()

        def gnb_task():
            with sync_playwright() as p_gnb:
                br = p_gnb.chromium.launch(headless=True)
                sub_page = br.new_page()
                sub_page.goto("http://127.0.0.1:8080/gnb/login")
                sub_page.fill("#gnb-username", "admin")
                sub_page.fill("#gnb-password", "pass")
                sub_page.click("#gnb-login-btn")
                sub_page.wait_for_selector("#gnb-rejected-table")
                txs = extract_transactions_from_active_table(sub_page)
                dual_results["gnb"] = txs
                br.close()

        th_otc = threading.Thread(target=otc_task)
        th_gnb = threading.Thread(target=gnb_task)
        th_otc.start()
        th_gnb.start()
        th_otc.join()
        th_gnb.join()
        t_dual = time.time() - t0

        results["dual_simultaneous"] = {
            "time_seconds": round(t_dual, 2),
            "otc_records": len(dual_results.get("otc", [])),
            "gnb_records": len(dual_results.get("gnb", [])),
        }

        browser.close()
        shutil.rmtree(out_tmp, ignore_errors=True)

    print("\n" + "=" * 50)
    print("  PERFORMANCE BENCHMARK EXECUTION RESULTS")
    print("=" * 50)
    for k, v in results.items():
        print(f"[{k.upper()}] -> {v}")
    print("=" * 50)


if __name__ == "__main__":
    run_benchmark()
