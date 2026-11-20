"""Enterprise UI components and dashboard for UBP Bot."""

from src.ubp_bot.ui.dashboard import (
    create_desktop_dashboard,
    launch_dashboard,
    open_folder_in_explorer,
)
from src.ubp_bot.ui.dialogs import (
    browse_and_validate_directory,
    prompt_mandatory_directory_setup,
    show_diagnostics_dialog,
)

__all__ = [
    "create_desktop_dashboard",
    "launch_dashboard",
    "open_folder_in_explorer",
    "browse_and_validate_directory",
    "prompt_mandatory_directory_setup",
    "show_diagnostics_dialog",
]
