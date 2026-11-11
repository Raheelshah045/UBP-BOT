"""Portal navigation module for BPS Check Bill Status.

Handles dynamic, non-destructive screen reading and in-page navigation to the
Check Bill Status interface with adaptive fallbacks for layout shifts and menu structures.
"""

import time
from typing import Any, Callable, Dict, Optional

from playwright.sync_api import Page

from src.state_detector import is_check_bill_screen_present


def navigate_to_check_bill_status(
    page: Page,
    selectors: Dict[str, Any],
    direct_url: Optional[str] = None,
    on_message: Optional[Callable[[str], None]] = None,
) -> bool:
    """Navigate dynamically to BPS -> Check Bill Status screen using in-page UI clicks.

    Never forces destructive page reloads that wipe out single-page app (React/Vite) sessions.
    Resilient to changes in menu positioning, buttons, sidebars, and top navigation bars.

    Args:
        page: Active Playwright page.
        selectors: Portal selector configuration dictionary.
        direct_url: Optional direct URL override (used only if explicit).
        on_message: Optional status message callback.

    Returns:
        bool: True if bill status form controls become visible.
    """
    if not page or page.is_closed():
        return False

    # 1. If already on Check Bill Status search form, proceed immediately
    if is_check_bill_screen_present(page):
        if on_message:
            on_message("Search form is ready on screen.")
        return True

    # 2. Check if direct action button exists anywhere on the screen
    direct_buttons = [
        "#btn-goto-check-bill-status",
        "[data-testid='btn-goto-check-bill-status']",
        "button:has-text('Check Bill Status')",
        "button:has-text('Go to Check Bill Status')",
        "a:has-text('Go to Check Bill Status')",
        "a:has-text('Check Bill Status')",
    ]
    for btn_sel in direct_buttons:
        try:
            loc = page.locator(btn_sel).first
            if loc.is_visible(timeout=300):
                if on_message:
                    on_message(f"Clicking navigation element: '{btn_sel}'...")
                loc.click()
                time.sleep(0.6)
                if is_check_bill_screen_present(page):
                    if on_message:
                        on_message("Check Bill Status search form loaded.")
                    return True
        except Exception:
            continue

    # 3. Check sidebar or navigation links for Check Bill Status
    nav_links = [
        "#nav-bps-check-bill-status",
        "[data-testid='nav-bps-check-bill-status']",
        "#navCheckBillStatus",
        "[data-nav*='check-bill' i]",
        "[id*='check-bill' i]",
        "[id*='checkbill' i]",
        "a[href*='check-bill' i]",
        "a[href*='checkbill' i]",
    ]
    for n_sel in nav_links:
        try:
            loc = page.locator(n_sel).first
            if loc.is_visible(timeout=300):
                if on_message:
                    on_message("Clicking Check Bill Status link...")
                loc.click()
                time.sleep(0.6)
                if is_check_bill_screen_present(page):
                    return True
        except Exception:
            continue

    # 4. If Check Bill Status is hidden under an expandable BPS menu, expand it
    bps_triggers = [
        "#nav-bps",
        "[data-testid='nav-bps']",
        "#navBps",
        "a:has-text('BPS')",
        "button:has-text('BPS')",
        "div:has-text('BPS')",
        "span:has-text('BPS')",
        "a:has-text('Bill Payment')",
        "button:has-text('Bill Payment')",
        "[data-nav*='bps' i]",
        "[id*='bps' i]",
    ]
    for b_sel in bps_triggers:
        try:
            loc = page.locator(b_sel).first
            if loc.is_visible(timeout=300):
                # Only click to expand if Check Bill Status sub-link is not already visible
                cb_check = page.locator("a:has-text('Check Bill Status')").first
                if not cb_check.is_visible(timeout=200):
                    if on_message:
                        on_message("Expanding BPS module menu...")
                    loc.click()
                    time.sleep(0.5)

                # Now click Check Bill Status sub-link
                cb_target = page.locator(
                    "#nav-bps-check-bill-status, [data-testid='nav-bps-check-bill-status'], "
                    "a:has-text('Check Bill Status'), button:has-text('Check Bill Status'), "
                    "a:has-text('Check Bill'), button:has-text('Check Bill')"
                ).first
                if cb_target.is_visible(timeout=600):
                    cb_target.click()
                    time.sleep(0.6)
                    if is_check_bill_screen_present(page):
                        return True
        except Exception:
            continue

    # 5. Fallback: Any clickable element matching 'Check Bill' or 'Bill Status'
    broad_loc = page.locator("text=/Check Bill Status/i, text=/Check Bill/i").first
    if broad_loc.is_visible(timeout=300):
        try:
            broad_loc.click()
            time.sleep(0.6)
        except Exception:
            pass

    # 6. Wait up to 4 seconds for form controls to render
    for _ in range(8):
        if is_check_bill_screen_present(page):
            if on_message:
                on_message("Check Bill Status search form ready.")
            return True
        time.sleep(0.5)

    # 7. Last resort: Direct URL if explicitly configured
    if direct_url and direct_url not in page.url:
        try:
            if on_message:
                on_message(f"Navigating to direct URL: {direct_url}")
            page.goto(direct_url, wait_until="domcontentloaded")
            time.sleep(1.0)
            return is_check_bill_screen_present(page)
        except Exception:
            pass

    return is_check_bill_screen_present(page)
