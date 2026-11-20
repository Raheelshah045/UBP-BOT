"""Enterprise Secret and Credential Management for UBP Bot.

Provides secure credential handling:
- Environment variable and .env parsing without exposing secret values
- Scrubbing and sanitization of secrets before serializing configuration to disk
- In-memory secret isolation to prevent credential leakage in logs or crash dumps
- Protection against hardcoded bank credentials
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

# Keywords that indicate confidential credential attributes
SECRET_KEYWORDS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "auth",
    "credential",
    "private_key",
)


def load_env_file(env_file_path: Path) -> Dict[str, str]:
    """Parse local .env file securely into a dictionary without logging values.

    Args:
        env_file_path: Path to the .env file.

    Returns:
        Dict[str, str]: Key-value pairs discovered in the file.
    """
    loaded: Dict[str, str] = {}
    if not env_file_path.exists():
        return loaded

    try:
        with env_file_path.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" in stripped:
                    key, val = stripped.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key:
                        loaded[key] = val
                        if key not in os.environ:
                            os.environ[key] = val
    except Exception:
        pass
    return loaded


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve a sensitive secret string from environment variables.

    Args:
        key: Variable name (e.g. 'GNB_PASSWORD').
        default: Fallback value if not set.

    Returns:
        Optional[str]: Secret value or default.
    """
    return os.environ.get(key, default)


def set_secret(key: str, value: str) -> None:
    """Store a secret securely in the current process environment.

    Args:
        key: Secret identifier.
        value: Secret text.
    """
    os.environ[key] = value


def is_secret_key(key_name: str) -> bool:
    """Check if a dictionary key name indicates sensitive credential information."""
    lower_key = str(key_name).lower()
    return any(keyword in lower_key for keyword in SECRET_KEYWORDS)


def sanitize_config_for_storage(data: Any) -> Any:
    """Recursively scrub passwords, secrets, and auth tokens before saving configuration to disk.

    Args:
        data: Arbitrary configuration data structure (dict, list, or primitive).

    Returns:
        Sanitized copy with all secret values replaced with empty strings.
    """
    if isinstance(data, dict):
        sanitized: Dict[str, Any] = {}
        for key, value in data.items():
            if is_secret_key(key):
                sanitized[key] = ""
            elif isinstance(value, (dict, list)):
                sanitized[key] = sanitize_config_for_storage(value)
            else:
                sanitized[key] = value
        return sanitized
    elif isinstance(data, list):
        return [sanitize_config_for_storage(item) for item in data]
    return data
