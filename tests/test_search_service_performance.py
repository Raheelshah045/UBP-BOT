"""Regression tests for OTC search polling and browser-session isolation."""

from typing import Any

import pytest

from src import browser_manager, search_service


class _FakeSearchButton:
    def click(self, timeout: int) -> None:
        self.timeout = timeout


class _FakeHandle:
    def __init__(self, value: str) -> None:
        self.value = value

    def json_value(self) -> str:
        return self.value


class _FakePage:
    def __init__(self, state: str | None) -> None:
        self.state = state
        self.polling: int | None = None
        self.timeout: int | None = None
        self.expression = ""
        self.argument: Any = None

    def wait_for_function(
        self,
        expression: str,
        *,
        arg: Any,
        timeout: int,
        polling: int,
    ) -> _FakeHandle:
        self.expression = expression
        self.argument = arg
        self.timeout = timeout
        self.polling = polling
        if self.state is None:
            raise TimeoutError("simulated portal response timeout")
        return _FakeHandle(self.state)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("TABLE", True),
        ("NO_RECORD", True),
        ("ERROR", False),
    ],
)
def test_search_waits_for_terminal_result_state_inside_browser(
    monkeypatch: pytest.MonkeyPatch, state: str, expected: bool
) -> None:
    monkeypatch.setattr(search_service, "fill_search_fields", lambda *args: None)
    monkeypatch.setattr(search_service, "_get_active_row_text", lambda *args: "previous")
    monkeypatch.setattr(
        search_service, "find_search_button_locator", lambda *args: _FakeSearchButton()
    )

    page = _FakePage(state)
    result = search_service.execute_transaction_search(
        page,
        {},
        "UBL",
        "123456789012",
        "2026-11-20",
        {},
        timeout_ms=15000,
    )

    assert result is expected
    assert page.polling == 100
    assert page.timeout == 15000
    assert "state === \"WAITING\"" in page.expression
    assert page.argument == ["previous", "123456789012"]


def test_search_timeout_returns_false_without_retrying_inside_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_service, "fill_search_fields", lambda *args: None)
    monkeypatch.setattr(search_service, "_get_active_row_text", lambda *args: None)
    monkeypatch.setattr(
        search_service, "find_search_button_locator", lambda *args: _FakeSearchButton()
    )

    page = _FakePage(None)
    result = search_service.execute_transaction_search(
        page,
        {},
        "UBL",
        "123456789012",
        "2026-11-20",
        {},
        timeout_ms=15000,
    )

    assert result is False
    assert page.polling == 100


def test_closing_otc_browser_does_not_close_gnb_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.gnb_client as gnb_client

    monkeypatch.setattr(browser_manager, "_PAGE", None)
    monkeypatch.setattr(browser_manager, "_CONTEXT", None)
    monkeypatch.setattr(browser_manager, "_BROWSER", None)
    monkeypatch.setattr(browser_manager, "_PLAYWRIGHT_INSTANCE", None)
    monkeypatch.setattr(browser_manager, "_IS_CDP_CONNECTION", False)

    gnb_close_calls: list[str] = []
    monkeypatch.setattr(
        gnb_client, "close_gnb_session", lambda: gnb_close_calls.append("closed")
    )

    browser_manager.close_browser_session()

    assert gnb_close_calls == []
