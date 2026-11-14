"""GNB System automation and rejected transaction extraction module.

Runs in an isolated, dedicated worker thread with its own Playwright instance,
preventing cross-thread greenlet context switching errors and ensuring total isolation
from the OTC workflow.
"""

import threading
import time
from pathlib import Path
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


def extract_transaction_ids_from_file(file_path: Path) -> List[str]:
    """Read a spreadsheet file and return all Transaction IDs as clean strings.

    Args:
        file_path: Path to Excel or CSV file.

    Returns:
        List[str]: Clean Transaction ID strings.
    """
    from src.input_processor import read_raw_dataframe

    df = read_raw_dataframe(file_path)
    id_col = None
    for col in df.columns:
        clean = str(col).strip().lower()
        if any(k in clean for k in ["transaction id", "tran id", "tran_id", "tranid"]):
            id_col = col
            break

    if id_col is None:
        return []

    return [str(val).strip() for val in df[id_col].dropna().tolist() if str(val).strip()]


def map_gnb_table_headers(headers: List[str]) -> Dict[str, int]:
    """Map GNB table headers to field keys dynamically.

    Args:
        headers: List of lowercased header names.

    Returns:
        Dict[str, int]: Mapping of field names to column indices.
    """
    mapping: Dict[str, int] = {}
    for idx, raw_h in enumerate(headers):
        h = raw_h.strip().lower()
        if any(k in h for k in ["tran id", "tran_id", "transaction id", "transaction_id", "tx id"]):
            mapping["tx_id"] = idx
        elif "stan" in h:
            mapping["stan"] = idx
        elif any(k in h for k in ["date & time", "datetime", "date/time"]):
            mapping["datetime"] = idx
        elif "date" in h:
            mapping["date"] = idx
        elif "time" in h:
            mapping["time"] = idx
        elif "status" in h:
            mapping["status"] = idx
        elif "amount" in h:
            mapping["amount"] = idx
        elif any(k in h for k in ["consumer", "account", "from acct"]):
            if "account" not in mapping:
                mapping["account"] = idx
        elif any(k in h for k in ["type", "tran_type"]):
            mapping["type"] = idx
        elif any(k in h for k in ["reason", "failure reason"]):
            mapping["reason"] = idx
    return mapping


def parse_single_gnb_row(
    texts: List[str], mapping: Dict[str, int]
) -> Optional[Dict[str, Any]]:
    """Parse a single table row text array into a transaction dictionary.

    Args:
        texts: Cell text values from table row.
        mapping: Header index mapping.

    Returns:
        Optional[Dict[str, Any]]: Extracted transaction if qualifying, else None.
    """
    if len(texts) < 4:
        return None

    row_str = " ".join(texts).lower()
    if "enter a transaction id" in row_str or "no records found" in row_str:
        return None

    tx_idx = mapping.get("tx_id", 0 if len(texts) < 10 else 1)
    status_idx = mapping.get("status", 4 if len(texts) < 10 else 5)
    acct_idx = mapping.get("account", 1 if len(texts) < 10 else 8)
    date_idx = mapping.get("date", 2 if len(texts) < 10 else 3)
    time_idx = mapping.get("time", 2 if len(texts) < 10 else 4)
    amt_idx = mapping.get("amount", 3 if len(texts) < 10 else 12)
    reason_idx = mapping.get("reason")
    type_idx = mapping.get("type", 0)

    tx_id = texts[tx_idx] if tx_idx < len(texts) else ""
    status = texts[status_idx] if status_idx < len(texts) else ""

    if status.upper() not in ["FAILED", "REJECTED"]:
        return None

    date_val = texts[date_idx] if date_idx < len(texts) else ""
    time_val = texts[time_idx] if time_idx < len(texts) else ""
    if mapping.get("datetime") and " " in date_val:
        parts = date_val.split(" ", 1)
        date_val, time_val = parts[0], parts[1]

    amount_val = texts[amt_idx] if amt_idx < len(texts) else ""
    acct_val = texts[acct_idx] if acct_idx < len(texts) else ""

    if reason_idx is not None and reason_idx < len(texts):
        reason_val = texts[reason_idx]
    elif type_idx < len(texts) and texts[type_idx]:
        reason_val = f"Transaction Failed ({texts[type_idx]})"
    else:
        reason_val = "Rejected in GNB"

    return {
        "transaction_id": tx_id,
        "account_consumer": acct_val,
        "transaction_date": date_val,
        "transaction_time": time_val,
        "amount": amount_val,
        "status": status,
        "failure_reason": reason_val,
    }


def extract_transactions_from_active_table(page: Page) -> List[Dict[str, Any]]:
    """Extract all qualifying rejected transactions from the currently rendered table.

    Args:
        page: Active Playwright page.

    Returns:
        List[Dict[str, Any]]: List of rejected transaction dictionaries.
    """
    rows = page.locator("table tbody tr")
    row_count = rows.count()
    if row_count == 0:
        return []

    ths = page.locator("table thead th").all()
    headers = [th.inner_text().strip().lower() for th in ths]
    mapping = map_gnb_table_headers(headers)

    results: List[Dict[str, Any]] = []
    for idx in range(row_count):
        row = rows.nth(idx)
        cells = row.locator("td")
        if cells.count() < 4:
            continue
        texts = [cells.nth(i).inner_text().strip() for i in range(cells.count())]
        parsed = parse_single_gnb_row(texts, mapping)
        if parsed:
            results.append(parsed)
    return results


