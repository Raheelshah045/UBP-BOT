"""Desktop interface module for the OTC Bot using Tkinter.

Provides comprehensive status displays for Directory Monitoring, Portal Session,
Batch Processing, and actionable control buttons.
"""

import os
import subprocess
import threading
import tkinter as tk
import urllib.request
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Dict, Optional

from src.browser_manager import (
    close_browser_session,
    get_active_browser_page,
    launch_persistent_browser_session,
    navigate_browser_to,
)
from src.config import ensure_workspace_directories, load_config, save_config
from src.diagnostics import format_diagnostics_report, run_full_system_diagnostics
from src.logger import set_ui_log_callback
from src.queue_manager import (
    clear_processing_queue,
    execute_startup_scan,
    set_monitoring_state,
    set_processing_paused,
    start_continuous_monitoring_worker,
)


def open_folder_in_explorer(folder_path: Path) -> None:
    """Open the operating system file explorer at the specified directory path.

    Args:
        folder_path: Directory to display.
    """
    folder_path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(folder_path))
    else:
        subprocess.run(["xdg-open", str(folder_path)], check=False)


def create_desktop_app(config_path: Optional[Path] = None) -> tk.Tk:
    """Initialize and construct the updated desktop GUI application window.

    Args:
        config_path: Optional path to config.json.

    Returns:
        tk.Tk: Configured root Tk window.
    """
    config = load_config(config_path)
    ensure_workspace_directories()

    root = tk.Tk()
    root.title("OTC Transaction Monitoring & Rejection Extraction Bot")
    root.geometry("960x780")
    root.minsize(860, 680)
    root.configure(bg="#f1f5f9")

    style = ttk.Style()
    style.theme_use("clam")

    # Header Banner
    header_frame = tk.Frame(root, bg="#1B365D", height=60, padx=20, pady=12)
    header_frame.pack(fill="x")
    title_lbl = tk.Label(
        header_frame,
        text="OTC Bot",
        font=("Segoe UI", 15, "bold"),
        fg="white",
        bg="#1B365D",
    )
    title_lbl.pack(side="left")

    portal_auth_badge = tk.Label(
        header_frame,
        text="Portal: Initializing...",
        font=("Segoe UI", 9, "bold"),
        fg="#1B365D",
        bg="#E2E8F0",
        padx=10,
        pady=4,
    )
    portal_auth_badge.pack(side="right")

    def show_diagnostics_dialog() -> None:
        diag = run_full_system_diagnostics(config_path)
        report_text = format_diagnostics_report(diag)

        diag_win = tk.Toplevel(root)
        diag_win.title("System Diagnostics — Pre-flight Checks")
        diag_win.geometry("640x520")
        diag_win.minsize(540, 420)
        diag_win.configure(bg="#f8fafc")

        status_color = (
            "#166534"
            if diag["overall_status"] == "PASS"
            else ("#854D0E" if diag["overall_status"] == "WARN" else "#991B1B")
        )
        tk.Label(
            diag_win,
            text=f"Diagnostics Status: {diag['overall_status']}",
            font=("Segoe UI", 12, "bold"),
            fg=status_color,
            bg="#f8fafc",
            pady=8,
        ).pack(fill="x")

        txt_frame = tk.Frame(diag_win, padx=10, pady=6, bg="#f8fafc")
        txt_frame.pack(fill="both", expand=True)

        txt = tk.Text(txt_frame, font=("Consolas", 9), wrap="word", bg="#0F172A", fg="#38BDF8")
        scroll = ttk.Scrollbar(txt_frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)
        txt.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        txt.insert(tk.END, report_text)
        txt.configure(state="disabled")

        tk.Button(
            diag_win,
            text="Close",
            font=("Segoe UI", 9, "bold"),
            bg="#1B365D",
            fg="white",
            padx=16,
            pady=4,
            command=diag_win.destroy,
        ).pack(pady=8)

    btn_diag_header = tk.Button(
        header_frame,
        text="🩺 Diagnostics",
        font=("Segoe UI", 9, "bold"),
        bg="#0284C7",
        fg="white",
        padx=10,
        pady=3,
        command=show_diagnostics_dialog,
    )
    btn_diag_header.pack(side="right", padx=(0, 10))

    main_container = tk.Frame(root, bg="#f1f5f9", padx=16, pady=10)
    main_container.pack(fill="both", expand=True)

    # Section 0: System Portal URL Configuration (Single Entrypoint)
    url_card = tk.LabelFrame(
        main_container,
        text=" System Portal URL Configuration ",
        font=("Segoe UI", 10, "bold"),
        padx=12,
        pady=8,
        bg="white",
    )
    url_card.pack(fill="x", pady=(0, 8))

    url_grid = tk.Frame(url_card, bg="white")
    url_grid.pack(fill="x")

    login_url_val = config.get("portal", {}).get("login_url", "http://192.168.1.11:5173/")
    portal_url_var = tk.StringVar(value=login_url_val)

    tk.Label(url_grid, text="Portal URL:", font=("Segoe UI", 9, "bold"), bg="white").grid(
        row=0, column=0, sticky="w", pady=3
    )
    portal_entry = ttk.Entry(url_grid, textvariable=portal_url_var, width=65)
    portal_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8), pady=3)

    def on_save_urls() -> None:
        new_url = portal_url_var.get().strip()
        if not new_url:
            messagebox.showerror("Error", "Portal URL cannot be empty.")
            return

        config.setdefault("portal", {})
        config["portal"]["login_url"] = new_url
        config["portal"]["base_url"] = new_url
        save_config(config, config_path)
        url_status_lbl.configure(text=f"✓ Portal URL saved: {new_url}")
        append_log_line(f"[✓] System Portal URL updated -> {new_url}")

        # If browser is active, navigate immediately so user doesn't see a blank page
        page = get_active_browser_page()
        if page and not page.is_closed():
            append_log_line(f"[*] Navigating open browser window to: {new_url}...")
            navigate_browser_to(new_url)

    def on_test_open_portal() -> None:
        target_url = portal_url_var.get().strip()
        if not target_url:
            messagebox.showerror("Error", "Please enter a valid portal URL first.")
            return

        on_save_urls()
        append_log_line(f"[*] Checking portal reachability: {target_url}...")
        try:
            req = urllib.request.urlopen(target_url, timeout=3)
            append_log_line(f"[✓] Portal host is online (HTTP {req.status}). Opening browser...")
        except Exception as conn_err:
            append_log_line(f"[!] Network notice for {target_url}: {conn_err}")
            append_log_line("    (Tip: If running locally, check if 'http://localhost:5173/' should be used)")

        _, _, page = launch_persistent_browser_session(config.get("browser", {}), initial_url=target_url)
        if page and not page.is_closed():
            navigate_browser_to(target_url)
            append_log_line(f"[✓] Active browser is viewing: {target_url}")

    btn_box = tk.Frame(url_grid, bg="white")
    btn_box.grid(row=0, column=2, padx=(6, 0), sticky="e")

    btn_save_url = tk.Button(
        btn_box,
        text="💾 Save & Apply",
        font=("Segoe UI", 9, "bold"),
        bg="#1B365D",
        fg="white",
        padx=10,
        pady=4,
        command=on_save_urls,
    )
    btn_save_url.pack(side="left", padx=(0, 4))

    btn_open_portal = tk.Button(
        btn_box,
        text="🌐 Open Portal",
        font=("Segoe UI", 9, "bold"),
        bg="#0284C7",
        fg="white",
        padx=10,
        pady=4,
        command=on_test_open_portal,
    )
    btn_open_portal.pack(side="left")

    url_status_lbl = tk.Label(
        url_grid,
        text="Enter the main portal URL. The bot will automatically inspect the screen and navigate.",
        font=("Segoe UI", 8, "italic"),
        fg="#475569",
        bg="white",
    )
    url_status_lbl.grid(row=1, column=1, sticky="w", padx=8, pady=(2, 0))
    url_grid.columnconfigure(1, weight=1)

    # Section 1: Directory Monitoring & Queue Panel
    dir_card = tk.LabelFrame(
        main_container,
        text=" Directory Monitoring & Queue Status ",
        font=("Segoe UI", 10, "bold"),
        padx=12,
        pady=8,
        bg="white",
    )
    dir_card.pack(fill="x", pady=(0, 8))

    dir_grid = tk.Frame(dir_card, bg="white")
    dir_grid.pack(fill="x")

    monitored_dir_var = tk.StringVar(
        value=str(Path(config.get("directories", {}).get("input_dir", "input")).resolve())
    )
    monitoring_status_var = tk.StringVar(value="Standby / Inactive")
    queue_count_var = tk.StringVar(value="0")
    current_file_var = tk.StringVar(value="None")

    tk.Label(dir_grid, text="Monitored Folder:", font=("Segoe UI", 9, "bold"), bg="white").grid(
        row=0, column=0, sticky="w", pady=2
    )
    tk.Label(
        dir_grid, textvariable=monitored_dir_var, font=("Segoe UI", 9), fg="#2563EB", bg="white"
    ).grid(row=0, column=1, sticky="w", padx=8, pady=2)

    tk.Label(dir_grid, text="Watcher State:", font=("Segoe UI", 9, "bold"), bg="white").grid(
        row=0, column=2, sticky="w", padx=(16, 0), pady=2
    )
    tk.Label(
        dir_grid,
        textvariable=monitoring_status_var,
        font=("Segoe UI", 9, "bold"),
        fg="#16A34A",
        bg="white",
    ).grid(row=0, column=3, sticky="w", padx=8, pady=2)

    tk.Label(dir_grid, text="Files in Queue:", font=("Segoe UI", 9, "bold"), bg="white").grid(
        row=1, column=0, sticky="w", pady=2
    )
    tk.Label(
        dir_grid,
        textvariable=queue_count_var,
        font=("Segoe UI", 9, "bold"),
        fg="#D97706",
        bg="white",
    ).grid(row=1, column=1, sticky="w", padx=8, pady=2)

    tk.Label(dir_grid, text="Active File:", font=("Segoe UI", 9, "bold"), bg="white").grid(
        row=1, column=2, sticky="w", padx=(16, 0), pady=2
    )
    tk.Label(
        dir_grid,
        textvariable=current_file_var,
        font=("Segoe UI", 9, "bold"),
        fg="#4F46E5",
        bg="white",
    ).grid(row=1, column=3, sticky="w", padx=8, pady=2)

    # Section 2: Browser & Portal Session Status
    session_card = tk.LabelFrame(
        main_container,
        text=" Portal Session & State Detection ",
        font=("Segoe UI", 10, "bold"),
        padx=12,
        pady=8,
        bg="white",
    )
    session_card.pack(fill="x", pady=(0, 8))

    sess_grid = tk.Frame(session_card, bg="white")
    sess_grid.pack(fill="x")

    browser_status_var = tk.StringVar(value="Profile Ready")
    portal_page_var = tk.StringVar(value="Standby")

    tk.Label(sess_grid, text="Browser Engine:", font=("Segoe UI", 9, "bold"), bg="white").grid(
        row=0, column=0, sticky="w", pady=2
    )
    tk.Label(
        sess_grid, textvariable=browser_status_var, font=("Segoe UI", 9), fg="#0F172A", bg="white"
    ).grid(row=0, column=1, sticky="w", padx=8, pady=2)

    tk.Label(sess_grid, text="Current Screen:", font=("Segoe UI", 9, "bold"), bg="white").grid(
        row=0, column=2, sticky="w", padx=(16, 0), pady=2
    )
    tk.Label(
        sess_grid,
        textvariable=portal_page_var,
        font=("Segoe UI", 9, "bold"),
        fg="#2563EB",
        bg="white",
    ).grid(row=0, column=3, sticky="w", padx=8, pady=2)

    # Section 3: Action Controls
    ctrl_frame = tk.Frame(main_container, bg="#f1f5f9")
    ctrl_frame.pack(fill="x", pady=(0, 8))

    btn_start_mon = tk.Button(
        ctrl_frame,
        text="▶ Start Monitoring",
        font=("Segoe UI", 9, "bold"),
        bg="#1B365D",
        fg="white",
        padx=10,
        pady=5,
    )
    btn_start_mon.pack(side="left", padx=(0, 6))

    btn_stop_mon = tk.Button(
        ctrl_frame,
        text="⏹ Stop Monitoring",
        font=("Segoe UI", 9),
        bg="#DC2626",
        fg="white",
        padx=10,
        pady=5,
        state="disabled",
    )
    btn_stop_mon.pack(side="left", padx=4)

    btn_pause = tk.Button(
        ctrl_frame,
        text="⏸ Pause",
        font=("Segoe UI", 9),
        bg="#D97706",
        fg="white",
        padx=10,
        pady=5,
        state="disabled",
    )
    btn_pause.pack(side="left", padx=4)

    btn_resume = tk.Button(
        ctrl_frame,
        text="▶ Resume",
        font=("Segoe UI", 9),
        bg="#059669",
        fg="white",
        padx=10,
        pady=5,
        state="disabled",
    )
    btn_resume.pack(side="left", padx=4)

    dirs_cfg = config.get("directories", {})
    input_folder_path = Path(dirs_cfg.get("input_dir", "input")).resolve()
    output_folder_path = Path(dirs_cfg.get("output_dir", "output")).resolve()

    btn_open_in = tk.Button(
        ctrl_frame,
        text="📂 Open Input",
        font=("Segoe UI", 9),
        bg="#E2E8F0",
        fg="#1E293B",
        padx=8,
        pady=5,
        command=lambda: open_folder_in_explorer(input_folder_path),
    )
    btn_open_in.pack(side="left", padx=4)

    btn_open_out = tk.Button(
        ctrl_frame,
        text="📂 Open Output",
        font=("Segoe UI", 9),
        bg="#E2E8F0",
        fg="#1E293B",
        padx=8,
        pady=5,
        command=lambda: open_folder_in_explorer(output_folder_path),
    )
    btn_open_out.pack(side="left", padx=4)

    def trigger_gnb_extraction() -> None:
        def worker() -> None:
            try:
                from src.excel_reporter import generate_gnb_rejected_report
                from src.gnb_client import run_gnb_extraction_pipeline

                txs = run_gnb_extraction_pipeline(config, on_message=lambda msg: append_log_line(f"[GNB] {msg}"))
                rep = generate_gnb_rejected_report(output_folder_path, txs)
                append_log_line(f"[GNB] SUCCESS: Report generated at {rep.name}")
                messagebox.showinfo("GNB Extraction", f"GNB Rejected Transactions saved to:\n{rep.name}")
            except Exception as exc:
                append_log_line(f"[GNB] ERROR: {exc}")
                messagebox.showerror("GNB Extraction Error", str(exc))

        threading.Thread(target=worker, daemon=True).start()

    btn_gnb = tk.Button(
        ctrl_frame,
        text="🏦 Extract GNB",
        font=("Segoe UI", 9, "bold"),
        bg="#0F5132",
        fg="white",
        padx=8,
        pady=5,
        command=trigger_gnb_extraction,
    )
    btn_gnb.pack(side="left", padx=4)

    btn_reprocess = tk.Button(
        ctrl_frame,
        text="🔁 Re-process Input",
        font=("Segoe UI", 9),
        bg="#E2E8F0",
        fg="#1E293B",
        padx=8,
        pady=5,
    )
    btn_reprocess.pack(side="left", padx=4)

    btn_reconnect = tk.Button(
        ctrl_frame,
        text="🔄 Reconnect Browser",
        font=("Segoe UI", 9),
        bg="#E2E8F0",
        fg="#1E293B",
        padx=8,
        pady=5,
    )
    btn_reconnect.pack(side="right", padx=2)

    # Section 4: Real-time Processing Metrics
    stats_card = tk.LabelFrame(
        main_container,
        text=" Batch Record Statistics ",
        font=("Segoe UI", 10, "bold"),
        padx=10,
        pady=6,
        bg="white",
    )
    stats_card.pack(fill="x", pady=(0, 8))

    progress_bar = ttk.Progressbar(stats_card, orient="horizontal", mode="determinate")
    progress_bar.pack(fill="x", pady=(0, 6))

    metrics_frame = tk.Frame(stats_card, bg="white")
    metrics_frame.pack(fill="x")

    def make_stat_box(parent: tk.Frame, label_text: str, default_val: str = "0") -> tk.StringVar:
        box = tk.Frame(parent, bg="#F8FAFC", padx=8, pady=4, relief="ridge", bd=1)
        box.pack(side="left", expand=True, fill="both", padx=3)
        var = tk.StringVar(value=default_val)
        tk.Label(
            box, textvariable=var, font=("Segoe UI", 11, "bold"), fg="#1E293B", bg="#F8FAFC"
        ).pack()
        tk.Label(box, text=label_text, font=("Segoe UI", 8), fg="#64748B", bg="#F8FAFC").pack()
        return var

    total_var = make_stat_box(metrics_frame, "Total Rows")
    processed_var = make_stat_box(metrics_frame, "Processed")
    curr_row_var = make_stat_box(metrics_frame, "Current Row", "-")
    _rej_var = make_stat_box(metrics_frame, "Qualifying Rejections")
    _appr_var = make_stat_box(metrics_frame, "Approved")
    _err_var = make_stat_box(metrics_frame, "Errors")

    # Section 5: Live Execution Logs Console
    log_card = tk.LabelFrame(
        main_container,
        text=" Continuous Event Log ",
        font=("Segoe UI", 10, "bold"),
        padx=6,
        pady=4,
        bg="white",
    )
    log_card.pack(fill="both", expand=True)

    log_text = tk.Text(
        log_card, bg="#0F172A", fg="#38BDF8", font=("Consolas", 9), wrap="word", height=9
    )
    log_scroll = ttk.Scrollbar(log_card, orient="vertical", command=log_text.yview)
    log_text.configure(yscrollcommand=log_scroll.set)
    log_text.pack(side="left", fill="both", expand=True)
    log_scroll.pack(side="right", fill="y")

    def append_log_line(message: str) -> None:
        def _insert() -> None:
            log_text.insert(tk.END, message + "\n")
            log_text.see(tk.END)

        root.after(0, _insert)

    set_ui_log_callback(append_log_line)

    # Worker Thread Handling
    def on_start_monitoring() -> None:
        on_save_urls()
        btn_start_mon.configure(state="disabled")
        btn_stop_mon.configure(state="normal")
        btn_pause.configure(state="normal")
        btn_resume.configure(state="disabled")
        monitoring_status_var.set("Active (Watching)")

        def update_queue(count: int, filename: str) -> None:
            root.after(0, lambda: [queue_count_var.set(str(count)), current_file_var.set(filename)])

        def update_progress(data: Dict[str, Any]) -> None:
            total = data.get("total_rows", 1)
            proc = data.get("processed_count", 0)
            cur = data.get("current_row", 0)
            root.after(
                0,
                lambda: [
                    total_var.set(str(total)),
                    processed_var.set(str(proc)),
                    curr_row_var.set(str(cur)),
                    progress_bar.configure(maximum=total, value=proc),
                ],
            )

        def update_status_msg(msg: str) -> None:
            append_log_line(f"[*] {msg}")

        def update_portal_state(state_str: str) -> None:
            root.after(
                0,
                lambda: [
                    portal_page_var.set(state_str),
                    portal_auth_badge.configure(
                        text=f"Portal: {state_str}",
                        bg="#DCFCE7" if "Active" in state_str else "#FEF9C3",
                        fg="#166534" if "Active" in state_str else "#854D0E",
                    ),
                ],
            )

        thread = threading.Thread(
            target=start_continuous_monitoring_worker,
            args=(config, update_queue, update_progress, update_status_msg, update_portal_state),
            daemon=True,
        )
        thread.start()

    def on_stop_monitoring() -> None:
        set_monitoring_state(False)
        btn_start_mon.configure(state="normal")
        btn_stop_mon.configure(state="disabled")
        btn_pause.configure(state="disabled")
        btn_resume.configure(state="disabled")
        monitoring_status_var.set("Stopped")
        append_log_line("[x] Continuous monitoring stopped by user.")

    def on_pause() -> None:
        set_processing_paused(True)
        btn_pause.configure(state="disabled")
        btn_resume.configure(state="normal")
        append_log_line("[!] File processing PAUSED.")

    def on_resume() -> None:
        set_processing_paused(False)
        btn_pause.configure(state="normal")
        btn_resume.configure(state="disabled")
        append_log_line("[>] File processing RESUMED.")

    def on_reprocess_input() -> None:
        clear_processing_queue()
        dirs_c = config.get("directories", {})
        in_p = Path(dirs_c.get("input_dir", "input"))
        db_p = Path(
            config.get("storage", {}).get(
                "checkpoint_db_path", "checkpoints/processing_checkpoint.db"
            )
        )
        append_log_line("[🔁] Cleared queue and re-scanning input folder...")
        enqueued_items = execute_startup_scan(in_p, db_p, force_reprocess=True)
        append_log_line(f"[✓] Enqueued {len(enqueued_items)} file(s) for immediate processing.")

    def on_reconnect_browser() -> None:
        on_save_urls()
        target_url = portal_url_var.get().strip()
        append_log_line(f"[🔄] Reconnecting browser session to {target_url}...")
        close_browser_session()
        _, _, page = launch_persistent_browser_session(config.get("browser", {}), initial_url=target_url)
        if page and not page.is_closed():
            navigate_browser_to(target_url)
        append_log_line("[✓] Browser session re-initialized and loaded portal.")

    btn_start_mon.configure(command=on_start_monitoring)
    btn_stop_mon.configure(command=on_stop_monitoring)
    btn_pause.configure(command=on_pause)
    btn_resume.configure(command=on_resume)
    btn_reprocess.configure(command=on_reprocess_input)
    btn_reconnect.configure(command=on_reconnect_browser)

    return root


def launch_gui(config_path: Optional[Path] = None) -> None:
    """Entry point function to launch the desktop Tkinter user interface.

    Args:
        config_path: Optional configuration JSON path.
    """
    app = create_desktop_app(config_path)
    app.mainloop()
