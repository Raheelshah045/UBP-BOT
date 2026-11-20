"""Log Sanitization and PII/Credential Masking for Enterprise UBP Bot.

Provides comprehensive masking for sensitive financial and operational telemetry:
- Passwords, secrets, tokens, API keys
- Consumer numbers, bank account numbers, CNICs
- Session cookies, bearer authorization headers
- UI event log callbacks
"""

import logging
import re
from pathlib import Path
from typing import Callable, Optional

_UI_LOG_CALLBACK: Optional[Callable[[str], None]] = None

# Regex patterns for sensitive credentials & tokens
_SENSITIVE_CRED_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|sessionid|cookie)\s*[:=]\s*([^\s,;\"']+)",
    re.IGNORECASE,
)

# Regex pattern for Authorization / Bearer tokens (e.g. Bearer eyJhbGci... or Authorization: Bearer xyz)
_BEARER_TOKEN_PATTERN = re.compile(
    r"(?i)(bearer|auth|authorization)\s*[:=]?\s*([a-zA-Z0-9_\-\.]{15,})",
    re.IGNORECASE,
)

# Regex pattern for JSON/form-encoded passwords & secrets
_JSON_CRED_PATTERN = re.compile(
    r'(?i)"(password|passwd|secret|token|api[_-]?key|bearer|auth)"\s*:\s*"([^"]+)"',
    re.IGNORECASE,
)

# Regex pattern for Pakistani CNIC (e.g. 42101-1234567-1 or 13 digits)
_CNIC_PATTERN = re.compile(r"\b(\d{5})-?(\d{7})-?(\d{1})\b")

# Regex pattern for standard payment card / 16-digit account formats
_CARD_ACCOUNT_PATTERN = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")


def mask_sensitive_text(text: str) -> str:
    """Mask credentials, secrets, tokens, and PII from a log message.

    Args:
        text: Raw log message string.

    Returns:
        str: Sanitized log message with sensitive substrings replaced with redaction markers.
    """
    if not text:
        return text

    sanitized = str(text)

    # 1. Mask key-value credentials: password=xyz -> password=***REDACTED***
    sanitized = _SENSITIVE_CRED_PATTERN.sub(r"\1=***REDACTED***", sanitized)

    # 1b. Mask Bearer / Authorization tokens
    sanitized = _BEARER_TOKEN_PATTERN.sub(r"\1 ***REDACTED***", sanitized)

    # 2. Mask JSON formatted credentials: "password": "xyz" -> "password": "***REDACTED***"
    sanitized = _JSON_CRED_PATTERN.sub(r'"\1": "***REDACTED***"', sanitized)

    # 3. Mask CNICs (show first 5 and last 1 digit only)
    sanitized = _CNIC_PATTERN.sub(r"\1-*******-\3", sanitized)

    # 4. Mask 16-digit card / account numbers (show first 4 and last 4)
    def _mask_card(match: re.Match[str]) -> str:
        raw = match.group(0).replace("-", "").replace(" ", "")
        return f"{raw[:4]}-****-****-{raw[-4:]}"

    sanitized = _CARD_ACCOUNT_PATTERN.sub(_mask_card, sanitized)

    return sanitized


def mask_consumer_number(consumer_number: str) -> str:
    """Mask a consumer/utility account number for safe display and logging.

    Displays only the first 4 and last 4 characters if length > 8, or replaces
    shorter identifiers with 6 asterisks.

    Args:
        consumer_number: The raw consumer identifier string.

    Returns:
        str: Masked string representation.
    """
    clean_num = str(consumer_number).strip()
    if not clean_num:
        return ""
    if len(clean_num) <= 8:
        return "******"
    masked_middle = "*" * (len(clean_num) - 8)
    return f"{clean_num[:4]}{masked_middle}{clean_num[-4:]}"


class SanitizedFormatter(logging.Formatter):
    """Logging formatter that automatically applies log sanitization to all records."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return mask_sensitive_text(original)


def set_ui_log_callback(callback: Optional[Callable[[str], None]]) -> None:
    """Register a callback to stream sanitized log messages to the desktop UI.

    Args:
        callback: Callable receiving single formatted log lines.
    """
    global _UI_LOG_CALLBACK
    _UI_LOG_CALLBACK = callback


def emit_ui_log(message: str) -> None:
    """Forward a log message to the desktop UI callback after sanitization.

    Args:
        message: Formatted log message text.
    """
    if _UI_LOG_CALLBACK is not None:
        try:
            _UI_LOG_CALLBACK(mask_sensitive_text(message))
        except Exception:
            pass


def get_logger(name: str = "ubp_bot", logs_dir: Optional[Path] = None) -> logging.Logger:
    """Configure and return a sanitized enterprise logger instance.

    Args:
        name: Logger name identifier.
        logs_dir: Optional custom directory to store daily log files.

    Returns:
        logging.Logger: Configured logger with sanitized stream and file handlers.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = SanitizedFormatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console / stream handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # File handler
    target_logs_dir = logs_dir if logs_dir is not None else Path("logs")
    try:
        target_logs_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime

        today_str = datetime.now().strftime("%Y%m%d")
        log_file = target_logs_dir / f"{name}_{today_str}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        pass

    return logger


def log_event(logger: logging.Logger, level: int, message: str) -> None:
    """Log an event safely through the logger and forward to UI subscribers.

    Args:
        logger: Logger instance.
        level: Standard logging level integer (e.g. logging.INFO).
        message: Raw message text to sanitize and record.
    """
    sanitized_msg = mask_sensitive_text(message)
    logger.log(level, sanitized_msg)
    emit_ui_log(sanitized_msg)
