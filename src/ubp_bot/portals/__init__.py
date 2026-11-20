"""Banking portal automation clients for UBP Bot (OTC and GNB)."""

from src.ubp_bot.portals.gnb_client import (
    is_gnb_authenticated,
    is_gnb_pipeline_active,
    login_gnb_portal,
    release_stale_profile_lock,
    run_gnb_extraction_pipeline,
)
from src.ubp_bot.portals.otc_client import (
    DEFAULT_APPROVED_CODES,
    DEFAULT_EXCLUDED_CODES,
    check_is_authenticated,
    check_is_session_expired,
    classify_transaction,
    detect_portal_state,
    ensure_portal_authenticated,
    execute_transaction_search,
    extract_all_transactions,
    is_check_bill_screen_present,
    is_portal_authenticated,
    navigate_to_check_bill_status,
)

__all__ = [
    "DEFAULT_EXCLUDED_CODES",
    "DEFAULT_APPROVED_CODES",
    "classify_transaction",
    "check_is_authenticated",
    "check_is_session_expired",
    "detect_portal_state",
    "ensure_portal_authenticated",
    "execute_transaction_search",
    "extract_all_transactions",
    "is_check_bill_screen_present",
    "is_portal_authenticated",
    "navigate_to_check_bill_status",
    "run_gnb_extraction_pipeline",
    "is_gnb_pipeline_active",
    "is_gnb_authenticated",
    "login_gnb_portal",
    "release_stale_profile_lock",
]
