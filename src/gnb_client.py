"""GNB System automation and rejected transaction extraction module.

Runs in an isolated, dedicated worker thread with its own Playwright instance,
preventing cross-thread greenlet context switching errors and ensuring total isolation
from the OTC workflow.
"""

import threading
import time
from typing import Any, Callable, Dict, List, Optional

from playwright.sync_api import BrowserContext, Page, sync_playwright

from src.browser_manager import configure_portable_browsers_path, verify_browser_runtime_available
from src.config import resolve_app_path
from src.logger import get_logger, log_event

# Thread-safe execution lock and persistent lifecycle storage for GNB
_GNB_LOCK = threading.Lock()
_IS_GNB_RUNNING = False

_GNB_THREAD: Optional[threading.Thread] = None
_GNB_PW_INSTANCE: Optional[Any] = None
_GNB_CONTEXT: Optional[BrowserContext] = None
_GNB_PAGE: Optional[Page] = None


def is_gnb_pipeline_active() -> bool:
    """Return whether the GNB extraction pipeline is currently executing."""
    return _IS_GNB_RUNNING


def is_gnb_authenticated(page: Page, selectors: Dict[str, Any]) -> bool:
    """Check if the GNB session is authenticated."""
    auth_selector = (
        selectors.get("login", {}).get("auth_indicator")
        or "#gnb-dashboard, #gnb-user-profile, [data-gnb-authenticated='true'], a[href*='logout'], button:has-text('Logout')"
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
    """Navigate to GNB login page and authenticate if credentials are provided."""
    logger = get_logger("gnb_client")
    login_url = gnb_config.get("login_url", "http://127.0.0.1:8080/")

    if on_message:
        on_message(f"Connecting to GNB System at {login_url}...")
    log_event(logger, 20, f"Connecting to GNB System at {login_url}")

    try:
        page.goto(login_url, wait_until="domcontentloaded", timeout=gnb_config.get("timeout_ms", 30000))
    except Exception as exc:
        log_event(logger, 30, f"Notice navigating to GNB {login_url}: {exc}")

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
    """Navigate to GNB rejected transactions page and extract all records."""
    logger = get_logger("gnb_client")
    configured_rej_url = gnb_config.get("rejected_transactions_url")
    base_url = gnb_config.get("login_url", "http://127.0.0.1:8080/")

    rejected_url = configured_rej_url if configured_rej_url else base_url

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


def _execute_gnb_in_thread(
    config: Dict[str, Any],
    on_message: Optional[Callable[[str], None]] = None,
    keep_browser_open: bool = True,
) -> List[Dict[str, Any]]:
    """Internal execution function strictly owned by the GNB worker thread."""
    global _GNB_PW_INSTANCE, _GNB_CONTEXT, _GNB_PAGE

    logger = get_logger("gnb_client")
    gnb_cfg = config.get("gnb", {})
    selectors = config.get("gnb_selectors", {})
    browser_cfg = config.get("browser", {})

    # Ensure no active asyncio event loop attaches to this clean thread
    import asyncio
    try:
        asyncio.set_event_loop(None)
    except Exception:
        pass

    configure_portable_browsers_path(browser_cfg)
    is_avail, detail = verify_browser_runtime_available(browser_cfg)
    if not is_avail:
        raise RuntimeError(f"GNB browser error: {detail}")

    pw_inst = sync_playwright().start()
    _GNB_PW_INSTANCE = pw_inst

    user_data_path = resolve_app_path(browser_cfg.get("user_data_dir", "checkpoints/browser_profile") + "_gnb")
    user_data_path.mkdir(parents=True, exist_ok=True)

    launch_kwargs: Dict[str, Any] = {
        "user_data_dir": str(user_data_path),
        "headless": browser_cfg.get("headless", False),
        "slow_mo": browser_cfg.get("slow_mo_ms", 100),
        "args": ["--start-maximized"],
        "no_viewport": True,
        "ignore_https_errors": True,
    }
    if browser_cfg.get("channel"):
        launch_kwargs["channel"] = browser_cfg["channel"]
    if browser_cfg.get("executable_path"):
        launch_kwargs["executable_path"] = str(resolve_app_path(browser_cfg["executable_path"]))

    try:
        context = pw_inst.chromium.launch_persistent_context(**launch_kwargs)
        _GNB_CONTEXT = context
        page = context.pages[0] if context.pages else context.new_page()
        _GNB_PAGE = page

        auth_success = login_gnb_portal(page, gnb_cfg, selectors, on_message=on_message)
        if not auth_success:
            log_event(logger, 40, "GNB authentication was not completed.")
            return []

        transactions = extract_gnb_rejected_transactions(page, gnb_cfg, selectors, on_message=on_message)
        return transactions

    finally:
        if not keep_browser_open:
            close_gnb_session()


def close_gnb_session() -> None:
    """Cleanly close GNB browser and context handles."""
    global _GNB_PW_INSTANCE, _GNB_CONTEXT, _GNB_PAGE
    if _GNB_PAGE is not None:
        try:
            if not _GNB_PAGE.is_closed():
                _GNB_PAGE.close()
        except Exception:
            pass
        _GNB_PAGE = None

    if _GNB_CONTEXT is not None:
        try:
            _GNB_CONTEXT.close()
        except Exception:
            pass
        _GNB_CONTEXT = None

    if _GNB_PW_INSTANCE is not None:
        try:
            _GNB_PW_INSTANCE.stop()
        except Exception:
            pass
        _GNB_PW_INSTANCE = None


def run_gnb_extraction_pipeline(
    config: Dict[str, Any],
    on_message: Optional[Callable[[str], None]] = None,
    keep_browser_open: bool = True,
    browser_page: Optional[Page] = None,
) -> List[Dict[str, Any]]:
    """Execute GNB extraction safely in a dedicated worker thread to prevent thread-switching errors.

    Guarantees that only ONE GNB pipeline runs at any given time, preventing duplicate launches.
    """
    global _IS_GNB_RUNNING

    with _GNB_LOCK:
        if _IS_GNB_RUNNING:
            if on_message:
                on_message("GNB extraction is already in progress. Skipping duplicate launch.")
            return []
        _IS_GNB_RUNNING = True

    result_container: List[Any] = []
    error_container: List[Exception] = []

    def thread_entry():
        try:
            res = _execute_gnb_in_thread(config, on_message=on_message, keep_browser_open=keep_browser_open)
            result_container.append(res)
        except Exception as exc:
            error_container.append(exc)
        finally:
            global _IS_GNB_RUNNING
            with _GNB_LOCK:
                _IS_GNB_RUNNING = False

    th = threading.Thread(target=thread_entry, name="GNBWorkerThread", daemon=True)
    th.start()
    th.join()

    if error_container:
        raise error_container[0]

    return result_container[0] if result_container else []
