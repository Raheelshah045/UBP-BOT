"""Table data extraction module for portal transaction results.

Extracts all records across single or multi-page results tables with dynamic column
mapping, header inspection, value pattern inference, data-testid support, and pagination traversal.
"""

import re
import time
from typing import Any, Dict, List, Optional

from playwright.sync_api import Locator, Page


def check_is_no_record_found(page: Page, selectors: Dict[str, Any]) -> bool:
    """Check if the results view indicates that no records were found.

    Args:
        page: Active Playwright page.
        selectors: Portal selector configuration.

    Returns:
        bool: True if 'no records found' alert is currently visible.
    """
    no_rec_sel = selectors.get("results", {}).get(
        "no_record_message",
        "#no-records-message, #noRecordsAlert, [data-testid='no-records-message']",
    )
    try:
        loc = page.locator(no_rec_sel)
        if loc.count() > 0 and loc.first.is_visible(timeout=300):
            return True
        # Check text pattern if specific element not found
        text_loc = page.locator("text=/No records? found/i")
        return text_loc.count() > 0 and text_loc.first.is_visible(timeout=300)
    except Exception:
        return False


def find_results_table(page: Page) -> Optional[Locator]:
    """Locate the visible transactions table adaptively.

    Args:
        page: Active Playwright page.

    Returns:
        Optional[Locator]: Visible table locator, or None.
    """
    candidates = [
        "#transactions-table",
        "[data-testid='transactions-table']",
        "#transactionsTable",
        "table:has(tbody tr)",
        "table:has(tr)",
        "table",
    ]
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=400):
                return loc
        except Exception:
            continue
    return None


def detect_column_mapping(table: Locator) -> Dict[str, int]:
    """Inspect table headers across thead th, tr th, or first row td to determine column indices.

    Resilient to header renaming, case differences, punctuation, and extra columns.

    Args:
        table: Active table Locator.

    Returns:
        Dict[str, int]: Map of logical field names to zero-based column indices.
    """
    col_map: Dict[str, int] = {}
    header_locs = table.locator("thead th").all()
    if not header_locs:
        header_locs = table.locator("tr th").all()
    if not header_locs:
        first_row = table.locator("tr").first
        if first_row.count() > 0:
            header_locs = first_row.locator("td").all()

    headers = [th.inner_text().strip().lower() for th in header_locs]

    for idx, raw_h in enumerate(headers):
        h = raw_h.replace(".", " ").replace("_", " ").replace("/", " ").replace("-", " ")
        words = h.split()

        # Consumer Number
        if any(w in ("consumer", "account", "customerno", "consumerno") for w in words) or "consumer" in h:
            col_map["consumer"] = idx
        # Bank / Service
        elif any(w in ("bank", "biller", "service", "institution", "company") for w in words) or "bank" in h:
            col_map["bank"] = idx
        # Transaction Date
        elif "date" in words or "date" in h:
            col_map["date"] = idx
        # Transaction Time
        elif "time" in words or "time" in h:
            col_map["time"] = idx
        # RRN
        elif "rrn" in words or "rrn" in h or "reference" in words:
            col_map["rrn"] = idx
        # Authorization ID
        elif "auth" in words or "auth" in h or "approval" in words:
            col_map["auth"] = idx
        # Amount
        elif any(w in ("amount", "pkr", "paid", "total") for w in words) or "amount" in h:
            col_map["amount"] = idx
        # Status
        elif any(w in ("status", "result", "state") for w in words) or "status" in h:
            col_map["status"] = idx
        # Response Code
        elif any(w in ("code", "rc", "responsecode") for w in words) or "code" in h:
            col_map["code"] = idx
        # Response Description
        elif any(w in ("desc", "description", "narration", "reason", "message", "remarks") for w in words) or "desc" in h:
            col_map["desc"] = idx

    return col_map


