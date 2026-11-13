"""Modern desktop operations dashboard for UBP Bot (Phase 1 Dual-System Operations).

Provides a clean, professional banking operations interface:
- Dual-system portal configuration (OTC and GNB side-by-side with independent URLs)
- Independent parallel browser sessions and extraction execution
- Clear real-time status indicators and progress metrics
- Direct workspace access (Input, Output, Logs)
- Distinct visual styling with modern light enterprise aesthetic
"""

import os
import subprocess
import threading
import tkinter as tk
import urllib.request
from pathlib import Path
from tkinter import ttk
from typing import Any, Dict, Optional

from src.browser_manager import (
    launch_persistent_browser_session,
)
from src.config import ensure_workspace_directories, load_config, save_config
from src.diagnostics import format_diagnostics_report, run_full_system_diagnostics
from src.excel_reporter import generate_gnb_rejected_report
from src.gnb_client import run_gnb_extraction_pipeline
from src.logger import set_ui_log_callback
from src.queue_manager import (
    set_monitoring_state,
    start_continuous_monitoring_worker,
)


def open_folder_in_explorer(folder_path: Path) -> None:
    """Open operating system file explorer at folder path."""
    folder_path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(folder_path))
    else:
        subprocess.run(["xdg-open", str(folder_path)], check=False)


