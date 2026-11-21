"""Enterprise dialogs and interactive directory selection pickers for UBP Bot.

Provides:
- Folder-browse dialogs with read/write permission verification
- Cancellation protection (preserves prior valid path when user cancels)
- First-launch mandatory directory setup modal
- System diagnostics report modal viewer
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, Optional, Tuple

from src.ubp_bot.core.config import (
    has_valid_directory_configuration,
    update_configured_directories,
    validate_directory_permissions,
)
from src.ubp_bot.services.diagnostics import (
    format_diagnostics_report,
    run_full_system_diagnostics,
)


def browse_and_validate_directory(
    parent: Optional[tk.Widget],
    title: str,
    current_path: Optional[str | Path] = None,
) -> Tuple[bool, Optional[Path]]:
    """Open an OS folder-picker dialog and validate read/write permissions.

    Cancelling selection preserves the previous valid path without alteration.

    Args:
        parent: Parent Tkinter widget or None.
        title: Dialog title bar text.
        current_path: Current valid folder path string or Path.

    Returns:
        Tuple[bool, Optional[Path]]: (is_changed_and_valid, resulting_path)
    """
    initial_dir = str(current_path) if current_path and Path(current_path).exists() else None
    chosen_str = filedialog.askdirectory(parent=parent, title=title, initialdir=initial_dir)

    # If user cancelled selection, return False and keep existing path
    if not chosen_str or not chosen_str.strip():
        return False, Path(current_path).resolve() if current_path else None

    chosen_path = Path(chosen_str).resolve()
    is_valid, reason = validate_directory_permissions(chosen_path)
    if not is_valid:
        messagebox.showerror(
            "Invalid Directory Selection",
            f"The selected folder cannot be used:\n\n{reason}\n\n"
            "Please ensure the folder exists and your Windows account has full Read and Write permissions.",
            parent=parent,
        )
        return False, Path(current_path).resolve() if current_path else None

    return True, chosen_path


def show_diagnostics_dialog(parent: tk.Tk, config_path: Optional[Path] = None) -> None:
    """Display a clean modal window containing full system pre-flight diagnostics."""
    diag_results = run_full_system_diagnostics(config_path)
    report_text = format_diagnostics_report(diag_results)

    diag_win = tk.Toplevel(parent)
    diag_win.title("UBP Bot — System Diagnostics")
    diag_win.geometry("720x560")
    diag_win.minsize(600, 400)
    diag_win.configure(bg="#F8FAFC")

    # Header frame
    head = tk.Frame(diag_win, bg="#0F4C81", padx=16, pady=12)
    head.pack(fill="x")
    tk.Label(
        head,
        text="Pre-Flight Environment & Runtime Diagnostics",
        font=("Segoe UI", 12, "bold"),
        fg="#FFFFFF",
        bg="#0F4C81",
    ).pack(side="left")

    status_color = "#D1FAE5" if diag_results["overall_status"] == "PASS" else "#FEE2E2"
    status_fg = "#065F46" if diag_results["overall_status"] == "PASS" else "#991B1B"
    tk.Label(
        head,
        text=f" Status: {diag_results['overall_status']} ",
        font=("Segoe UI", 10, "bold"),
        bg=status_color,
        fg=status_fg,
        padx=8,
        pady=2,
    ).pack(side="right")

    # Body frame
    body = tk.Frame(diag_win, bg="#F8FAFC", padx=16, pady=16)
    body.pack(fill="both", expand=True)

    text_frame = tk.Frame(body, bg="#FFFFFF", relief="solid", bd=1)
    text_frame.pack(fill="both", expand=True)

    scroll = ttk.Scrollbar(text_frame)
    scroll.pack(side="right", fill="y")

    txt = tk.Text(
        text_frame,
        font=("Consolas", 10),
        bg="#FFFFFF",
        fg="#0F172A",
        wrap="none",
        relief="flat",
        padx=12,
        pady=12,
        yscrollcommand=scroll.set,
    )
    txt.insert("end", report_text)
    txt.configure(state="disabled")
    txt.pack(side="left", fill="both", expand=True)
    scroll.config(command=txt.yview)

    # Close button
    btn_frame = tk.Frame(diag_win, bg="#F8FAFC", padx=16, pady=10)
    btn_frame.pack(fill="x")
    tk.Button(
        btn_frame,
        text="Close Diagnostics",
        font=("Segoe UI", 9, "bold"),
        bg="#E2E8F0",
        fg="#0F172A",
        padx=16,
        pady=6,
        relief="flat",
        cursor="hand2",
        command=diag_win.destroy,
    ).pack(side="right")


def prompt_mandatory_directory_setup(
    parent: tk.Tk,
    config: Dict[str, Any],
    config_path: Optional[Path] = None,
) -> bool:
    """Prompt user to select valid input and output directories on first launch.

    Args:
        parent: Root application window.
        config: Current configuration dictionary.
        config_path: Configuration file path.

    Returns:
        bool: True if directories are valid and saved; False if user exited without setup.
    """
    is_valid, _ = has_valid_directory_configuration(config)
    if is_valid:
        return True

    dirs = config.get("directories", {})
    in_dir = dirs.get("input_dir", "")
    out_dir = dirs.get("output_dir", "")

    setup_win = tk.Toplevel(parent)
    setup_win.title("UBP Bot — Mandatory Directory Setup")
    setup_win.geometry("640x360")
    setup_win.resizable(False, False)
    setup_win.configure(bg="#F8FAFC")
    setup_win.grab_set()

    # Title Banner
    head = tk.Frame(setup_win, bg="#0F4C81", padx=16, pady=12)
    head.pack(fill="x")
    tk.Label(
        head,
        text="First Launch: Working Directory Configuration",
        font=("Segoe UI", 11, "bold"),
        fg="#FFFFFF",
        bg="#0F4C81",
    ).pack(anchor="w")

    body = tk.Frame(setup_win, bg="#F8FAFC", padx=20, pady=16)
    body.pack(fill="both", expand=True)

    tk.Label(
        body,
        text=(
            "Welcome to UBP Bot. Before processing begins, please select valid, accessible\n"
            "folders for your daily input spreadsheets and generated rejected-transaction reports."
        ),
        font=("Segoe UI", 9),
        fg="#334155",
        bg="#F8FAFC",
        justify="left",
    ).pack(anchor="w", pady=(0, 16))

    # Input row
    tk.Label(body, text="Input Spreadsheet Folder:", font=("Segoe UI", 9, "bold"), fg="#0F172A", bg="#F8FAFC").pack(anchor="w")
    in_row = tk.Frame(body, bg="#F8FAFC")
    in_row.pack(fill="x", pady=(2, 10))

    in_var = tk.StringVar(value=in_dir)
    in_entry = tk.Entry(in_row, textvariable=in_var, font=("Consolas", 9), relief="solid", bd=1)
    in_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

    def on_browse_input():
        changed, p = browse_and_validate_directory(setup_win, "Select Input Spreadsheet Folder", in_var.get())
        if changed and p:
            in_var.set(str(p))

    tk.Button(in_row, text="Browse...", font=("Segoe UI", 8, "bold"), bg="#E2E8F0", command=on_browse_input).pack(side="right")

    # Output row
    tk.Label(body, text="Output Reports Folder:", font=("Segoe UI", 9, "bold"), fg="#0F172A", bg="#F8FAFC").pack(anchor="w")
    out_row = tk.Frame(body, bg="#F8FAFC")
    out_row.pack(fill="x", pady=(2, 16))

    out_var = tk.StringVar(value=out_dir)
    out_entry = tk.Entry(out_row, textvariable=out_var, font=("Consolas", 9), relief="solid", bd=1)
    out_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

    def on_browse_output():
        changed, p = browse_and_validate_directory(setup_win, "Select Output Reports Folder", out_var.get())
        if changed and p:
            out_var.set(str(p))

    tk.Button(out_row, text="Browse...", font=("Segoe UI", 8, "bold"), bg="#E2E8F0", command=on_browse_output).pack(side="right")

    status_var = tk.StringVar(value="")
    status_lbl = tk.Label(body, textvariable=status_var, font=("Segoe UI", 8, "bold"), fg="#E11D48", bg="#F8FAFC")
    status_lbl.pack(anchor="w")

    confirmed = False

    def on_save_and_continue():
        nonlocal confirmed
        in_path = in_var.get().strip()
        out_path = out_var.get().strip()

        if not in_path or not out_path:
            status_var.set("Both Input and Output directories must be selected.")
            return

        try:
            update_configured_directories(in_path, out_path, config_path)
            confirmed = True
            setup_win.destroy()
        except ValueError as exc:
            status_var.set(str(exc))

    btn_row = tk.Frame(setup_win, bg="#F8FAFC", padx=20, pady=12)
    btn_row.pack(fill="x")
    tk.Button(
        btn_row,
        text="Confirm & Start Bot",
        font=("Segoe UI", 9, "bold"),
        bg="#0F4C81",
        fg="#FFFFFF",
        padx=14,
        pady=6,
        relief="flat",
        cursor="hand2",
        command=on_save_and_continue,
    ).pack(side="right")

    parent.wait_window(setup_win)
    return confirmed