def infer_columns_from_cell_values(cell_texts: List[str]) -> Dict[str, int]:
    """Infer column roles by inspecting the string formatting and patterns of cell values.

    Acts as a safety net when table headers are missing, obfuscated, or custom-styled.

    Args:
        cell_texts: List of text strings extracted from a single data row.

    Returns:
        Dict[str, int]: Inferred mapping of field names to column indices.
    """
    inferred: Dict[str, int] = {}
    date_regex = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}$|^\d{2}[-/]\d{2}[-/]\d{4}$")
    time_regex = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")
    amount_regex = re.compile(r"^[\d,]+\.\d{2}$")
    status_keywords = {"APPROVED", "SUCCESSFUL", "REJECTED", "PENDING", "FAILED", "SUCCESS"}
    code_regex = re.compile(r"^[0-9A-Z]{2,3}$")

    for idx, txt in enumerate(cell_texts):
        cleaned = txt.strip()
        upper = cleaned.upper()

        if upper in status_keywords and "status" not in inferred:
            inferred["status"] = idx
        elif date_regex.match(cleaned) and "date" not in inferred:
            inferred["date"] = idx
        elif time_regex.match(cleaned) and "time" not in inferred:
            inferred["time"] = idx
        elif amount_regex.match(cleaned) and "amount" not in inferred:
            inferred["amount"] = idx
        elif code_regex.match(cleaned) and len(cleaned) <= 3 and "code" not in inferred:
            inferred["code"] = idx
        elif len(cleaned) >= 10 and cleaned.isdigit() and "consumer" not in inferred:
            inferred["consumer"] = idx
        elif len(cleaned) == 12 and cleaned.isdigit() and "rrn" not in inferred:
            inferred["rrn"] = idx

    return inferred


