"""Unit tests for secret manager and credential protection."""

import json
import os
from pathlib import Path

from src.ubp_bot.security.secret_manager import (
    get_secret,
    is_secret_key,
    load_env_file,
    sanitize_config_for_storage,
    set_secret,
)


def test_is_secret_key():
    """Verify secret keyword detection."""
    assert is_secret_key("password") is True
    assert is_secret_key("GNB_PASSWORD") is True
    assert is_secret_key("api_key") is True
    assert is_secret_key("auth_token") is True
    assert is_secret_key("username") is False
    assert is_secret_key("login_url") is False


def test_sanitize_config_for_storage():
    """Verify secrets are wiped when serializing config."""
    sensitive_data = {
        "portal": {"login_url": "http://example.com", "password": "SuperSecretPassword123"},
        "gnb": {
            "username": "operator1",
            "password": "GnbPassword456",
            "api_key": "xyz987token",
            "nested": {"token": "secret_session_token", "normal_field": "visible"},
        },
    }

    sanitized = sanitize_config_for_storage(sensitive_data)
    assert sanitized["portal"]["password"] == ""
    assert sanitized["gnb"]["password"] == ""
    assert sanitized["gnb"]["api_key"] == ""
    assert sanitized["gnb"]["nested"]["token"] == ""
    assert sanitized["gnb"]["nested"]["normal_field"] == "visible"
    assert sanitized["portal"]["login_url"] == "http://example.com"
    assert sanitized["gnb"]["username"] == "operator1"


def test_load_env_file_parses_without_logging(tmp_path: Path):
    """Verify .env file parsing."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Test environment variables\n"
        "GNB_TEST_SECRET_KEY=Secret12345\n"
        "GNB_ANOTHER_VAR='QuotedVal'\n",
        encoding="utf-8",
    )

    loaded = load_env_file(env_file)
    assert loaded["GNB_TEST_SECRET_KEY"] == "Secret12345"
    assert loaded["GNB_ANOTHER_VAR"] == "QuotedVal"
    assert os.environ.get("GNB_TEST_SECRET_KEY") == "Secret12345"


def test_get_and_set_secret():
    """Verify in-process secret get/set operations."""
    set_secret("TEST_RUNTIME_SECRET", "RuntimeVal999")
    assert get_secret("TEST_RUNTIME_SECRET") == "RuntimeVal999"
    assert get_secret("NON_EXISTENT_KEY", "fallback") == "fallback"
