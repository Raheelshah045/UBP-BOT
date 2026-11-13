"""GNB System automation and rejected transaction extraction module.

Handles independent authentication and extraction of rejected transactions from the GNB system.
Runs independently of the OTC workflow to ensure fault isolation.
"""

import time
from typing import Any, Callable, Dict, List, Optional

from playwright.sync_api import Page

from src.browser_manager import (
    launch_persistent_browser_session,
)
from src.logger import get_logger, log_event


def is_gnb_authenticated(page: Page, selectors: Dict[str, Any]) -> bool:
    """Check if the GNB session is authenticated.

    Args:
        page: Active browser page.
        selectors: GNB selector configuration dictionary.

    Returns:
        bool: True if authentication indicator is detected.
    """
    auth_selector = (
        selectors.get("login", {}).get("auth_indicator")
        or "#gnb-dashboard, #gnb-user-profile, [data-gnb-authenticated='true']"
    )
    for sel in [s.strip() for s in auth_selector.split(",")]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1000):
                return True
        except Exception:
            continue
    return False


def login_gnb_portal(
    page: Page,
    gnb_config: Dict[str, Any],
    selectors: Dict[str, Any],
    on_message: Optional[Callable[[str], None]] = None,
) -> bool:
    """Navigate to GNB login page and authenticate if credentials are provided.

    Args:
        page: Active Playwright page.
        gnb_config: GNB configuration dictionary.
        selectors: GNB selector mappings.
        on_message: Optional UI notification callback.

    Returns:
        bool: True if authenticated successfully.
    """
    logger = get_logger("gnb_client")
    login_url = gnb_config.get("login_url", "http://127.0.0.1:8080/gnb/login")

    if on_message:
        on_message(f"Connecting to GNB System at {login_url}...")
    log_event(logger, 20, f"Connecting to GNB System at {login_url}")

    page.goto(login_url, wait_until="domcontentloaded", timeout=gnb_config.get("timeout_ms", 30000))

    if is_gnb_authenticated(page, selectors):
        if on_message:
            on_message("GNB session already authenticated.")
        return True

    username = gnb_config.get("username", "")
    password = gnb_config.get("password", "")

    login_sels = selectors.get("login", {})
    user_input_sel = login_sels.get(
        "username_input",
        "#gnb-username, input[type='email'], input[name='email'], input[name='username'], #email, #username",
    )
    pwd_input_sel = login_sels.get(
        "password_input",
        "#gnb-password, input[type='password'], input[name='password'], #password",
    )
    submit_btn_sel = login_sels.get(
        "submit_button",
        "#gnb-login-btn, button[type='submit'], input[type='submit'], button:has-text('Log in'), button:has-text('Login'), button:has-text('Sign in')",
    )

    # If credentials are provided in config, auto-fill login
    if username and password:
        try:
            page.locator(user_input_sel).first.fill(username, timeout=5000)
            page.locator(pwd_input_sel).first.fill(password, timeout=5000)
            page.locator(submit_btn_sel).first.click(timeout=5000)
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as exc:
            log_event(logger, 30, f"Automatic GNB login submission failed: {exc}")

    if is_gnb_authenticated(page, selectors):
        if on_message:
            on_message("GNB authentication successful.")
        return True

    # Otherwise, wait for manual authentication (same pattern as OTC)
    if on_message:
        on_message("Please complete GNB login in the browser window...")

    start_time = time.time()
    while time.time() - start_time < 300:
        if is_gnb_authenticated(page, selectors):
            if on_message:
                on_message("GNB authentication detected successfully.")
            return True
        time.sleep(1.0)

    return False


