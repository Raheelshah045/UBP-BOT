"""Logging module for the OTC Bot.

Provides masked logging, file handlers, and UI event hooks.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

_UI_LOG_CALLBACK: Optional[Callable[[str], None]] = None

_SENSITIVE_PATTERN = re.compile(
    r"(password|secret|token|api[_-]?key)\s*[:=]\s*([^\s,;]+)",
    re.IGNORECASE,
)


def mask_sensitive_text(text: str) -> str:
    """Mask credentials, secrets, or tokens in text strings."""
    return _SENSITIVE_PATTERN.sub(r"\1=***REDACTED***", text)


def mask_consumer_number(consumer_number: str) -> str:
    """Mask a consumer number for safe logging to protect sensitive data.

    Args:
        consumer_number: The raw consumer number string.

    Returns:
        str: Masked string displaying only leading and trailing digits.
    """
    clean_num = str(consumer_number).strip()
    if len(clean_num) <= 6:
        return "******"
    return f"{clean_num[:4]}{'*' * (len(clean_num) - 8)}{clean_num[-4:]}"


def set_ui_log_callback(callback: Optional[Callable[[str], None]]) -> None:
    """Register a callback function to forward log messages to the desktop UI.

    Args:
        callback: Function accepting a single formatted log line string.
    """
    global _UI_LOG_CALLBACK
    _UI_LOG_CALLBACK = callback


def emit_ui_log(message: str) -> None:
    """Deliver a log message to the desktop interface callback if set.

    Args:
        message: Formatted text to display in the UI console.
    """
    if _UI_LOG_CALLBACK is not None:
        try:
            _UI_LOG_CALLBACK(mask_sensitive_text(message))
        except Exception:
            pass


def get_logger(name: str = "otc_bot", logs_dir: Optional[Path] = None) -> logging.Logger:
    """Configure and retrieve a logger instance with file and stream outputs.

    Args:
        name: Name of the logger instance.
        logs_dir: Optional custom directory to store log files.

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    target_dir = (
        logs_dir if logs_dir is not None else Path(__file__).resolve().parent.parent / "logs"
    )
    target_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file_path = target_dir / f"otc_bot_{date_str}.log"
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    row_number: Optional[int] = None,
    consumer_number: Optional[str] = None,
) -> None:
    """Log an execution event with row reference and masked consumer number.

    Args:
        logger: Logger instance to write to.
        level: Logging level (e.g. logging.INFO, logging.WARNING).
        message: Main message text.
        row_number: Optional 1-based input row index.
        consumer_number: Optional consumer identifier to be masked.
    """
    row_part = f"[Row {row_number}] " if row_number is not None else ""
    consumer_part = (
        f"[Consumer: {mask_consumer_number(consumer_number)}] "
        if consumer_number is not None
        else ""
    )
    full_message = mask_sensitive_text(f"{row_part}{consumer_part}{message}")
    logger.log(level, full_message)
    emit_ui_log(full_message)
