"""OTC (Over-The-Counter) BPS Client and Automation Module for UBP Bot.

Provides complete functionality for:
- Manual login authentication detection and session monitoring
- Screen detection and navigation to BPS Check Bill Status
- Bank selection, consumer number entry, and date parameterization
- Table extraction with adaptive pagination
- Transaction classification with strict exclusion of rejection codes 95 and 98
"""

import time
from urllib.parse import urlparse
from typing import Any, Callable, Dict, List, Optional

from playwright.sync_api import Page

# =========================================================================
# Classification Rules (Strict Exclusion of Codes 95 & 98)
# =========================================================================

DEFAULT_EXCLUDED_CODES = ["95", "98"]
DEFAULT_APPROVED_CODES = ["00"]
DEFAULT_APPROVED_STATUSES = ["APPROVED", "SUCCESSFUL"]
DEFAULT_REJECTED_STATUSES = [
    "REJECTED",
    "REJECT",
    "DECLINED",
    "DECLINE",
    "FAILED",
    "FAIL",
    "UNSUCCESSFUL",
]
DEFAULT_PENDING_STATUSES = ["PENDING"]


def normalize_token(value: Any) -> str:
    """Normalize a string or numeric value by trimming and converting to uppercase."""
    if value is None:
        return ""
    return str(value).strip().upper()


