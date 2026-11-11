"""Authentication and session management module.

Implements responsive existing-session detection, automated login recognition,
and resilient session expiration recovery.
"""

import time
from typing import Any, Callable, Dict, Optional

from playwright.sync_api import Page

from src.portal_navigator import navigate_to_check_bill_status
from src.state_detector import (
    STATE_SESSION_EXPIRED,
    detect_portal_state,
    is_check_bill_screen_present,
    is_login_screen_present,
    is_portal_authenticated,
)


def check_is_authenticated(page: Page, selectors: Dict[str, Any]) -> bool:
    """Check if the current browser page presents an authenticated state.

    Args:
        page: Active Playwright page object.
        selectors: Configured portal selector mapping.

    Returns:
        bool: True if authenticated landing element is present and visible.
    """
    return is_portal_authenticated(page, selectors)


def wait_for_manual_login(
    page: Page,
    login_url: str,
    selectors: Dict[str, Any],
    timeout_seconds: int = 300,
    check_interval: float = 0.8,
    on_prompt_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """Wait for manual authentication (backward-compatible wrapper)."""
    return ensure_portal_authenticated(
        page=page,
        login_url=login_url,
        check_bill_url=None,
        selectors=selectors,
        timeout_seconds=timeout_seconds,
        on_message_callback=on_prompt_callback,
    )


def ensure_portal_authenticated(
    page: Page,
    login_url: str,
    check_bill_url: Optional[str] = None,
    selectors: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 300,
    on_message_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """Detect existing portal state and guide authentication autonomously.

    Args:
        page: Active Playwright page.
        login_url: Configured portal entrypoint URL.
        check_bill_url: Optional direct URL to check bill status.
        selectors: Optional portal selector configuration.
        timeout_seconds: Maximum time to wait for manual authentication.
        on_message_callback: Optional UI status feedback hook.

    Returns:
        bool: True if portal is authenticated and positioned at Check Bill Status.
    """
    sel = selectors or {}

    # Situation A: Already on Check Bill Status screen
    if is_check_bill_screen_present(page):
        if on_message_callback:
            on_message_callback(
                "Portal is already open at Check Bill Status screen. Starting search."
            )
        return True

    # Situation A2: Already authenticated on another page
    if is_portal_authenticated(page, sel):
        if on_message_callback:
            on_message_callback("Existing authenticated session detected. Navigating to BPS...")
        navigate_to_check_bill_status(page, sel, check_bill_url, on_message=on_message_callback)
        return True

    # Situation C: Blank page -> Navigate to configured single portal URL
    if not page.url or page.url in ("about:blank", ""):
        if on_message_callback:
            on_message_callback(f"Opening portal URL: {login_url}")
        page.goto(login_url, wait_until="domcontentloaded")
        time.sleep(1.0)

        if is_portal_authenticated(page, sel):
            if on_message_callback:
                on_message_callback("Session authenticated automatically from profile cookies.")
            navigate_to_check_bill_status(page, sel, check_bill_url, on_message=on_message_callback)
            return True

    # Situation B: Login form is active -> Prompt operator and poll responsive DOM state
    if on_message_callback:
        on_message_callback("Please complete portal authentication in the browser window.")

    start_time = time.time()
    last_notify_time = start_time

    while time.time() - start_time < timeout_seconds:
        # Check if login form is gone and user has successfully authenticated
        if not is_login_screen_present(page) and is_portal_authenticated(page, sel):
            if on_message_callback:
                on_message_callback("Authentication confirmed! Transitioning to BPS...")
            time.sleep(0.5)
            navigate_to_check_bill_status(page, sel, check_bill_url, on_message=on_message_callback)
            return True

        if is_check_bill_screen_present(page):
            if on_message_callback:
                on_message_callback("Reached Check Bill Status. Ready to process records.")
            return True

        # Periodic gentle reminder in console every 30s
        if time.time() - last_notify_time > 30.0:
            if on_message_callback:
                on_message_callback("Waiting for manual authentication to complete...")
            last_notify_time = time.time()

        time.sleep(0.8)

    if on_message_callback:
        on_message_callback("Authentication timeout reached without successful login.")
    return False


def check_is_session_expired(page: Page, selectors: Dict[str, Any]) -> bool:
    """Detect whether the portal session has expired or been evicted.

    Args:
        page: Active Playwright page.
        selectors: Configured portal selectors.

    Returns:
        bool: True if page indicates session expiration or forced redirection to login.
    """
    state = detect_portal_state(page, selectors)
    if state == STATE_SESSION_EXPIRED:
        return True
    return is_login_screen_present(page)