def check_url_reachability(url: str, timeout_seconds: float = 3.0) -> bool:
    """Check if URL returns an HTTP response without hanging."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) UBP-Bot/2.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return resp.status < 500
    except Exception:
        return False


def create_desktop_app(config_path: Optional[Path] = None) -> tk.Tk:
    """Initialize and construct the UBP Bot dual-system operations window."""
    config = load_config(config_path)
    ensure_workspace_directories()

    root = tk.Tk()
    root.title("UBP Bot — Operations Dashboard (Phase 1)")
    root.geometry("1060x860")
    root.minsize(980, 750)
    root.configure(bg="#F8FAFC")

    # Theme & Colors
    BG_MAIN = "#F8FAFC"
    BG_CARD = "#FFFFFF"
    BORDER_COLOR = "#E2E8F0"
    TEXT_MAIN = "#0F172A"
    TEXT_MUTED = "#64748B"
    PRIMARY_COLOR = "#0F4C81"  # Banking Navy
    SUCCESS_COLOR = "#0D9488"  # Teal Green
    DANGER_COLOR = "#E11D48"   # Rose Red

    style = ttk.Style()
    style.theme_use("clam")
    style.configure(
        "TProgressbar",
        troughcolor="#E2E8F0",
        background=PRIMARY_COLOR,
        thickness=10,
    )

    # 1. HEADER BANNER
    header_frame = tk.Frame(root, bg=PRIMARY_COLOR, height=64, padx=24, pady=12)
    header_frame.pack(fill="x")

    title_box = tk.Frame(header_frame, bg=PRIMARY_COLOR)
    title_box.pack(side="left")

    title_lbl = tk.Label(
        title_box,
        text="UBP Bot",
        font=("Segoe UI", 16, "bold"),
        fg="#FFFFFF",
        bg=PRIMARY_COLOR,
    )
    title_lbl.pack(side="left")

    phase_lbl = tk.Label(
        title_box,
        text="  PHASE 1: TRANSACTION EXTRACTION  ",
        font=("Segoe UI", 8, "bold"),
        fg="#E0F2FE",
        bg="#0369A1",
        padx=8,
        pady=3,
    )
    phase_lbl.pack(side="left", padx=12)

    header_right = tk.Frame(header_frame, bg=PRIMARY_COLOR)
    header_right.pack(side="right")

    global_status_badge = tk.Label(
        header_right,
        text="System Ready",
        font=("Segoe UI", 9, "bold"),
        fg="#065F46",
        bg="#D1FAE5",
        padx=12,
        pady=4,
    )
    global_status_badge.pack(side="right")

    # MAIN SCROLLABLE OR STRUCTURED CONTAINER
    main_container = tk.Frame(root, bg=BG_MAIN, padx=20, pady=16)
    main_container.pack(fill="both", expand=True)

    # 2. DUAL-SYSTEM PORTAL CONFIGURATION (SIDE-BY-SIDE CARDS)
    portals_frame = tk.Frame(main_container, bg=BG_MAIN)
    portals_frame.pack(fill="x", pady=(0, 14))

    # --- OTC Portal Card (Left) ---
    otc_card = tk.LabelFrame(
        portals_frame,
        text="  OTC System Portal (Manual Login)  ",
        font=("Segoe UI", 10, "bold"),
        fg=TEXT_MAIN,
        bg=BG_CARD,
        padx=16,
        pady=12,
        relief="solid",
        bd=1,
    )
    otc_card.pack(side="left", fill="both", expand=True, padx=(0, 8))

    otc_url_var = tk.StringVar(value=config.get("portal", {}).get("login_url", "http://localhost:5173/"))
    otc_auth_var = tk.StringVar(value="Waiting Authentication")
    otc_proc_var = tk.StringVar(value="Idle")

    tk.Label(otc_card, text="OTC Portal URL:", font=("Segoe UI", 9, "bold"), fg=TEXT_MUTED, bg=BG_CARD).pack(anchor="w")
    otc_url_entry = tk.Entry(
        otc_card,
        textvariable=otc_url_var,
        font=("Consolas", 9),
        bg="#F8FAFC",
        fg=TEXT_MAIN,
        relief="solid",
        bd=1,
    )
    otc_url_entry.pack(fill="x", pady=(4, 8))

    otc_status_row = tk.Frame(otc_card, bg=BG_CARD)
    otc_status_row.pack(fill="x", pady=(0, 10))

    tk.Label(otc_status_row, text="Auth:", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=BG_CARD).pack(side="left")
    otc_auth_badge = tk.Label(
        otc_status_row,
        textvariable=otc_auth_var,
        font=("Segoe UI", 8, "bold"),
        fg="#854D0E",
        bg="#FEF9C3",
        padx=6,
        pady=2,
    )
    otc_auth_badge.pack(side="left", padx=(4, 12))

    tk.Label(otc_status_row, text="Task:", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=BG_CARD).pack(side="left")
    otc_task_badge = tk.Label(
        otc_status_row,
        textvariable=otc_proc_var,
        font=("Segoe UI", 8, "bold"),
        fg="#1E293B",
        bg="#E2E8F0",
        padx=6,
        pady=2,
    )
    otc_task_badge.pack(side="left", padx=4)

    otc_btns_frame = tk.Frame(otc_card, bg=BG_CARD)
    otc_btns_frame.pack(fill="x")

    def on_save_otc_url() -> None:
        new_url = otc_url_var.get().strip()
        config.setdefault("portal", {})["login_url"] = new_url
        config["portal"]["base_url"] = new_url
        save_config(config)
        append_log_line(f"[OTC] Saved URL: {new_url}")

    def on_open_otc() -> None:
        on_save_otc_url()
        url = otc_url_var.get().strip()
        append_log_line(f"[OTC] Opening browser window to {url}...")
        threading.Thread(
            target=lambda: launch_persistent_browser_session(config.get("browser", {}), initial_url=url, system_name="otc"),
            daemon=True,
        ).start()

    btn_save_otc = tk.Button(
        otc_btns_frame,
        text="Save URL",
        font=("Segoe UI", 8, "bold"),
        bg="#E2E8F0",
        fg=TEXT_MAIN,
        padx=10,
        pady=4,
        relief="flat",
        cursor="hand2",
        command=on_save_otc_url,
    )
    btn_save_otc.pack(side="left", padx=(0, 6))

    btn_open_otc = tk.Button(
        otc_btns_frame,
        text="🌐 Open OTC Portal",
        font=("Segoe UI", 8, "bold"),
        bg="#EFF6FF",
        fg=PRIMARY_COLOR,
        padx=10,
        pady=4,
        relief="flat",
        cursor="hand2",
        command=on_open_otc,
    )
    btn_open_otc.pack(side="left")

    # --- GNB Portal Card (Right) ---
    gnb_card = tk.LabelFrame(
        portals_frame,
        text="  GNB System Portal (Automated Login)  ",
        font=("Segoe UI", 10, "bold"),
        fg=TEXT_MAIN,
        bg=BG_CARD,
        padx=16,
        pady=12,
        relief="solid",
        bd=1,
    )
    gnb_card.pack(side="right", fill="both", expand=True, padx=(8, 0))

    gnb_url_var = tk.StringVar(value=config.get("gnb", {}).get("login_url", "http://127.0.0.1:8080/gnb/login"))
    gnb_auth_var = tk.StringVar(value="Waiting Authentication")
    gnb_proc_var = tk.StringVar(value="Idle")

    tk.Label(gnb_card, text="GNB Portal URL:", font=("Segoe UI", 9, "bold"), fg=TEXT_MUTED, bg=BG_CARD).pack(anchor="w")
    gnb_url_entry = tk.Entry(
        gnb_card,
        textvariable=gnb_url_var,
        font=("Consolas", 9),
        bg="#F8FAFC",
        fg=TEXT_MAIN,
        relief="solid",
        bd=1,
    )
    gnb_url_entry.pack(fill="x", pady=(4, 8))

    gnb_status_row = tk.Frame(gnb_card, bg=BG_CARD)
    gnb_status_row.pack(fill="x", pady=(0, 10))

    tk.Label(gnb_status_row, text="Auth:", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=BG_CARD).pack(side="left")
    gnb_auth_badge = tk.Label(
        gnb_status_row,
        textvariable=gnb_auth_var,
        font=("Segoe UI", 8, "bold"),
        fg="#854D0E",
        bg="#FEF9C3",
        padx=6,
        pady=2,
    )
    gnb_auth_badge.pack(side="left", padx=(4, 12))

    tk.Label(gnb_status_row, text="Task:", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=BG_CARD).pack(side="left")
    gnb_task_badge = tk.Label(
        gnb_status_row,
        textvariable=gnb_proc_var,
        font=("Segoe UI", 8, "bold"),
        fg="#1E293B",
        bg="#E2E8F0",
        padx=6,
        pady=2,
    )
    gnb_task_badge.pack(side="left", padx=4)

    gnb_btns_frame = tk.Frame(gnb_card, bg=BG_CARD)
    gnb_btns_frame.pack(fill="x")

    def on_save_gnb_url() -> None:
        new_url = gnb_url_var.get().strip()
        config.setdefault("gnb", {})["login_url"] = new_url
        # Also sync rejected_transactions_url so it doesn't default to hardcoded mock port 8080 subpath
        config["gnb"]["rejected_transactions_url"] = new_url
        save_config(config)
        append_log_line(f"[GNB] Saved URL: {new_url}")

    def on_open_gnb() -> None:
        on_save_gnb_url()
        url = gnb_url_var.get().strip()
        append_log_line(f"[GNB] Opening independent browser session for GNB: {url}...")
        threading.Thread(
            target=lambda: launch_persistent_browser_session(config.get("browser", {}), initial_url=url, system_name="gnb"),
            daemon=True,
        ).start()

    btn_save_gnb = tk.Button(
        gnb_btns_frame,
        text="Save URL",
        font=("Segoe UI", 8, "bold"),
        bg="#E2E8F0",
        fg=TEXT_MAIN,
        padx=10,
        pady=4,
        relief="flat",
        cursor="hand2",
        command=on_save_gnb_url,
    )
    btn_save_gnb.pack(side="left", padx=(0, 6))

    btn_open_gnb = tk.Button(
        gnb_btns_frame,
        text="🏦 Open GNB Portal",
        font=("Segoe UI", 8, "bold"),
        bg="#F0FDF4",
        fg="#166534",
        padx=10,
        pady=4,
        relief="flat",
        cursor="hand2",
        command=on_open_gnb,
    )
    btn_open_gnb.pack(side="left")

    # 3. WORKSPACE & CONTROLS FRAME
    action_panel = tk.Frame(main_container, bg=BG_CARD, padx=16, pady=12, relief="solid", bd=1)
    action_panel.pack(fill="x", pady=(0, 14))

    # Top Row of Action Panel: Workspace Folder Shortcuts
    workspace_row = tk.Frame(action_panel, bg=BG_CARD)
    workspace_row.pack(fill="x", pady=(0, 10))

    tk.Label(workspace_row, text="Workspace Folders:", font=("Segoe UI", 9, "bold"), fg=TEXT_MUTED, bg=BG_CARD).pack(side="left", padx=(0, 10))

    dirs_cfg = config.get("directories", {})
    input_folder_path = Path(dirs_cfg.get("input_dir", "input")).resolve()
    output_folder_path = Path(dirs_cfg.get("output_dir", "output")).resolve()
    logs_folder_path = Path(dirs_cfg.get("logs_dir", "logs")).resolve()

    def make_btn(parent, text, cmd, bg_color="#E2E8F0", fg_color=TEXT_MAIN):
        return tk.Button(
            parent,
            text=text,
            font=("Segoe UI", 9, "bold"),
            bg=bg_color,
            fg=fg_color,
            padx=12,
            pady=6,
            relief="flat",
            cursor="hand2",
            command=cmd,
        )

    btn_in = make_btn(workspace_row, "📂 Input Folder", lambda: open_folder_in_explorer(input_folder_path))
    btn_in.pack(side="left", padx=4)

    btn_out = make_btn(workspace_row, "📊 Output Folder", lambda: open_folder_in_explorer(output_folder_path))
    btn_out.pack(side="left", padx=4)

    btn_logs = make_btn(workspace_row, "📜 Logs Folder", lambda: open_folder_in_explorer(logs_folder_path))
    btn_logs.pack(side="left", padx=4)

    # Diagnostics Button
    def show_diagnostics() -> None:
        diag = run_full_system_diagnostics(config_path)
        report_text = format_diagnostics_report(diag)
        diag_win = tk.Toplevel(root)
        diag_win.title("UBP Bot — System Diagnostics")
        diag_win.geometry("640x520")
        diag_win.configure(bg="#F8FAFC")
        txt = tk.Text(diag_win, font=("Consolas", 10), bg="#FFFFFF", fg=TEXT_MAIN, padx=12, pady=12)
        txt.insert("end", report_text)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True, padx=14, pady=14)

    btn_diag = make_btn(workspace_row, "🔍 System Diagnostics", show_diagnostics, bg_color="#F1F5F9", fg_color=TEXT_MUTED)
    btn_diag.pack(side="right")

    # Divider
    tk.Frame(action_panel, bg=BORDER_COLOR, height=1).pack(fill="x", pady=6)

    # Bottom Row of Action Panel: Main Operations Buttons
    ops_row = tk.Frame(action_panel, bg=BG_CARD)
    ops_row.pack(fill="x", pady=(4, 0))

    tk.Label(ops_row, text="Execution Controls:", font=("Segoe UI", 9, "bold"), fg=TEXT_MUTED, bg=BG_CARD).pack(side="left", padx=(0, 10))

    # Operational status tracking
    is_otc_running = False
    is_gnb_running = False

    def update_global_badge():
        if is_otc_running and is_gnb_running:
            global_status_badge.configure(text="Running Both Systems", bg="#E0F2FE", fg="#0369A1")
        elif is_otc_running:
            global_status_badge.configure(text="OTC Active", bg="#E0F2FE", fg="#0369A1")
        elif is_gnb_running:
            global_status_badge.configure(text="GNB Active", bg="#D1FAE5", fg="#065F46")
        else:
            global_status_badge.configure(text="System Ready", bg="#D1FAE5", fg="#065F46")

    # OTC Handlers
    def start_otc_worker() -> None:
        nonlocal is_otc_running
        if is_otc_running:
            return
        is_otc_running = True
        update_global_badge()
        otc_proc_var.set("Monitoring & Extracting")
        otc_task_badge.configure(bg="#E0F2FE", fg="#0369A1")
        btn_start_otc.configure(state="disabled")
        btn_stop_otc.configure(state="normal")
        set_monitoring_state(True)

        def update_queue(q_count: int, cur_file: str = "") -> None:
            pass

        def update_progress(data: Dict[str, Any]) -> None:
            tot = data.get("total_rows", 1)
            prc = data.get("processed_count", 0)
            progress_bar.configure(maximum=tot, value=prc)

        def update_portal_state(state_str: str) -> None:
            root.after(0, lambda: otc_auth_var.set(state_str))

        append_log_line("[OTC] Continuous monitoring and extraction started.")
        threading.Thread(
            target=start_continuous_monitoring_worker,
            args=(config, update_queue, update_progress, append_log_line, update_portal_state),
            daemon=True,
        ).start()

    def stop_otc_worker() -> None:
        nonlocal is_otc_running
        set_monitoring_state(False)
        is_otc_running = False
        update_global_badge()
        otc_proc_var.set("Stopped")
        otc_task_badge.configure(bg="#E2E8F0", fg="#1E293B")
        btn_start_otc.configure(state="normal")
        btn_stop_otc.configure(state="disabled")
        append_log_line("[OTC] Monitoring stopped by user.")

    # GNB Handlers
    def start_gnb_worker() -> None:
        nonlocal is_gnb_running
        if is_gnb_running:
            return
        is_gnb_running = True
        update_global_badge()
        gnb_proc_var.set("Extracting")
        gnb_task_badge.configure(bg="#D1FAE5", fg="#065F46")
        btn_start_gnb.configure(state="disabled")
        btn_stop_gnb.configure(state="normal")

        def worker():
            nonlocal is_gnb_running
            try:
                append_log_line("[GNB] Launching independent GNB extraction pipeline...")
                gnb_auth_var.set("Authenticating...")
                txs = run_gnb_extraction_pipeline(
                    config,
                    on_message=lambda msg: append_log_line(f"[GNB] {msg}"),
                    keep_browser_open=True,
                )
                gnb_auth_var.set("Authenticated")
                out_p = Path(config.get("directories", {}).get("output_dir", "output"))
                rep = generate_gnb_rejected_report(out_p, txs)
                gnb_proc_var.set(f"Completed ({len(txs)})")
                append_log_line(f"[GNB] Report generated: {rep.name} ({len(txs)} rejections)")
            except Exception as exc:
                gnb_proc_var.set("Error")
                append_log_line(f"[GNB] Extraction failed: {exc}")
            finally:
                is_gnb_running = False
                root.after(0, lambda: [
                    btn_start_gnb.configure(state="normal"),
                    btn_stop_gnb.configure(state="disabled"),
                    update_global_badge(),
                ])

        threading.Thread(target=worker, daemon=True).start()

    def stop_gnb_worker() -> None:
        nonlocal is_gnb_running
        is_gnb_running = False
        update_global_badge()
        gnb_proc_var.set("Stopped")
        btn_start_gnb.configure(state="normal")
        btn_stop_gnb.configure(state="disabled")
        append_log_line("[GNB] Extraction cancelled.")

    def run_both_systems() -> None:
        append_log_line("[*] Launching BOTH systems concurrently in isolated pipelines...")
        start_otc_worker()
        start_gnb_worker()

    btn_start_otc = make_btn(ops_row, "▶ Start OTC", start_otc_worker, bg_color=PRIMARY_COLOR, fg_color="#FFFFFF")
    btn_start_otc.pack(side="left", padx=4)

    btn_stop_otc = make_btn(ops_row, "⏹ Stop OTC", stop_otc_worker, bg_color=DANGER_COLOR, fg_color="#FFFFFF")
    btn_stop_otc.configure(state="disabled")
    btn_stop_otc.pack(side="left", padx=4)

    btn_start_gnb = make_btn(ops_row, "▶ Start GNB", start_gnb_worker, bg_color=SUCCESS_COLOR, fg_color="#FFFFFF")
    btn_start_gnb.pack(side="left", padx=4)

    btn_stop_gnb = make_btn(ops_row, "⏹ Stop GNB", stop_gnb_worker, bg_color=DANGER_COLOR, fg_color="#FFFFFF")
    btn_stop_gnb.configure(state="disabled")
    btn_stop_gnb.pack(side="left", padx=4)

    btn_run_both = make_btn(ops_row, "⚡ Run Both Simultaneously", run_both_systems, bg_color="#4F46E5", fg_color="#FFFFFF")
    btn_run_both.pack(side="left", padx=(12, 4))

    # 4. PROGRESS BAR
    prog_frame = tk.Frame(main_container, bg=BG_MAIN)
    prog_frame.pack(fill="x", pady=(0, 10))

    progress_bar = ttk.Progressbar(prog_frame, mode="determinate", style="TProgressbar")
    progress_bar.pack(fill="x")

    # 5. LIVE ACTIVITY CONSOLE (LOGS)
    log_card = tk.LabelFrame(
        main_container,
        text="  Live Operations Activity  ",
        font=("Segoe UI", 10, "bold"),
        fg=TEXT_MAIN,
        bg=BG_CARD,
        padx=12,
        pady=10,
        relief="solid",
        bd=1,
    )
    log_card.pack(fill="both", expand=True)

    log_text = tk.Text(
        log_card,
        font=("Consolas", 9),
        bg="#0F172A",
        fg="#F1F5F9",
        wrap="word",
        relief="flat",
        padx=10,
        pady=8,
    )
    log_scroll = ttk.Scrollbar(log_card, command=log_text.yview)
    log_text.configure(yscrollcommand=log_scroll.set)

    log_scroll.pack(side="right", fill="y")
    log_text.pack(side="left", fill="both", expand=True)

    def append_log_line(msg: str) -> None:
        def do_append():
            log_text.insert("end", f"{msg}\n")
            log_text.see("end")

        root.after(0, do_append)

    set_ui_log_callback(append_log_line)
    append_log_line("[UBP Bot] Initialized. Ready for Phase 1 transaction extraction.")

    return root


def launch_gui(config_path: Optional[Path] = None) -> None:
    """Entry point function to launch the UBP Bot desktop interface."""
    app = create_desktop_app(config_path)
    app.mainloop()
