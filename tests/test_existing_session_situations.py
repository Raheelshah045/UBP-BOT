"""Unit tests verifying Situation A, Situation B, and Situation C login detection."""

from playwright.sync_api import sync_playwright

from src.auth_manager import check_is_session_expired, ensure_portal_authenticated

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


def test_situation_a_portal_already_authenticated_skips_login() -> None:
    """Verify that when portal is already authenticated, ensure_portal_authenticated returns True immediately."""
    messages = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <div id="userProfile" data-authenticated="true">User OP-101</div>
            <a id="navBps" href="#">BPS</a>
            <select id="bankSelect"><option value="HBL">HBL</option></select>
            <input id="consumerNumberInput" type="text" />
        """)

        ok = ensure_portal_authenticated(
            page=page,
            login_url="http://fake/login",
            check_bill_url=None,
            selectors=SELECTORS,
            timeout_seconds=2,
            on_message_callback=lambda m: messages.append(m),
        )
        assert ok is True
        assert any(
            "already open at Check Bill Status" in m
            or "Existing authenticated session detected" in m
            for m in messages
        )
        browser.close()


def test_situation_b_manual_login_transition_is_automatically_detected() -> None:
    """Verify that completing login on the page is automatically recognized without clicking continue."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <div id="loginContainer">
                <input id="username" type="text" />
                <button id="btnLogin" onclick="document.body.innerHTML='<div id=\\'userProfile\\'>Logged In</div><select id=\\'bankSelect\\'><option>HBL</option></select><input id=\\'consumerNumberInput\\'>'">Log In</button>
            </div>
        """)

        page.click("#btnLogin")

        ok = ensure_portal_authenticated(
            page=page,
            login_url="http://fake/login",
            check_bill_url=None,
            selectors=SELECTORS,
            timeout_seconds=3,
        )
        assert ok is True
        browser.close()


def test_session_expired_detection_flags_invalid_session() -> None:
    """Verify that session expired banner triggers check_is_session_expired."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("<div id='sessionExpiredAlert'>Session Expired</div>")
        assert check_is_session_expired(page, SELECTORS) is True
        browser.close()
