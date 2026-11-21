"""Core services and utilities for UBP Bot."""

from src.ubp_bot.services.browser_manager import (
    close_all_browser_sessions,
    close_browser_session,
    configure_portable_browsers_path,
    get_active_browser_page,
    launch_persistent_browser_session,
    verify_browser_runtime_available,
)
from src.ubp_bot.services.diagnostics import (
    format_diagnostics_report,
    run_full_system_diagnostics,
)
from src.ubp_bot.services.excel_reporter import (
    generate_excel_report,
    generate_gnb_rejected_report,
    generate_otc_rejected_report,
    sanitize_cell_value,
    save_workbook_safely,
)

__all__ = [
    "configure_portable_browsers_path",
    "verify_browser_runtime_available",
    "launch_persistent_browser_session",
    "get_active_browser_page",
    "close_browser_session",
    "close_all_browser_sessions",
    "format_diagnostics_report",
    "run_full_system_diagnostics",
    "sanitize_cell_value",
    "save_workbook_safely",
    "generate_otc_rejected_report",
    "generate_gnb_rejected_report",
    "generate_excel_report",
]
