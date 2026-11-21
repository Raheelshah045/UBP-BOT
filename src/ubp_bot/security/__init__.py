"""Security and audit subsystems for UBP Bot."""

from src.ubp_bot.security.log_sanitizer import (
    emit_ui_log,
    get_logger,
    log_event,
    mask_consumer_number,
    mask_sensitive_text,
    set_ui_log_callback,
)
from src.ubp_bot.security.secret_manager import (
    get_secret,
    load_env_file,
    sanitize_config_for_storage,
    set_secret,
)

__all__ = [
    "mask_sensitive_text",
    "mask_consumer_number",
    "get_logger",
    "log_event",
    "set_ui_log_callback",
    "emit_ui_log",
    "load_env_file",
    "get_secret",
    "set_secret",
    "sanitize_config_for_storage",
]
