"""Transaction classification module for the OTC Bot.

Evaluates transaction status and response code pairs according to business rules.
"""

from typing import Any, Dict, Optional

DEFAULT_EXCLUDED_CODES = ["95", "98"]
DEFAULT_APPROVED_CODES = ["00"]
DEFAULT_APPROVED_STATUSES = ["APPROVED", "SUCCESSFUL"]
DEFAULT_REJECTED_STATUSES = ["REJECTED"]
DEFAULT_PENDING_STATUSES = ["PENDING"]


def normalize_token(value: Any) -> str:
    """Normalize a string or numeric value by trimming and converting to uppercase.

    Args:
        value: Any input object.

    Returns:
        str: Clean uppercase string representation.
    """
    if value is None:
        return ""
    return str(value).strip().upper()


def classify_transaction(
    status: str, response_code: str, rules_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Classify a single transaction record based on status and response code.

    Args:
        status: The raw transaction status string from the portal.
        response_code: The raw response code string from the portal.
        rules_config: Optional custom rules dictionary.

    Returns:
        Dict[str, Any]: Classification details including category and qualification flags.
    """
    clean_status = normalize_token(status)
    clean_code = normalize_token(response_code)

    excluded_codes = (
        rules_config.get("excluded_rejection_codes", DEFAULT_EXCLUDED_CODES)
        if rules_config
        else DEFAULT_EXCLUDED_CODES
    )
    excluded_codes = [normalize_token(c) for c in excluded_codes]

    approved_statuses = (
        rules_config.get("approved_status_keywords", DEFAULT_APPROVED_STATUSES)
        if rules_config
        else DEFAULT_APPROVED_STATUSES
    )
    approved_statuses = [normalize_token(s) for s in approved_statuses]

    pending_statuses = (
        rules_config.get("pending_status_keywords", DEFAULT_PENDING_STATUSES)
        if rules_config
        else DEFAULT_PENDING_STATUSES
    )
    pending_statuses = [normalize_token(p) for p in pending_statuses]

    rejected_statuses = (
        rules_config.get("rejected_status_keywords", DEFAULT_REJECTED_STATUSES)
        if rules_config
        else DEFAULT_REJECTED_STATUSES
    )
    rejected_statuses = [normalize_token(r) for r in rejected_statuses]

    # Rule 1: Approved / Successful with Code 00
    if clean_status in approved_statuses and clean_code == "00":
        return {
            "classification": "Approved",
            "is_qualifying_rejection": False,
            "is_exception": False,
            "reason": "Transaction approved successfully with code 00.",
        }

    # Rule 2: Rejected with Code 95
    if clean_status in rejected_statuses and clean_code == "95":
        return {
            "classification": "Excluded Code 95",
            "is_qualifying_rejection": False,
            "is_exception": True,
            "reason": "Excluded rejection: Response code 95 (Customer cancelled/Timeout).",
        }

    # Rule 3: Rejected with Code 98
    if clean_status in rejected_statuses and clean_code == "98":
        return {
            "classification": "Excluded Code 98",
            "is_qualifying_rejection": False,
            "is_exception": True,
            "reason": "Excluded rejection: Response code 98 (Duplicate reversal/System cutoff).",
        }

    # Rule 4: Rejected with any other code
    if clean_status in rejected_statuses and clean_code not in excluded_codes:
        return {
            "classification": "Rejected",
            "is_qualifying_rejection": True,
            "is_exception": False,
            "reason": f"Qualifying rejection with response code {clean_code}.",
        }

    # Rule 5: Pending with any code
    if clean_status in pending_statuses:
        return {
            "classification": "Pending",
            "is_qualifying_rejection": False,
            "is_exception": True,
            "reason": f"Pending transaction status with response code {clean_code}.",
        }

    # Rule 6: Unknown or conflicting combinations
    return {
        "classification": "Manual Review",
        "is_qualifying_rejection": False,
        "is_exception": True,
        "reason": f"Unrecognized status '{status}' or unhandled code '{response_code}'.",
    }
