"""Browser management module for Playwright lifecycle operations.

Supports persistent browser profiles, reusable contexts, and Chrome DevTools
Protocol (CDP) remote debugging attachments.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

_PLAYWRIGHT_INSTANCE: Optional[Any] = None
_BROWSER: Optional[Browser] = None
_CONTEXT: Optional[BrowserContext] = None
_PAGE: Optional[Page] = None
_IS_CDP_CONNECTION: bool = False


def launch_persistent_browser_session(
    browser_config: Dict[str, Any],
) -> Tuple[Optional[Browser], BrowserContext, Page]:
    """Initialize or reuse a persistent browser session or CDP connection.

    Args:
        browser_config: Configuration dictionary for browser options.

    Returns:
        Tuple[Optional[Browser], BrowserContext, Page]: Active browser handle (if direct launch),
        context, and page.
    """
    global _PLAYWRIGHT_INSTANCE, _BROWSER, _CONTEXT, _PAGE, _IS_CDP_CONNECTION

    # If context and page are already active and healthy, reuse them directly
    if _CONTEXT is not None and _PAGE is not None and not _PAGE.is_closed():
        return _BROWSER, _CONTEXT, _PAGE

    close_browser_session()

    headless = browser_config.get("headless", False)
    slow_mo = browser_config.get("slow_mo_ms", 100)
    cdp_url = browser_config.get("cdp_url")

    _PLAYWRIGHT_INSTANCE = sync_playwright().start()

    # Mode 1: Connect to existing Chrome instance with remote debugging enabled
    if cdp_url:
        _BROWSER = _PLAYWRIGHT_INSTANCE.chromium.connect_over_cdp(cdp_url)
        _CONTEXT = _BROWSER.contexts[0] if _BROWSER.contexts else _BROWSER.new_context()
        _PAGE = _CONTEXT.pages[0] if _CONTEXT.pages else _CONTEXT.new_page()
        _IS_CDP_CONNECTION = True
        return _BROWSER, _CONTEXT, _PAGE

    # Mode 2: Launch persistent profile context so authentication session persists across restarts
    user_data_dir_str = browser_config.get("user_data_dir", "checkpoints/browser_profile")
    user_data_path = Path(user_data_dir_str).resolve()
    user_data_path.mkdir(parents=True, exist_ok=True)

    _CONTEXT = _PLAYWRIGHT_INSTANCE.chromium.launch_persistent_context(
        user_data_dir=str(user_data_path),
        headless=headless,
        slow_mo=slow_mo,
        args=["--start-maximized"],
        no_viewport=True,
        ignore_https_errors=True,
    )
    _BROWSER = None
    _PAGE = _CONTEXT.pages[0] if _CONTEXT.pages else _CONTEXT.new_page()
    _IS_CDP_CONNECTION = False

    return _BROWSER, _CONTEXT, _PAGE


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