def extract_gnb_rejected_transactions(
    page: Page,
    gnb_config: Dict[str, Any],
    selectors: Dict[str, Any],
    on_message: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, Any]]:
    """Navigate to GNB rejected transactions page and extract all records.

    If rejected_transactions_url is not explicitly configured or is identical/relative
    to the login/base URL, uses the current authenticated page or resolves from base URL.

    Args:
        page: Active Playwright page.
        gnb_config: GNB settings.
        selectors: GNB selector mappings.
        on_message: Optional status callback.

    Returns:
        List[Dict[str, Any]]: Extracted rejected transactions.
    """
    logger = get_logger("gnb_client")
    configured_rej_url = gnb_config.get("rejected_transactions_url")
    base_url = gnb_config.get("login_url", "http://127.0.0.1:8080/")

    # If user provided a specific rejected_transactions_url use it, otherwise stay on / derive from base_url
    if configured_rej_url:
        rejected_url = configured_rej_url
    else:
        # Default to base_url without forcing an obsolete /gnb/rejected-transactions path
        rejected_url = base_url

    # Only navigate if we are not already on the target URL or a subpath of it
    current_url = page.url.rstrip("/")
    target_clean = rejected_url.rstrip("/")
    if target_clean and current_url != target_clean:
        if on_message:
            on_message(f"Navigating to GNB Transactions at {rejected_url}...")
        log_event(logger, 20, f"Navigating to GNB Transactions at {rejected_url}")
        try:
            page.goto(rejected_url, wait_until="domcontentloaded", timeout=gnb_config.get("timeout_ms", 30000))
        except Exception as nav_exc:
            log_event(logger, 30, f"Navigation notice for {rejected_url}: {nav_exc}")
    else:
        if on_message:
            on_message("Inspecting active GNB page for rejected transactions...")

    tx_sels = selectors.get("transactions", {})
    table_sel = tx_sels.get("table", "#gnb-rejected-table, table")
    rows_sel = tx_sels.get("rows", "#gnb-rejected-table tbody tr, table tbody tr")

    try:
        page.wait_for_selector(table_sel, timeout=10000)
    except Exception:
        log_event(logger, 30, "GNB rejected table not found or no records available.")
        return []

    rows = page.locator(rows_sel)
    row_count = rows.count()
    log_event(logger, 20, f"Found {row_count} rows in GNB rejected table.")

    extracted: List[Dict[str, Any]] = []
    for idx in range(row_count):
        row = rows.nth(idx)
        cells = row.locator("td")
        if cells.count() < 4:
            continue

        texts = [cells.nth(i).inner_text().strip() for i in range(cells.count())]

        # Standard GNB table format: [TxID, Account/Consumer, Date/Time, Amount, Status, Reason]
        tx_id = texts[0] if len(texts) > 0 else ""
        account = texts[1] if len(texts) > 1 else ""
        datetime_val = texts[2] if len(texts) > 2 else ""
        amount = texts[3] if len(texts) > 3 else ""
        status = texts[4] if len(texts) > 4 else "Rejected"
        reason = texts[5] if len(texts) > 5 else "Rejected in GNB"

        date_val = ""
        time_val = ""
        if " " in datetime_val:
            parts = datetime_val.split(" ", 1)
            date_val, time_val = parts[0], parts[1]
        else:
            date_val = datetime_val

        extracted.append({
            "transaction_id": tx_id,
            "account_consumer": account,
            "transaction_date": date_val,
            "transaction_time": time_val,
            "amount": amount,
            "status": status,
            "failure_reason": reason,
        })

    if on_message:
        on_message(f"Extracted {len(extracted)} rejected transactions from GNB.")
    log_event(logger, 20, f"Successfully extracted {len(extracted)} GNB rejected transactions.")
    return extracted


def run_gnb_extraction_pipeline(
    config: Dict[str, Any],
    on_message: Optional[Callable[[str], None]] = None,
    keep_browser_open: bool = True,
    browser_page: Optional[Page] = None,
) -> List[Dict[str, Any]]:
    """Execute the end-to-end GNB authentication and rejected transaction extraction pipeline.

    Args:
        config: Full configuration dictionary.
        on_message: Optional UI message hook.
        keep_browser_open: Whether to retain browser window open after run.
        browser_page: Optional explicit dedicated GNB page.

    Returns:
        List[Dict[str, Any]]: Extracted GNB rejected transactions.
    """
    logger = get_logger("gnb_client")
    gnb_cfg = config.get("gnb", {})
    selectors = config.get("gnb_selectors", {})
    browser_cfg = config.get("browser", {})

    page = browser_page
    context = None
    if page is None or page.is_closed():
        login_url = gnb_cfg.get("login_url", "http://127.0.0.1:8080/gnb/login")
        _, context, page = launch_persistent_browser_session(browser_cfg, initial_url=login_url, system_name="gnb")

    auth_success = login_gnb_portal(page, gnb_cfg, selectors, on_message=on_message)
    if not auth_success:
        log_event(logger, 40, "GNB authentication was not completed.")
        return []

    transactions = extract_gnb_rejected_transactions(page, gnb_cfg, selectors, on_message=on_message)

    if not keep_browser_open and context is not None:
        try:
            context.close()
        except Exception:
            pass

    return transactions
