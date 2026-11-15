"""Browser management module for Playwright lifecycle operations.

Supports persistent browser profiles, reusable contexts, and Chrome DevTools
Protocol (CDP) remote debugging attachments.
Includes portable browser path configuration for restricted Windows workstations.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from src.config import resolve_app_path

_PLAYWRIGHT_INSTANCE: Optional[Any] = None
_BROWSER: Optional[Browser] = None
_CONTEXT: Optional[BrowserContext] = None
_PAGE: Optional[Page] = None
_IS_CDP_CONNECTION: bool = False

_GNB_PLAYWRIGHT: Optional[Any] = None
_GNB_CONTEXT: Optional[BrowserContext] = None
_GNB_PAGE: Optional[Page] = None


def configure_portable_browsers_path(browser_config: Dict[str, Any]) -> Optional[Path]:
    """Configure PLAYWRIGHT_BROWSERS_PATH to use application-controlled directories.

    Prioritizes:
    1. Explicit 'browser_dir' setting in configuration.
    2. Local 'browsers' directory inside the portable application root.
    3. Retains existing environment variable or user-level fallback.

    Args:
        browser_config: Browser options dictionary.

    Returns:
        Optional[Path]: Configured directory path if found and set.
    """
    custom_dir = browser_config.get("browser_dir")
    if custom_dir:
        resolved_custom = resolve_app_path(custom_dir)
        if resolved_custom.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(resolved_custom)
            return resolved_custom

    local_browsers = resolve_app_path("browsers")
    if local_browsers.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(local_browsers)
        return local_browsers

    return None


def verify_browser_runtime_available(browser_config: Dict[str, Any]) -> Tuple[bool, str]:
    """Verify that a usable browser binary exists before attempting to launch.

    Returns:
        Tuple[bool, str]: (is_available, description_or_error_path)
    """
    cdp_url = browser_config.get("cdp_url")
    if cdp_url:
        return True, f"Remote CDP URL configured: {cdp_url}"

    channel = browser_config.get("channel")
    if channel:
        return True, f"System channel configured: {channel}"

    exec_path = browser_config.get("executable_path")
    if exec_path:
        p = resolve_app_path(exec_path)
        if p.exists():
            return True, str(p)
        return False, f"Configured browser executable not found at: {p}"

    browsers_dir = resolve_app_path("browsers")
    if browsers_dir.exists():
        for ch_dir in browsers_dir.glob("chromium-*"):
            chrome_exe = ch_dir / "chrome-win" / "chrome.exe"
            if chrome_exe.exists():
                return True, str(chrome_exe)

    local_app = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    if local_app.exists():
        for ch_dir in local_app.glob("chromium-*"):
            chrome_exe = ch_dir / "chrome-win" / "chrome.exe"
            if chrome_exe.exists():
                return True, str(chrome_exe)

    try:
        pw_probe = sync_playwright().start()
        try:
            exe = Path(pw_probe.chromium.executable_path)
            if exe.exists():
                return True, str(exe)
        finally:
            pw_probe.stop()
    except Exception:
        pass

    expected = browsers_dir / "chromium-<version>" / "chrome-win" / "chrome.exe"
    return False, f"Missing bundled Chromium runtime at: {expected}. Run 'playwright install chromium' to download."


def launch_persistent_browser_session(
    browser_config: Dict[str, Any],
    initial_url: Optional[str] = None,
    system_name: str = "otc",
) -> Tuple[Optional[Browser], BrowserContext, Page]:
    """Initialize or reuse a persistent browser session or CDP connection for a system.

    Supports independent browser profiles and contexts per system (e.g. OTC vs GNB).

    Args:
        browser_config: Configuration dictionary for browser options.
        initial_url: Optional target portal URL to navigate immediately upon launch.
        system_name: Name of system for isolated context profiling ("otc" or "gnb").

    Returns:
        Tuple[Optional[Browser], BrowserContext, Page]: Active browser handle (if direct launch),
        context, and page.

    Raises:
        RuntimeError: If browser launch fails with actionable diagnostic remedies.
    """
    global _PLAYWRIGHT_INSTANCE, _BROWSER, _CONTEXT, _PAGE, _IS_CDP_CONNECTION
    global _GNB_PLAYWRIGHT, _GNB_CONTEXT, _GNB_PAGE

    # If asking for default/otc and already open and healthy, reuse
    if system_name == "otc" and _CONTEXT is not None and _PAGE is not None and not _PAGE.is_closed():
        if initial_url and _PAGE.url in ("about:blank", ""):
            try:
                _PAGE.goto(initial_url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass
        return _BROWSER, _CONTEXT, _PAGE

    # If asking for gnb and already open and healthy, reuse
    if system_name == "gnb" and _GNB_CONTEXT is not None and _GNB_PAGE is not None and not _GNB_PAGE.is_closed():
        if initial_url and _GNB_PAGE.url in ("about:blank", ""):
            try:
                _GNB_PAGE.goto(initial_url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass
        return None, _GNB_CONTEXT, _GNB_PAGE

    configure_portable_browsers_path(browser_config)

    # Pre-flight check: verify browser availability before attempting launch
    is_avail, detail = verify_browser_runtime_available(browser_config)
    if not is_avail:
        raise RuntimeError(
            f"Browser runtime error: {detail}\n"
            "Please ensure the 'browsers' directory with Chromium binaries is present in the "
            "application root, or configure 'channel': 'msedge' to use the pre-installed system browser."
        )

    headless = browser_config.get("headless", False)
    slow_mo = browser_config.get("slow_mo_ms", 100)
    cdp_url = browser_config.get("cdp_url")
    channel = browser_config.get("channel")
    exec_path = browser_config.get("executable_path")

    # In Playwright Python (sync_api), each thread must have its own Playwright instance
    # to avoid greenlet thread-affinity errors ("Cannot switch to a different thread").
    playwright_inst = sync_playwright().start()
    if system_name == "otc":
        _PLAYWRIGHT_INSTANCE = playwright_inst


    # Mode 1: Connect to existing Chrome instance with remote debugging enabled
    if cdp_url:
        _BROWSER = playwright_inst.chromium.connect_over_cdp(cdp_url)
        _CONTEXT = _BROWSER.contexts[0] if _BROWSER.contexts else _BROWSER.new_context()
        _PAGE = _CONTEXT.pages[0] if _CONTEXT.pages else _CONTEXT.new_page()
        _IS_CDP_CONNECTION = True
        if initial_url and _PAGE.url in ("about:blank", ""):
            try:
                _PAGE.goto(initial_url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass
        return _BROWSER, _CONTEXT, _PAGE

    # Mode 2: Launch persistent profile context isolated per system
    base_user_data = browser_config.get("user_data_dir", "checkpoints/browser_profile")
    if system_name != "otc":
        user_data_dir_str = f"{base_user_data}_{system_name}"
    else:
        user_data_dir_str = base_user_data

    user_data_path = resolve_app_path(user_data_dir_str)
    user_data_path.mkdir(parents=True, exist_ok=True)

    launch_kwargs: Dict[str, Any] = {
        "user_data_dir": str(user_data_path),
        "headless": headless,
        "slow_mo": slow_mo,
        "args": ["--start-maximized"],
        "no_viewport": True,
        "ignore_https_errors": browser_config.get("ignore_https_errors", False),
    }
    if channel:
        launch_kwargs["channel"] = channel
    if exec_path:
        launch_kwargs["executable_path"] = str(resolve_app_path(exec_path))

    try:
        context = playwright_inst.chromium.launch_persistent_context(**launch_kwargs)
    except Exception as exc:
        try:
            from src.gnb_client import release_stale_profile_lock

            release_stale_profile_lock(user_data_path)
            context = playwright_inst.chromium.launch_persistent_context(**launch_kwargs)
        except Exception:
            err_msg = str(exc)
            remedy = (
                "Browser launch failed. If your workstation security policy (AppLocker) blocks custom "
                "binaries, set 'channel': 'msedge' or 'channel': 'chrome' in config.json to use the "
                "pre-installed system browser, or use 'cdp_url' for remote debugging."
            )
            raise RuntimeError(f"{err_msg}\n[Diagnostic Tip]: {remedy}") from exc

    page = context.pages[0] if context.pages else context.new_page()

    if system_name == "otc":
        _CONTEXT = context
        _PAGE = page
        _BROWSER = None
        _IS_CDP_CONNECTION = False
    elif system_name == "gnb":
        _GNB_PLAYWRIGHT = playwright_inst
        _GNB_CONTEXT = context
        _GNB_PAGE = page

    if initial_url:
        try:
            page.goto(initial_url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass

    return None, context, page



def navigate_browser_to(url: str, timeout_ms: int = 15000) -> bool:
    """Navigate the active browser page to the specified URL without opening blank tabs.

    Args:
        url: Target web address.
        timeout_ms: Maximum navigation timeout in milliseconds.

    Returns:
        bool: True if page loaded successfully.
    """
    page = get_active_browser_page()
    if not page or page.is_closed():
        return False
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        return True
    except Exception:
        return False


def launch_browser_session(
    browser_config: Dict[str, Any],
) -> Tuple[Optional[Browser], BrowserContext, Page]:
    """Backward compatible launcher wrapper."""
    return launch_persistent_browser_session(browser_config)


def get_active_page() -> Optional[Page]:
    """Backward compatible page getter wrapper."""
    return get_active_browser_page()


def get_active_browser_page() -> Optional[Page]:
    """Retrieve the current active browser page instance.

    Returns:
        Optional[Page]: Active page if valid, else None.
    """
    if _PAGE is not None and not _PAGE.is_closed():
        return _PAGE
    return None


def close_browser_session() -> None:
    """Safely terminate page, context, browser, and playwright runner instances."""
    global _PLAYWRIGHT_INSTANCE, _BROWSER, _CONTEXT, _PAGE, _IS_CDP_CONNECTION

    if _PAGE is not None:
        try:
            if not _PAGE.is_closed():
                _PAGE.close()
        except Exception:
            pass
        _PAGE = None

    if _CONTEXT is not None:
        try:
            _CONTEXT.close()
        except Exception:
            pass
        _CONTEXT = None

    if _BROWSER is not None:
        try:
            _BROWSER.close()
        except Exception:
            pass
        _BROWSER = None

    if _PLAYWRIGHT_INSTANCE is not None:
        try:
            _PLAYWRIGHT_INSTANCE.stop()
        except Exception:
            pass
        _PLAYWRIGHT_INSTANCE = None

    _IS_CDP_CONNECTION = False

    try:
        from src.gnb_client import close_gnb_session
        close_gnb_session()
    except Exception:
        pass
