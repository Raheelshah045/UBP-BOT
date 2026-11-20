"""Unit tests for log sanitization and sensitive data masking."""

from src.ubp_bot.security.log_sanitizer import (
    mask_consumer_number,
    mask_sensitive_text,
)


def test_mask_sensitive_text_credentials():
    """Verify password, token, and api key masking in free text."""
    raw1 = "Failed login for user admin with password=MySecretPass123!"
    sanitized1 = mask_sensitive_text(raw1)
    assert "MySecretPass123!" not in sanitized1
    assert "password=***REDACTED***" in sanitized1

    raw2 = 'Request body: {"username": "admin", "password": "UnsafePassword789"}'
    sanitized2 = mask_sensitive_text(raw2)
    assert "UnsafePassword789" not in sanitized2
    assert '"password": "***REDACTED***"' in sanitized2

    raw3 = "Headers: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    sanitized3 = mask_sensitive_text(raw3)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized3


def test_mask_sensitive_text_cnic_and_card():
    """Verify national ID and card/account numbers are sanitized."""
    # CNIC format 42101-1234567-1
    raw_cnic = "Customer CNIC is 42101-1234567-1 for verification"
    sanitized_cnic = mask_sensitive_text(raw_cnic)
    assert "1234567" not in sanitized_cnic
    assert "42101-*******-1" in sanitized_cnic

    # 16-digit card number
    raw_card = "Processed account 1234-5678-9876-5432 with success"
    sanitized_card = mask_sensitive_text(raw_card)
    assert "5678" not in sanitized_card
    assert "9876" not in sanitized_card
    assert "1234-****-****-5432" in sanitized_card


def test_mask_consumer_number():
    """Verify consumer number masking displays only edge digits."""
    assert mask_consumer_number("12345678901234") == "1234******1234"
    assert mask_consumer_number("10012345678901") == "1001******8901"
    assert mask_consumer_number("12345") == "******"
    assert mask_consumer_number("") == ""