def query_single_gnb_transaction(page: Page, tx_id: str) -> List[Dict[str, Any]]:
    """Submit a single Transaction ID in GNB and extract table rows.

    Args:
        page: Active Playwright page.
        tx_id: Clean Transaction ID.

    Returns:
        List[Dict[str, Any]]: Extracted rejected transactions, if any.
    """
    page.locator("#transactionId, input[name='transactionId']").first.fill(tx_id)
    page.locator("#searchBtn, button:has-text('Search')").first.click()
    page.wait_for_timeout(350)
    return extract_transactions_from_active_table(page)


def search_gnb_by_transaction_ids(
    page: Page,
    tx_ids: List[str],
    on_message: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, Any]]:
    """Search GNB portal sequentially for each transaction ID in input list.

    Args:
        page: Active Playwright page.
        tx_ids: List of transaction ID strings.
        on_message: Optional UI message callback.

    Returns:
        List[Dict[str, Any]]: Extracted rejected transactions.
    """
    extracted: List[Dict[str, Any]] = []
    total = len(tx_ids)

    try:
        page.locator("#fromDate").first.fill("")
        page.locator("#toDate").first.fill("")
    except Exception:
        pass

    for idx, tx_id in enumerate(tx_ids, 1):
        clean_id = str(tx_id).strip()
        if not clean_id:
            continue
        try:
            tx_rows = query_single_gnb_transaction(page, clean_id)
            if tx_rows:
                extracted.extend(tx_rows)
                msg = f"[{idx}/{total}] Tx ID {clean_id}: REJECTED/FAILED -> Extracted"
            else:
                msg = f"[{idx}/{total}] Tx ID {clean_id}: Verified (Approved/Pending/None)"
            if on_message:
                on_message(msg)
        except Exception as exc:
            if on_message:
                on_message(f"[{idx}/{total}] Error querying Tx ID {clean_id}: {exc}")

    return extracted


def search_gnb_general_date_range(
    page: Page,
    on_message: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, Any]]:
    """Perform a broad search on GNB portal when no specific input file is provided.

    Args:
        page: Active Playwright page.
        on_message: Optional UI message callback.

    Returns:
        List[Dict[str, Any]]: Extracted rejected transactions.
    """
    search_input = page.locator("#transactionId, input[name='transactionId']").first
    from_date_input = page.locator("#fromDate, input[name='fromDate']").first
    to_date_input = page.locator("#toDate, input[name='toDate']").first
    search_btn = page.locator("#searchBtn, button:has-text('Search')").first

    try:
        if from_date_input.is_visible(timeout=1000):
            from_date_input.fill("2026-01-01")
            to_date_input.fill("2026-12-31")
            search_input.fill("")
            search_btn.click()
            page.wait_for_timeout(1000)
        elif search_btn.is_visible(timeout=1000):
            search_btn.click()
            page.wait_for_timeout(1000)
    except Exception as exc:
        if on_message:
            on_message(f"General search notice: {exc}")

    return extract_transactions_from_active_table(page)


def navigate_to_gnb_destination(
    page: Page,
    gnb_config: Dict[str, Any],
    on_message: Optional[Callable[[str], None]] = None,
) -> None:
    """Ensure browser page is on configured GNB destination URL.

    Args:
        page: Active Playwright page.
        gnb_config: GNB configuration dictionary.
        on_message: Optional UI message callback.
    """
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
    elif on_message:
        on_message("Inspecting active GNB page for rejected transactions...")


def extract_gnb_rejected_transactions(
    page: Page,
    gnb_config: Dict[str, Any],
    selectors: Dict[str, Any],
    input_file_path: Optional[Path] = None,
    on_message: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, Any]]:
    """Navigate to GNB rejected transactions page and extract all qualifying records.

    Args:
        page: Active Playwright page.
        gnb_config: GNB configuration dictionary.
        selectors: GNB selector mappings.
        input_file_path: Optional input spreadsheet with Transaction IDs.
        on_message: Optional UI callback for log events.

    Returns:
        List[Dict[str, Any]]: List of extracted rejected transactions.
    """
    logger = get_logger("gnb_client")
    navigate_to_gnb_destination(page, gnb_config, on_message=on_message)

    tx_ids: List[str] = []
    if input_file_path and Path(input_file_path).exists():
        tx_ids = extract_transaction_ids_from_file(Path(input_file_path))
        if on_message:
            on_message(f"Loaded {len(tx_ids)} Transaction IDs from {Path(input_file_path).name}")

    has_search = False
    try:
        search_ctrl = page.locator("#searchBtn, button:has-text('Search'), #transactionId").first
        has_search = search_ctrl.is_visible(timeout=1500)
    except Exception:
        has_search = False

    if has_search and tx_ids:
        extracted = search_gnb_by_transaction_ids(page, tx_ids, on_message=on_message)
    elif has_search:
        extracted = search_gnb_general_date_range(page, on_message=on_message)
    else:
        extracted = extract_transactions_from_active_table(page)

    if on_message:
        on_message(f"Extracted {len(extracted)} rejected transactions from GNB.")
    log_event(logger, 20, f"Successfully extracted {len(extracted)} GNB rejected transactions.")
    return extracted


def _execute_gnb_in_thread(
    config: Dict[str, Any],
    input_file_path: Optional[Path] = None,
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

        transactions = extract_gnb_rejected_transactions(
            page,
            gnb_cfg,
            selectors,
            input_file_path=input_file_path,
            on_message=on_message,
        )
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
    input_file_path: Optional[Path] = None,
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
            res = _execute_gnb_in_thread(
                config,
                input_file_path=input_file_path,
                on_message=on_message,
                keep_browser_open=keep_browser_open,
            )
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