def extract_current_page_rows(page: Page, selectors: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse table rows currently rendered on the page into transaction dictionaries.

    Uses header name mapping, data-testid attributes, and value-based inference to ensure
    perfect alignment regardless of table column variations or layout shifts.

    Args:
        page: Active Playwright page.
        selectors: Portal selector configuration.

    Returns:
        List[Dict[str, Any]]: List of parsed transaction rows.
    """
    table = find_results_table(page)
    if not table:
        return []

    col_map = detect_column_mapping(table)

    rows = table.locator("tbody tr")
    if rows.count() == 0:
        rows = table.locator("tr:has(td)")

    row_count = rows.count()
    results: List[Dict[str, Any]] = []

    # Optional header locs for offset calculation
    header_locs = table.locator("thead th").all()
    headers = [th.inner_text().strip().lower() for th in header_locs]

    for i in range(row_count):
        row_el = rows.nth(i)
        cells = row_el.locator("td")
        c_count = cells.count()
        if c_count < 3:
            continue

        cell_texts = [cells.nth(c).inner_text().strip() for c in range(c_count)]

        # If key columns missing from header map, try value inference on this row
        row_inferred = infer_columns_from_cell_values(cell_texts)

        def get_val(key: str, default_idx: int) -> str:
            # 1. Check data-testid attribute on cell
            testid_map = {
                "consumer": "cell-consumer-number",
                "bank": "cell-biller",
                "date": "cell-date",
                "time": "cell-time",
                "rrn": "cell-rrn",
                "auth": "cell-auth-id",
                "amount": "cell-amount",
                "status": "cell-status-badge",
                "code": "cell-response-code",
                "desc": "cell-response-description",
            }
            tid = testid_map.get(key)
            if tid:
                cell_loc = row_el.locator(f"[data-testid='{tid}']")
                if cell_loc.count() > 0:
                    return cell_loc.first.inner_text().strip()

            # 2. Check detected header index
            if key in col_map and col_map[key] < c_count:
                return cell_texts[col_map[key]]

            # 3. Check value-inferred index
            if key in row_inferred and row_inferred[key] < c_count:
                return cell_texts[row_inferred[key]]

            # 4. Fallback to default positional index
            if default_idx < c_count:
                return cell_texts[default_idx]
            return ""

        # Default fallback indices depend on whether Sr. No. is column 0
        has_sr_no = "sr" in headers[0] if headers else (c_count >= 11)
        offset = 1 if has_sr_no else 0

        consumer_num = get_val("consumer", offset + 0)
        bank_service = get_val("bank", offset + 1)
        tx_date = get_val("date", offset + 2)
        tx_time = get_val("time", offset + 3)
        rrn = get_val("rrn", offset + 4) or f"RRN_{i + 1}"
        auth_id = get_val("auth", offset + 5) or f"AUTH_{i + 1}"
        amount = get_val("amount", offset + 6)
        status = get_val("status", offset + 7)
        resp_code = get_val("code", offset + 8)
        resp_desc = get_val("desc", offset + 9)

        results.append(
            {
                "consumer_number": consumer_num,
                "bank_service": bank_service,
                "transaction_date": tx_date,
                "transaction_time": tx_time,
                "rrn": rrn,
                "auth_id": auth_id,
                "amount": amount,
                "status": status,
                "response_code": resp_code,
                "response_description": resp_desc,
            }
        )

    return results


def has_next_page(page: Page, selectors: Dict[str, Any]) -> bool:
    """Check if pagination has an active, clickable Next button.

    Args:
        page: Active Playwright page.
        selectors: Portal selector configuration.

    Returns:
        bool: True if Next button exists and is not disabled.
    """
    next_selectors = [
        "#btn-page-next",
        "[data-testid='btn-page-next']",
        selectors.get("results", {}).get("pagination_next", "#btnNextPage"),
        "button:has-text('Next')",
        "button:has-text('›')",
        "a:has-text('Next')",
        "[aria-label*='next' i]",
        "#btnNextPage",
    ]
    for sel in next_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=300):
                is_disabled = (
                    loc.is_disabled()
                    or "disabled" in (loc.get_attribute("class") or "")
                    or loc.get_attribute("aria-disabled") == "true"
                )
                return not is_disabled
        except Exception:
            continue
    return False


def click_next_page(page: Page, selectors: Dict[str, Any]) -> bool:
    """Click pagination Next button and wait for refreshed table data.

    Args:
        page: Active Playwright page.
        selectors: Portal selector configuration.

    Returns:
        bool: True if next page loaded successfully.
    """
    next_selectors = [
        "#btn-page-next",
        "[data-testid='btn-page-next']",
        selectors.get("results", {}).get("pagination_next", "#btnNextPage"),
        "button:has-text('Next')",
        "a:has-text('Next')",
        "#btnNextPage",
    ]
    for sel in next_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=300) and not loc.is_disabled():
                loc.click()
                time.sleep(0.5)
                # Wait for any spinner to disappear
                loading_sel = selectors.get("results", {}).get(
                    "loading_indicator", "#loading-spinner, #loading-indicator, #loadingSpinner, .spinner"
                )
                try:
                    if page.locator(loading_sel).first.is_visible(timeout=300):
                        page.wait_for_selector(f"{loading_sel}:not(:visible)", timeout=10000)
                except Exception:
                    pass
                return True
        except Exception:
            continue
    return False


def extract_all_transactions(
    page: Page, selectors: Dict[str, Any], max_pages: int = 50
) -> List[Dict[str, Any]]:
    """Traverse all pagination pages and extract complete transaction records.

    Args:
        page: Active Playwright page.
        selectors: Portal selector configuration.
        max_pages: Safeguard maximum pagination depth.

    Returns:
        List[Dict[str, Any]]: Aggregated transactions across all result pages.
    """
    if check_is_no_record_found(page, selectors):
        return []

    all_records: List[Dict[str, Any]] = []
    seen_keys = set()
    current_page = 1

    while current_page <= max_pages:
        page_records = extract_current_page_rows(page, selectors)
        if not page_records:
            break

        new_on_this_page = 0
        for rec in page_records:
            unique_key = (
                rec.get("consumer_number", ""),
                rec.get("rrn", ""),
                rec.get("transaction_date", ""),
                rec.get("transaction_time", ""),
            )
            if unique_key not in seen_keys:
                seen_keys.add(unique_key)
                all_records.append(rec)
                new_on_this_page += 1

        if new_on_this_page == 0 or not has_next_page(page, selectors):
            break

        if not click_next_page(page, selectors):
            break

        current_page += 1

    return all_records