def classify_transaction(
    status: str, response_code: str, rules_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Classify a single transaction record based on status and response code.

    Strict Business Rule: Response codes 95 and 98 are strictly excluded from
    qualifying rejections.

    Args:
        status: The raw transaction status string from the portal.
        response_code: The raw response code string from the portal.
        rules_config: Optional custom rules dictionary.

    Returns:
        Dict[str, Any]: Classification details including category and qualification flags.
    """
    clean_status = normalize_token(status)
    clean_code = normalize_token(response_code)

    excluded_codes = (
        rules_config.get("excluded_rejection_codes", DEFAULT_EXCLUDED_CODES)
        if rules_config
        else DEFAULT_EXCLUDED_CODES
    )
    excluded_codes = [normalize_token(c) for c in excluded_codes]

    approved_statuses = (
        rules_config.get("approved_status_keywords", DEFAULT_APPROVED_STATUSES)
        if rules_config
        else DEFAULT_APPROVED_STATUSES
    )
    approved_statuses = [normalize_token(s) for s in approved_statuses]

    pending_statuses = (
        rules_config.get("pending_status_keywords", DEFAULT_PENDING_STATUSES)
        if rules_config
        else DEFAULT_PENDING_STATUSES
    )
    pending_statuses = [normalize_token(s) for s in pending_statuses]

    # Rule 1: Exclusion of 95 and 98
    if clean_code in excluded_codes:
        return {
            "classification": "Excluded Rejection",
            "is_qualifying_rejection": False,
            "reason": f"Excluded response code {clean_code}",
        }

    # Rule 2: Approved / Successful transactions
    if clean_code in DEFAULT_APPROVED_CODES or any(app_s in clean_status for app_s in approved_statuses):
        return {
            "classification": "Approved",
            "is_qualifying_rejection": False,
            "reason": f"Approved status '{status}' / Code '{clean_code}'",
        }

    # Rule 3: Pending transactions
    if any(pnd_s in clean_status for pnd_s in pending_statuses):
        return {
            "classification": "Pending",
            "is_qualifying_rejection": False,
            "reason": f"Pending status '{status}'",
        }

    # Rule 4: Qualifying Rejected
    is_rejected_status = any(rej_s in clean_status for rej_s in DEFAULT_REJECTED_STATUSES)
    is_non_approved_code = bool(clean_code and clean_code not in DEFAULT_APPROVED_CODES)

    if is_rejected_status or is_non_approved_code:
        return {
            "classification": "Rejected",
            "is_qualifying_rejection": True,
            "reason": f"Qualifying rejection with code '{clean_code}'",
        }

    return {
        "classification": "Unknown",
        "is_qualifying_rejection": False,
        "reason": f"Unrecognized status '{status}' and code '{clean_code}'",
    }


# =========================================================================
# State Detection & Session Monitoring
# =========================================================================

STATE_LOGIN = "LOGIN"
STATE_AUTHENTICATED = "AUTHENTICATED"
STATE_CHECK_BILL = "CHECK_BILL"
STATE_SESSION_EXPIRED = "SESSION_EXPIRED"
STATE_UNKNOWN = "UNKNOWN"


def is_check_bill_screen_present(page: Page) -> bool:
    """Verify if the Check Bill Status search form is actively visible."""
    if not page or page.is_closed():
        return False

    form_selectors = [
        "#bankSelect",
        "#consumerNumberInput",
        "select[name*='bank' i]",
        "input[placeholder*='consumer' i]",
        "input[id*='consumer' i]",
        "button:has-text('Search')",
        "#btnSearch",
    ]
    for sel in form_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=250):
                return True
        except Exception:
            continue
    return False


def is_portal_authenticated(page: Page, selectors: Dict[str, Any]) -> bool:
    """Check if the user is authenticated in the OTC portal."""
    if not page or page.is_closed():
        return False

    auth_indicators = [
        selectors.get("login", {}).get("auth_indicator"),
        "#userProfile",
        "[data-testid='user-profile']",
        "#user-profile",
        ".user-profile",
        "a[href*='logout' i]",
        "button:has-text('Logout')",
        "button:has-text('Sign Out')",
        "#navBps",
        "#nav-bps",
    ]
    for sel in auth_indicators:
        if not sel:
            continue
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=250):
                return True
        except Exception:
            continue
    return False


def is_login_screen_present(page: Page, selectors: Dict[str, Any]) -> bool:
    """Check if the login form is currently visible."""
    if not page or page.is_closed():
        return False

    login_indicators = [
        "#username",
        "#password",
        "input[type='password']",
        "button:has-text('Login')",
        "button:has-text('Sign In')",
        "#btnLogin",
    ]
    for sel in login_indicators:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=250):
                return True
        except Exception:
            continue
    return False


def check_is_session_expired(page: Page, selectors: Dict[str, Any]) -> bool:
    """Check if the session has expired or been kicked back to login."""
    if not page or page.is_closed():
        return False

    expired_sel = selectors.get("login", {}).get("session_expired_indicator", "#sessionExpiredAlert")
    try:
        if page.locator(expired_sel).first.is_visible(timeout=200):
            return True
    except Exception:
        pass

    if is_login_screen_present(page, selectors) and not is_check_bill_screen_present(page):
        return True

    return False


def detect_portal_state(page: Page, selectors: Dict[str, Any]) -> str:
    """Detect current high-level portal state."""
    if not page or page.is_closed():
        return STATE_UNKNOWN

    if is_check_bill_screen_present(page):
        return STATE_CHECK_BILL
    if check_is_session_expired(page, selectors):
        return STATE_SESSION_EXPIRED
    if is_portal_authenticated(page, selectors):
        return STATE_AUTHENTICATED
    if is_login_screen_present(page, selectors):
        return STATE_LOGIN

    return STATE_UNKNOWN


def check_is_authenticated(page: Page, selectors: Dict[str, Any]) -> bool:
    """Check if the current browser page presents an authenticated state."""
    return is_portal_authenticated(page, selectors)


def ensure_portal_authenticated(
    page: Page,
    login_url: str,
    check_bill_url: Optional[str] = None,
    selectors: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 300,
    on_message_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """Wait for manual authentication and verify the BPS search screen is ready."""
    sel = selectors or {}

    def notify(message: str) -> None:
        if on_message_callback:
            on_message_callback(message)

    if not page or page.is_closed():
        notify("OTC browser page is unavailable; authentication cannot continue.")
        return False

    target_host = (urlparse(login_url).hostname or "").lower()
    current_host = (urlparse(page.url).hostname or "").lower()
    if not page.url or page.url in ("about:blank", "") or current_host != target_host:
        notify(f"Opening configured OTC portal: {login_url}")
        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            notify(f"OTC portal navigation failed: {type(exc).__name__}: {exc}")
            return False

    if is_check_bill_screen_present(page):
        notify("OTC Check Bill Status screen is ready.")
        return True

    notify("Waiting for manual OTC credentials, CAPTCHA, and OTP completion...")
    start_time = time.monotonic()
    next_status_log = start_time + 10
    navigation_attempted = False
    last_navigation_attempt = 0.0

    while time.monotonic() - start_time < max(1, timeout_seconds):
        if page.is_closed():
            notify("OTC browser page closed while waiting for authentication.")
            return False

        if is_check_bill_screen_present(page):
            notify("OTC authentication and Check Bill Status readiness confirmed.")
            return True

        if is_portal_authenticated(page, sel):
            now = time.monotonic()
            if not navigation_attempted or now - last_navigation_attempt >= 3:
                notify("OTC login detected; opening Check Bill Status...")
                navigation_attempted = True
                last_navigation_attempt = now
                if navigate_to_check_bill_status(
                    page, sel, check_bill_url, on_message=on_message_callback
                ) and is_check_bill_screen_present(page):
                    notify("OTC Check Bill Status screen is ready.")
                    return True
                notify(
                    "OTC session is authenticated, but Check Bill Status is not ready yet; retrying."
                )

        now = time.monotonic()
        if now >= next_status_log:
            notify(f"Still waiting for OTC portal readiness ({int(now - start_time)}s elapsed).")
            next_status_log = now + 10

        time.sleep(0.5)

    notify(
        f"OTC authentication/readiness timed out after {timeout_seconds}s. "
        f"Current URL: {page.url}"
    )
    return False

# =========================================================================
# Navigation to Check Bill Status
# =========================================================================

def navigate_to_check_bill_status(
    page: Page,
    selectors: Dict[str, Any],
    direct_url: Optional[str] = None,
    on_message: Optional[Callable[[str], None]] = None,
) -> bool:
    """Navigate dynamically to BPS -> Check Bill Status without destructive page reloads."""
    if not page or page.is_closed():
        return False

    if is_check_bill_screen_present(page):
        return True

    # Check direct navigation button
    direct_buttons = [
        "#btn-goto-check-bill-status",
        "[data-testid='btn-goto-check-bill-status']",
        "button:has-text('Check Bill Status')",
        "a:has-text('Check Bill Status')",
        "#navCheckBillStatus",
    ]
    for btn_sel in direct_buttons:
        try:
            loc = page.locator(btn_sel).first
            if loc.is_visible(timeout=300):
                loc.click()
                time.sleep(0.5)
                if is_check_bill_screen_present(page):
                    return True
        except Exception:
            continue

    # Try expandable BPS menu
    bps_triggers = ["#navBps", "#nav-bps", "a:has-text('BPS')", "button:has-text('BPS')"]
    for trig in bps_triggers:
        try:
            loc = page.locator(trig).first
            if loc.is_visible(timeout=300):
                loc.click()
                time.sleep(0.4)
                break
        except Exception:
            continue

    for btn_sel in direct_buttons:
        try:
            loc = page.locator(btn_sel).first
            if loc.is_visible(timeout=300):
                loc.click()
                time.sleep(0.5)
                if is_check_bill_screen_present(page):
                    return True
        except Exception:
            continue

    if direct_url:
        try:
            page.goto(direct_url, wait_until="domcontentloaded", timeout=30000)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if is_check_bill_screen_present(page):
                    return True
                time.sleep(0.25)
        except Exception as exc:
            if on_message:
                on_message(f"OTC direct navigation failed: {type(exc).__name__}: {exc}")

    ready = is_check_bill_screen_present(page)
    if not ready and on_message:
        on_message(
            "OTC navigation did not reach Check Bill Status. "
            f"Current URL: {page.url}"
        )
    return ready


# =========================================================================
# Search Execution
# =========================================================================

def resolve_bank_option_value(
    bank_name: str, bank_mapping: Dict[str, str], available_options: Dict[str, str]
) -> Optional[str]:
    """Match bank name to dropdown option value."""
    clean_target = bank_name.strip().upper()

    for val in available_options:
        if val.strip().upper() == clean_target:
            return val

    for val in available_options:
        if clean_target in val.strip().upper() or val.strip().upper() in clean_target:
            return val

    for val, text in available_options.items():
        t_upper = text.strip().upper()
        if clean_target == t_upper or f" {clean_target} " in f" {t_upper} " or f"({clean_target})" in t_upper:
            return val

    mapped_name = bank_mapping.get(clean_target, "").strip().upper()
    if mapped_name:
        for val, text in available_options.items():
            t_upper = text.strip().upper()
            if mapped_name in t_upper or t_upper in mapped_name:
                return val

    return None


def execute_transaction_search(
    page: Page,
    selectors: Dict[str, Any],
    bank_name: str,
    consumer_number: str,
    search_date: Optional[str] = None,
    bank_mapping: Optional[Dict[str, str]] = None,
    on_message: Optional[Callable[[str], None]] = None,
) -> bool:
    """Execute search query for a consumer number and bank in the portal."""
    if not page or page.is_closed():
        return False

    b_mapping = bank_mapping or {}

    # 1. Bank Selection
    bank_select = page.locator("#bankSelect, select[name*='bank' i]").first
    if bank_select.is_visible(timeout=1000):
        # Extract available options
        options = bank_select.locator("option").all()
        opts_dict = {}
        for opt in options:
            val = opt.get_attribute("value") or ""
            txt = opt.inner_text() or ""
            if val:
                opts_dict[val] = txt

        resolved_val = resolve_bank_option_value(bank_name, b_mapping, opts_dict)
        if resolved_val:
            bank_select.select_option(value=resolved_val)
        else:
            try:
                bank_select.select_option(label=bank_name)
            except Exception:
                pass

    # 2. Consumer Number Entry
    consumer_input = page.locator("#consumerNumberInput, input[id*='consumer' i], input[name*='consumer' i]").first
    if consumer_input.is_visible(timeout=1000):
        consumer_input.fill(consumer_number)

    # 3. Date Entry (if date inputs exist)
    if search_date:
        for date_sel in ["#fromDateInput", "#from_date", "input[name*='from' i]"]:
            loc = page.locator(date_sel).first
            try:
                if loc.is_visible(timeout=200):
                    loc.fill(search_date)
            except Exception:
                pass
        for date_sel in ["#toDateInput", "#to_date", "input[name*='to' i]"]:
            loc = page.locator(date_sel).first
            try:
                if loc.is_visible(timeout=200):
                    loc.fill(search_date)
            except Exception:
                pass

    # 4. Click Search or Press Enter
    search_btn = page.locator("#btnSearch, button:has-text('Search'), input[type='submit']").first
    if search_btn.is_visible(timeout=500):
        search_btn.click()
    else:
        consumer_input.press("Enter")

    # 5. Wait for loading spinner to resolve or results table to appear
    spinner = page.locator("#loadingSpinner, [data-testid='spinner'], .spinner").first
    try:
        if spinner.is_visible(timeout=300):
            spinner.wait_for(state="hidden", timeout=15000)
    except Exception:
        pass

    time.sleep(0.4)
    return True


# =========================================================================
# Table Extraction & Pagination
# =========================================================================

def extract_all_transactions(
    page: Page, selectors: Dict[str, Any], max_pages: int = 10
) -> List[Dict[str, Any]]:
    """Extract tabular results across all available pagination pages."""
    if not page or page.is_closed():
        return []

    extracted: List[Dict[str, Any]] = []
    seen_rows = set()

    for _ in range(max_pages):
        table = page.locator("#transactionsTable, table").first
        try:
            if not table.is_visible(timeout=800):
                break
        except Exception:
            break

        rows = table.locator("tbody tr").all()
        for row in rows:
            tds = row.locator("td").all()
            if not tds or len(tds) < 3:
                continue

            vals = [td.inner_text().strip() for td in tds]
            row_key = "|".join(vals)
            if row_key in seen_rows:
                continue
            seen_rows.add(row_key)

            # Map typical BPS table columns
            # [Sr, Consumer, Date, Time, RRN, AuthID, Amount, Status, Code, Desc]
            tx_data: Dict[str, Any] = {
                "raw_columns": vals,
                "consumer_number": vals[1] if len(vals) > 1 else "",
                "transaction_date": vals[2] if len(vals) > 2 else "",
                "transaction_time": vals[3] if len(vals) > 3 else "",
                "rrn": vals[4] if len(vals) > 4 else "",
                "auth_id": vals[5] if len(vals) > 5 else "",
                "amount": vals[6] if len(vals) > 6 else "",
                "status": vals[7] if len(vals) > 7 else (vals[-2] if len(vals) >= 2 else ""),
                "response_code": vals[8] if len(vals) > 8 else (vals[-1] if len(vals) >= 1 else ""),
                "response_description": vals[9] if len(vals) > 9 else "",
            }
            extracted.append(tx_data)

        # Check pagination
        next_btn = page.locator("#btnNextPage, button:has-text('Next'), a:has-text('Next')").first
        try:
            if next_btn.is_visible(timeout=250) and next_btn.is_enabled():
                next_btn.click()
                time.sleep(0.4)
            else:
                break
        except Exception:
            break

    return extracted
