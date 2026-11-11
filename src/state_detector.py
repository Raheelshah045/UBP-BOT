"""Screen and application state detection module for the OTC Portal.

Inspects active DOM elements, stable selectors, and navigation URLs to accurately
classify the portal screen into discrete operational states.
"""

from typing import Any, Dict

from playwright.sync_api import Page

STATE_AUTHENTICATED_DASHBOARD = "AUTHENTICATED_DASHBOARD"
STATE_CHECK_BILL_STATUS = "CHECK_BILL_STATUS"
STATE_BPS_NAVIGATION = "BPS_NAVIGATION"
STATE_LOGIN_SCREEN = "LOGIN_SCREEN"
STATE_CAPTCHA_SCREEN = "CAPTCHA_SCREEN"
STATE_OTP_SCREEN = "OTP_SCREEN"
STATE_SESSION_EXPIRED = "SESSION_EXPIRED"
STATE_APPLICATION_ERROR = "APPLICATION_ERROR"
STATE_UNKNOWN = "UNKNOWN"


def is_element_present_and_visible(page: Page, selector: str, timeout_ms: int = 400) -> bool:
    """Check if any element matching the selector is currently visible in DOM.

    Args:
        page: Active Playwright page.
        selector: CSS or text selector string.
        timeout_ms: Locator check timeout in milliseconds.

    Returns:
        bool: True if element is attached and visible.
    """
    try:
        loc = page.locator(selector)
        return loc.count() > 0 and loc.first.is_visible(timeout=timeout_ms)
    except Exception:
        return False


def is_login_screen_present(page: Page) -> bool:
    """Check if the page is currently presenting an active, unauthenticated login form.

    Args:
        page: Active Playwright page.

    Returns:
        bool: True if password field or login submit button is visible.
    """
    try:
        # Check if visible password field exists
        pwd_locator = page.locator(
            "#login-password-input, #password, input[type='password']:visible"
        )
        if pwd_locator.count() > 0 and pwd_locator.first.is_visible(timeout=300):
            return True

        # Check if login button in a login container is visible
        login_btn = page.locator(
            "#btn-login, #btnLogin, button:has-text('Sign In'), button:has-text('Log In')"
        )
        if login_btn.count() > 0 and login_btn.first.is_visible(timeout=300):
            username_field = page.locator(
                "#login-username-input, #username, input[name*='user' i]"
            )
            if username_field.count() > 0 and username_field.first.is_visible(timeout=300):
                return True

        return False
    except Exception:
        return False


def is_check_bill_screen_present(page: Page) -> bool:
    """Check if the current view presents the BPS Check Bill Status transaction search form.

    Args:
        page: Active Playwright page.

    Returns:
        bool: True if bank selector and consumer number input are visible.
    """
    if not page or page.is_closed():
        return False
    try:
        # 1. Check for dedicated bill status page wrapper
        if is_element_present_and_visible(
            page, "#bill-status-page, [data-testid='bill-status-page']", timeout_ms=300
        ):
            return True

        # 2. Check for biller/bank selector
        has_bank = is_element_present_and_visible(
            page,
            "#biller-service-select, #bankSelect, select[name*='biller' i], select[name*='bank' i], select[id*='bank' i], select[data-testid='biller-service-select']",
            timeout_ms=300,
        )
        # 3. Check for consumer number input
        has_consumer = is_element_present_and_visible(
            page,
            "#consumer-number-input, #consumerNumberInput, input[name*='consumer' i], input[id*='consumer' i], input[data-testid='consumer-number-input']",
            timeout_ms=300,
        )
        if has_bank and has_consumer:
            return True

        # 4. Check for search button with Check Bill text
        if is_element_present_and_visible(
            page, "#btn-search-bill-status, #filter-section-card, #btnSearch", timeout_ms=300
        ):
            return True

        # 5. Semantic fallback: Check Bill Status heading with any visible form controls
        has_heading = is_element_present_and_visible(
            page, "h1:has-text('Bill Status'), h2:has-text('Bill Status'), div:has-text('Check Bill Status')", timeout_ms=300
        )
        if has_heading and page.locator("input:visible").count() > 0:
            return True

        return False
    except Exception:
        return False


def detect_portal_state(page: Page, selectors: Dict[str, Any]) -> str:
    """Identify the current state of the OTC Portal page using prioritized checks.

    Priority:
    1. Session Expired / Timeout indicator
    2. Check Bill Status search screen
    3. Login / CAPTCHA / OTP screens
    4. Authenticated Dashboard / Application view
    5. Fallback URL pattern inspection

    Args:
        page: Active Playwright page.
        selectors: Portal selector configuration.

    Returns:
        str: Detected state constant.
    """
    if not page or page.is_closed():
        return STATE_UNKNOWN

    # 1. Session Expired check
    expired_sel = selectors.get("login", {}).get(
        "session_expired_indicator",
        "#sessionExpiredAlert, .session-expired",
    )
    if is_element_present_and_visible(page, expired_sel):
        return STATE_SESSION_EXPIRED

    # 2. Check Bill Status screen check (active search form)
    if is_check_bill_screen_present(page):
        return STATE_CHECK_BILL_STATUS

    # 3. Check if active login form is still on screen
    if is_login_screen_present(page):
        otp_sel = selectors.get("login", {}).get("otp_input", "#otp, input[name*='otp' i]")
        if is_element_present_and_visible(page, otp_sel):
            return STATE_OTP_SCREEN
        return STATE_LOGIN_SCREEN

    # 4. Authenticated Indicators
    auth_indicators = [
        "#dashboard-page",
        "#top-navbar",
        "#bank-logo-badge",
        "#btn-goto-check-bill-status",
        "#nav-bps-check-bill-status",
        "#sidebar-nav",
        "#otc-portal-root",
        "#user-display-name",
        "#userProfile",
        ".user-logged-in",
        "[data-authenticated='true']",
        "#navBps",
        "#navCheckBillStatus",
    ]
    for ind in auth_indicators:
        if is_element_present_and_visible(page, ind):
            return STATE_AUTHENTICATED_DASHBOARD

    # 5. Fallback URL pattern inspection
    current_url = page.url.lower()
    if "bps" in current_url or "check-bill" in current_url:
        return STATE_CHECK_BILL_STATUS
    if "dashboard" in current_url or "home" in current_url:
        return STATE_AUTHENTICATED_DASHBOARD
    if "login" in current_url:
        return STATE_LOGIN_SCREEN

    # If no login form exists and URL is valid, assume authenticated app shell
    if current_url and current_url != "about:blank":
        return STATE_AUTHENTICATED_DASHBOARD

    return STATE_UNKNOWN


def is_portal_authenticated(page: Page, selectors: Dict[str, Any]) -> bool:
    """Determine whether the portal is in any fully authenticated operational state.

    Args:
        page: Active Playwright page.
        selectors: Portal selector configuration.

    Returns:
        bool: True if portal has passed login and is in dashboard or bill status state.
    """
    if not page or page.is_closed():
        return False

    # If login form with password field is still active, we are not logged in
    if is_login_screen_present(page):
        return False

    state = detect_portal_state(page, selectors)
    if state == STATE_SESSION_EXPIRED:
        return False

    return state in (STATE_CHECK_BILL_STATUS, STATE_AUTHENTICATED_DASHBOARD, STATE_BPS_NAVIGATION)
