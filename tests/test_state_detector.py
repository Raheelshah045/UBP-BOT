"""Unit tests for portal screen and application state identification."""

from playwright.sync_api import sync_playwright

from src.state_detector import (
    STATE_AUTHENTICATED_DASHBOARD,
    STATE_CHECK_BILL_STATUS,
    STATE_LOGIN_SCREEN,
    STATE_SESSION_EXPIRED,
    detect_portal_state,
    is_portal_authenticated,
)

SELECTORS = {
    "login": {
        "auth_indicator": "#userProfile",
        "username_input": "#username",
        "session_expired_indicator": "#sessionExpiredAlert",
        "submit_button": "#btnLogin",
    },
    "navigation": {"bps_menu": "#navBps", "check_bill_status_link": "#navCheckBillStatus"},
    "search": {"bank_select": "#bankSelect", "consumer_input": "#consumerNumberInput"},
}


def test_detects_login_screen_state() -> None:
    """Verify that a page presenting username and login button is identified as LOGIN_SCREEN."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <div id="loginContainer">
                <input id="username" type="text" />
                <input id="password" type="password" />
                <button id="btnLogin">Log In</button>
            </div>
        """)
        state = detect_portal_state(page, SELECTORS)
        assert state == STATE_LOGIN_SCREEN
        assert is_portal_authenticated(page, SELECTORS) is False
        browser.close()


def test_detects_authenticated_dashboard_state() -> None:
    """Verify that dashboard showing user profile and BPS menu is identified as AUTHENTICATED_DASHBOARD."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <div id="userProfile" data-authenticated="true">User OP-101</div>
            <a id="navBps" href="/bps">BPS</a>
        """)
        state = detect_portal_state(page, SELECTORS)
        assert state == STATE_AUTHENTICATED_DASHBOARD
        assert is_portal_authenticated(page, SELECTORS) is True
        browser.close()


def test_detects_check_bill_status_state() -> None:
    """Verify that search form screen is identified as CHECK_BILL_STATUS."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <select id="bankSelect"><option value="HBL">HBL</option></select>
            <input id="consumerNumberInput" type="text" />
        """)
        state = detect_portal_state(page, SELECTORS)
        assert state == STATE_CHECK_BILL_STATUS
        assert is_portal_authenticated(page, SELECTORS) is True
        browser.close()


def test_detects_session_expired_state() -> None:
    """Verify that expired alert element is identified as SESSION_EXPIRED."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <div id="sessionExpiredAlert">Your session has timed out.</div>
        """)
        state = detect_portal_state(page, SELECTORS)
        assert state == STATE_SESSION_EXPIRED
        assert is_portal_authenticated(page, SELECTORS) is False
        browser.close()
