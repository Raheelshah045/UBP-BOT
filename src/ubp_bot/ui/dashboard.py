"""Enterprise Light Dashboard for UBP Bot (Phase 1 Dual-System Operations).

Provides a modern banking operations cockpit:
- 8px grid layout system with clean glassmorphism accents
- High-contrast, accessible enterprise light theme
- Dynamic input/output directory selection with read/write permission verification
- Prevention of directory modification during active processing
- Side-by-side isolated OTC and GNB configuration, execution, and live terminals
- Real-time statistics counters, determinate progress bar, and responsive async execution
"""

import os
import subprocess
import threading
import tkinter as tk
import urllib.parse
import urllib.request
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Dict, Optional

from src.ubp_bot.core.config import (
    ensure_workspace_directories,
    load_config,
    resolve_app_path,
    save_config,
    update_configured_directories,
)
from src.ubp_bot.core.pipeline import set_stop_state
from src.ubp_bot.core.queue_manager import (
    set_monitoring_state,
    start_continuous_monitoring_worker,
)
from src.ubp_bot.portals.gnb_client import run_gnb_extraction_pipeline
from src.ubp_bot.security.log_sanitizer import set_ui_log_callback
from src.ubp_bot.services.browser_manager import launch_persistent_browser_session
from src.ubp_bot.services.excel_reporter import generate_gnb_rejected_report
from src.ubp_bot.ui.dialogs import (
    browse_and_validate_directory,
    prompt_mandatory_directory_setup,
    show_diagnostics_dialog,
)


def check_url_reachability(url: str, timeout_seconds: float = 3.0) -> bool:
    """Check if URL returns an HTTP response without hanging."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) UBP-Bot/2.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:  # nosec B310
            return resp.status < 500
    except Exception:
        return False


def open_folder_in_explorer(folder_path: Path) -> None:
    """Open operating system file explorer at target folder path."""
    folder_path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(folder_path))
    else:
        subprocess.run(["xdg-open", str(folder_path)], check=False)


def create_desktop_dashboard(config_path: Optional[Path] = None) -> tk.Tk:
    """Initialize and construct the UBP Bot enterprise operations dashboard."""
    config = load_config(config_path)
    ensure_workspace_directories(config=config)

    root = tk.Tk()
    root.title("UBP Bot — Enterprise Operations Dashboard (Phase 1)")
    root.geometry("1180x900")
    root.minsize(1060, 780)
    root.configure(bg="#F8FAFC")

    # Prompt mandatory directory setup on first launch if unconfigured
    prompt_mandatory_directory_setup(root, config, config_path)
    config = load_config(config_path)

    # Enterprise Light Color Palette (8px Grid, WCAG AAA compliant contrast)
    BG_MAIN = "#F8FAFC"
    BG_CARD = "#FFFFFF"
    _BORDER_COLOR = "#E2E8F0"  # used via style definitions below
    TEXT_MAIN = "#0F172A"
    TEXT_MUTED = "#64748B"
    PRIMARY_COLOR = "#0F4C81"  # Banking Navy
    SUCCESS_COLOR = "#0D9488"  # Teal Green
    DANGER_COLOR = "#E11D48"   # Rose Red
    INDIGO_ACCENT = "#4338CA"

    style = ttk.Style()
    style.theme_use("clam")
    style.configure(
        "TProgressbar",
        troughcolor="#E2E8F0",
        background=PRIMARY_COLOR,
        thickness=10,
    )

    # 1. HEADER BANNER (64px, 8px grid)
    header_frame = tk.Frame(root, bg=PRIMARY_COLOR, height=64, padx=24, pady=16)
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
        text="  ENTERPRISE PHASE 1: DUAL-SYSTEM TRANSACTION EXTRACTION  ",
        font=("Segoe UI", 8, "bold"),
        fg="#E0F2FE",
        bg="#0369A1",
        padx=8,
        pady=4,
    )
    phase_lbl.pack(side="left", padx=16)

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

    # MAIN SCROLLABLE / STRUCTURED CONTAINER
    main_container = tk.Frame(root, bg=BG_MAIN, padx=24, pady=16)
    main_container.pack(fill="both", expand=True)

    # Operational state tracking
    is_otc_running = False
    is_gnb_running = False
    gnb_stop_event: Optional[threading.Event] = None

    def is_any_system_running() -> bool:
        return is_otc_running or is_gnb_running

    def update_global_badge():
        if is_otc_running and is_gnb_running:
            global_status_badge.configure(text="Running Both Systems", bg="#E0F2FE", fg="#0369A1")
        elif is_otc_running:
            global_status_badge.configure(text="OTC Active", bg="#E0F2FE", fg="#0369A1")
        elif is_gnb_running:
            global_status_badge.configure(text="GNB Active", bg="#D1FAE5", fg="#065F46")
        else:
            global_status_badge.configure(text="System Ready", bg="#D1FAE5", fg="#065F46")

    # 2. DYNAMIC DIRECTORY CONFIGURATION PANEL (Glassmorphism Card)
    dir_card = tk.LabelFrame(
        main_container,
        text="  Dynamic Working Directories  ",
        font=("Segoe UI", 9, "bold"),
        fg=TEXT_MAIN,
        bg=BG_CARD,
        padx=16,
        pady=8,
        relief="solid",
        bd=1,
    )
    dir_card.pack(fill="x", pady=(0, 12))

    dirs_cfg = config.get("directories", {})
    input_path_var = tk.StringVar(value=str(resolve_app_path(dirs_cfg.get("input_dir", "input"))))
    output_path_var = tk.StringVar(value=str(resolve_app_path(dirs_cfg.get("output_dir", "output"))))
    input_perm_var = tk.StringVar(value="✓ Valid Read/Write")
    output_perm_var = tk.StringVar(value="✓ Valid Read/Write")

    # Row 1: Input Directory Picker
    in_row = tk.Frame(dir_card, bg=BG_CARD)
    in_row.pack(fill="x", pady=(2, 6))

    tk.Label(in_row, text="Input Folder:", font=("Segoe UI", 9, "bold"), fg=TEXT_MUTED, bg=BG_CARD, width=12, anchor="w").pack(side="left")
    in_entry = tk.Entry(in_row, textvariable=input_path_var, font=("Consolas", 9), relief="solid", bd=1, state="readonly")
    in_entry.pack(side="left", fill="x", expand=True, padx=(4, 8))

    in_badge = tk.Label(in_row, textvariable=input_perm_var, font=("Segoe UI", 8, "bold"), bg="#D1FAE5", fg="#065F46", padx=6, pady=2)
    in_badge.pack(side="left", padx=(0, 8))

    def on_change_input_dir():
        if is_any_system_running():
            messagebox.showwarning("Processing Active", "Directory paths cannot be altered while batch extraction is active.", parent=root)
            return
        changed, new_path = browse_and_validate_directory(root, "Select Dynamic Input Folder", input_path_var.get())
        if changed and new_path:
            input_path_var.set(str(new_path))
            try:
                update_configured_directories(new_path, output_path_var.get(), config_path)
                append_log_line(f"[SYSTEM] Dynamic Input Folder set to: {new_path}")
                in_badge.configure(bg="#D1FAE5", fg="#065F46")
                input_perm_var.set("✓ Valid Read/Write")
            except Exception as e:
                in_badge.configure(bg="#FEE2E2", fg="#991B1B")
                input_perm_var.set("⚠ Permission Error")
                messagebox.showerror("Error", str(e), parent=root)

    btn_browse_in = tk.Button(
        in_row,
        text="📁 Change Input...",
        font=("Segoe UI", 8, "bold"),
        bg="#E2E8F0",
        fg=TEXT_MAIN,
        padx=10,
        pady=3,
        relief="flat",
        cursor="hand2",
        command=on_change_input_dir,
    )
    btn_browse_in.pack(side="left", padx=4)

    btn_open_in = tk.Button(
        in_row,
        text="📂 Open",
        font=("Segoe UI", 8, "bold"),
        bg="#EFF6FF",
        fg=PRIMARY_COLOR,
        padx=8,
        pady=3,
        relief="flat",
        cursor="hand2",
        command=lambda: open_folder_in_explorer(Path(input_path_var.get())),
    )
    btn_open_in.pack(side="left")

    # Row 2: Output Directory Picker
    out_row = tk.Frame(dir_card, bg=BG_CARD)
    out_row.pack(fill="x", pady=(2, 4))

    tk.Label(out_row, text="Output Folder:", font=("Segoe UI", 9, "bold"), fg=TEXT_MUTED, bg=BG_CARD, width=12, anchor="w").pack(side="left")
    out_entry = tk.Entry(out_row, textvariable=output_path_var, font=("Consolas", 9), relief="solid", bd=1, state="readonly")
    out_entry.pack(side="left", fill="x", expand=True, padx=(4, 8))

    out_badge = tk.Label(out_row, textvariable=output_perm_var, font=("Segoe UI", 8, "bold"), bg="#D1FAE5", fg="#065F46", padx=6, pady=2)
    out_badge.pack(side="left", padx=(0, 8))

    def on_change_output_dir():
        if is_any_system_running():
            messagebox.showwarning("Processing Active", "Directory paths cannot be altered while batch extraction is active.", parent=root)
            return
        changed, new_path = browse_and_validate_directory(root, "Select Dynamic Output Folder", output_path_var.get())
        if changed and new_path:
            output_path_var.set(str(new_path))
            try:
                update_configured_directories(input_path_var.get(), new_path, config_path)
                append_log_line(f"[SYSTEM] Dynamic Output Folder set to: {new_path}")
                out_badge.configure(bg="#D1FAE5", fg="#065F46")
                output_perm_var.set("✓ Valid Read/Write")
            except Exception as e:
                out_badge.configure(bg="#FEE2E2", fg="#991B1B")
                output_perm_var.set("⚠ Permission Error")
                messagebox.showerror("Error", str(e), parent=root)

    btn_browse_out = tk.Button(
        out_row,
        text="📁 Change Output...",
        font=("Segoe UI", 8, "bold"),
        bg="#E2E8F0",
        fg=TEXT_MAIN,
        padx=10,
        pady=3,
        relief="flat",
        cursor="hand2",
        command=on_change_output_dir,
    )
    btn_browse_out.pack(side="left", padx=4)

    btn_open_out = tk.Button(
        out_row,
        text="📂 Open",
        font=("Segoe UI", 8, "bold"),
        bg="#EFF6FF",
        fg=PRIMARY_COLOR,
        padx=8,
        pady=3,
        relief="flat",
        cursor="hand2",
        command=lambda: open_folder_in_explorer(Path(output_path_var.get())),
    )
    btn_open_out.pack(side="left")

    # 3. DUAL-SYSTEM PORTAL CARDS (SIDE-BY-SIDE)
    portals_frame = tk.Frame(main_container, bg=BG_MAIN)
    portals_frame.pack(fill="x", pady=(0, 12))

    # --- OTC Portal Card (Left) ---
    otc_card = tk.LabelFrame(
        portals_frame,
        text="  System A: OTC BPS Portal (Manual Authentication)  ",
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
    otc_status_row.pack(fill="x", pady=(0, 8))

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

    def on_save_otc_url():
        new_url = otc_url_var.get().strip()
        config.setdefault("portal", {})["login_url"] = new_url
        config["portal"]["base_url"] = new_url
        save_config(config)
        append_log_line(f"[OTC] Saved URL: {new_url}")

    def on_open_otc():
        on_save_otc_url()
        url = otc_url_var.get().strip()
        append_log_line(f"[OTC] Opening browser window to {url}...")
        threading.Thread(
            target=lambda: launch_persistent_browser_session(config.get("browser", {}), initial_url=url, system_name="otc"),
            daemon=True,
        ).start()

    tk.Button(
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
    ).pack(side="left", padx=(0, 6))

    tk.Button(
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
    ).pack(side="left")

    # --- GNB Portal Card (Right) ---
    gnb_card = tk.LabelFrame(
        portals_frame,
        text="  System B: GNB Portal (Automated/Configured Auth)  ",
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
    gnb_status_row.pack(fill="x", pady=(0, 8))

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

    def on_save_gnb_url():
        new_url = gnb_url_var.get().strip()
        config.setdefault("gnb", {})["login_url"] = new_url
        config["gnb"]["rejected_transactions_url"] = new_url
        save_config(config)
        append_log_line(f"[GNB] Saved URL: {new_url}")

    def on_open_gnb():
        on_save_gnb_url()
        url = gnb_url_var.get().strip()
        append_log_line(f"[GNB] Opening independent browser session for GNB: {url}...")
        threading.Thread(
            target=lambda: launch_persistent_browser_session(config.get("browser", {}), initial_url=url, system_name="gnb"),
            daemon=True,
        ).start()

    tk.Button(
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
    ).pack(side="left", padx=(0, 6))

    tk.Button(
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
    ).pack(side="left")

    # 4. EXECUTION CONTROLS & STATISTICS STRIP
    control_strip = tk.Frame(main_container, bg=BG_CARD, padx=16, pady=12, relief="solid", bd=1)
    control_strip.pack(fill="x", pady=(0, 12))

    ctrl_row = tk.Frame(control_strip, bg=BG_CARD)
    ctrl_row.pack(fill="x", pady=(0, 8))

    tk.Label(ctrl_row, text="Execution Controls:", font=("Segoe UI", 9, "bold"), fg=TEXT_MUTED, bg=BG_CARD).pack(side="left", padx=(0, 10))

    def update_dir_button_states():
        active = is_any_system_running()
        state = "disabled" if active else "normal"
        btn_browse_in.configure(state=state)
        btn_browse_out.configure(state=state)

    # OTC Handlers
    def start_otc_worker():
        nonlocal is_otc_running
        if is_otc_running:
            return
        is_otc_running = True
        update_dir_button_states()
        update_global_badge()
        otc_proc_var.set("Monitoring & Extracting")
        otc_task_badge.configure(bg="#E0F2FE", fg="#0369A1")
        btn_start_otc.configure(state="disabled")
        btn_stop_otc.configure(state="normal")
        set_monitoring_state(True)
        set_stop_state(False)

        def update_queue(q_count: int, cur_file: str = "") -> None:
            root.after(0, lambda: stat_queue_var.set(f"Queue: {q_count} | Active: {cur_file}"))

        def update_progress(data: Dict[str, Any]) -> None:
            tot = data.get("total_rows", 1)
            prc = data.get("processed_count", 0)
            root.after(0, lambda: [
                progress_bar.configure(maximum=tot, value=prc),
                stat_processed_var.set(f"Processed: {prc}/{tot}"),
            ])

        def update_portal_state(state_str: str) -> None:
            root.after(0, lambda: otc_auth_var.set(state_str))

        append_log_line("[OTC] Continuous monitoring and extraction started.")

        def otc_msg(msg: str) -> None:
            s = str(msg).strip()
            append_log_line(s if s.startswith("[OTC]") else f"[OTC] {s}")

        # Always reload fresh config with dynamic directories
        active_config = load_config(config_path)

        threading.Thread(
            target=start_continuous_monitoring_worker,
            args=(active_config, update_queue, update_progress, otc_msg, update_portal_state),
            kwargs={"allowed_target_system": "otc"},
            daemon=True,
        ).start()

    def stop_otc_worker():
        nonlocal is_otc_running
        set_monitoring_state(False)
        set_stop_state(True)
        is_otc_running = False
        update_dir_button_states()
        update_global_badge()
        otc_proc_var.set("Stopped")
        otc_task_badge.configure(bg="#E2E8F0", fg="#1E293B")
        btn_start_otc.configure(state="normal")
        btn_stop_otc.configure(state="disabled")
        append_log_line("[OTC] Monitoring stopped by user.")

    # GNB Handlers
    def start_gnb_worker():
        nonlocal is_gnb_running, gnb_stop_event
        if is_gnb_running:
            return
        is_gnb_running = True
        gnb_stop_event = threading.Event()
        update_dir_button_states()
        update_global_badge()
        root.after(0, lambda: [
            gnb_proc_var.set("Extracting"),
            gnb_task_badge.configure(bg="#D1FAE5", fg="#065F46"),
            btn_start_gnb.configure(state="disabled"),
            btn_stop_gnb.configure(state="normal"),
        ])

        def worker():
            nonlocal is_gnb_running
            try:
                append_log_line("[GNB] Launching independent GNB extraction pipeline...")
                root.after(0, lambda: gnb_auth_var.set("Authenticating..."))
                active_cfg = load_config(config_path)
                in_dir = resolve_app_path(active_cfg.get("directories", {}).get("input_dir", "input"))
                gnb_candidates = [
                    f for f in in_dir.glob("*")
                    if "gnb" in f.name.lower() and f.suffix.lower() in [".xlsx", ".xls", ".csv"]
                ]
                gnb_file = gnb_candidates[0] if gnb_candidates else None

                def gnb_msg(msg: str) -> None:
                    s = str(msg).strip()
                    append_log_line(s if s.startswith("[GNB]") else f"[GNB] {s}")

                txs = run_gnb_extraction_pipeline(
                    active_cfg,
                    input_file_path=gnb_file,
                    on_message=gnb_msg,
                    keep_browser_open=False,
                    stop_event=gnb_stop_event,
                )
                if gnb_stop_event and gnb_stop_event.is_set():
                    root.after(0, lambda: gnb_proc_var.set("Stopped"))
                    append_log_line("[GNB] Extraction cancelled.")
                    return

                root.after(0, lambda: gnb_auth_var.set("Authenticated"))
                out_p = resolve_app_path(active_cfg.get("directories", {}).get("output_dir", "output"))
                rep = generate_gnb_rejected_report(out_p, txs)
                root.after(0, lambda: [
                    gnb_proc_var.set(f"Completed ({len(txs)})"),
                    stat_gnb_var.set(f"GNB Rejections: {len(txs)}"),
                ])
                append_log_line(f"[GNB] Report generated: {rep.name} ({len(txs)} rejections)")

                if gnb_file and gnb_file.exists():
                    from src.ubp_bot.core.file_detector import compute_file_sha256, move_file_safely
                    from src.ubp_bot.core.pipeline import record_file_history

                    comp_dir = resolve_app_path(active_cfg.get("directories", {}).get("completed_dir", "completed"))
                    archived = move_file_safely(gnb_file, comp_dir)
                    f_hash = compute_file_sha256(archived)
                    db_p = resolve_app_path(
                        active_cfg.get("storage", {}).get("checkpoint_db_path", "checkpoints/processing_checkpoint.db")
                    )
                    record_file_history(db_p, f_hash, archived.name, str(archived), "COMPLETED", str(rep))
                    append_log_line(f"[GNB] Completed and archived: {archived.name}")

            except Exception as exc:
                root.after(0, lambda: gnb_proc_var.set("Error"))
                append_log_line(f"[GNB] Extraction error: {exc}")
            finally:
                is_gnb_running = False
                root.after(0, lambda: [
                    btn_start_gnb.configure(state="normal"),
                    btn_stop_gnb.configure(state="disabled"),
                    update_dir_button_states(),
                    update_global_badge(),
                ])

        threading.Thread(target=worker, daemon=True).start()

    def stop_gnb_worker():
        nonlocal gnb_stop_event
        if gnb_stop_event:
            gnb_stop_event.set()
        root.after(0, lambda: [
            gnb_proc_var.set("Stopping..."),
            btn_stop_gnb.configure(state="disabled"),
        ])
        append_log_line("[GNB] Stop requested. Waiting for clean shutdown...")

    def run_both_systems():
        append_log_line("[*] Launching BOTH systems concurrently in isolated pipelines...")
        start_otc_worker()
        start_gnb_worker()

    btn_start_otc = tk.Button(ctrl_row, text="▶ Start OTC", font=("Segoe UI", 9, "bold"), bg=PRIMARY_COLOR, fg="#FFFFFF", padx=12, pady=5, relief="flat", cursor="hand2", command=start_otc_worker)
    btn_start_otc.pack(side="left", padx=4)

    btn_stop_otc = tk.Button(ctrl_row, text="⏹ Stop OTC", font=("Segoe UI", 9, "bold"), bg=DANGER_COLOR, fg="#FFFFFF", padx=12, pady=5, relief="flat", cursor="hand2", command=stop_otc_worker)
    btn_stop_otc.configure(state="disabled")
    btn_stop_otc.pack(side="left", padx=4)

    btn_start_gnb = tk.Button(ctrl_row, text="▶ Start GNB", font=("Segoe UI", 9, "bold"), bg=SUCCESS_COLOR, fg="#FFFFFF", padx=12, pady=5, relief="flat", cursor="hand2", command=start_gnb_worker)
    btn_start_gnb.pack(side="left", padx=4)

    btn_stop_gnb = tk.Button(ctrl_row, text="⏹ Stop GNB", font=("Segoe UI", 9, "bold"), bg=DANGER_COLOR, fg="#FFFFFF", padx=12, pady=5, relief="flat", cursor="hand2", command=stop_gnb_worker)
    btn_stop_gnb.configure(state="disabled")
    btn_stop_gnb.pack(side="left", padx=4)

    btn_run_both = tk.Button(ctrl_row, text="⚡ Run Both Concurrently", font=("Segoe UI", 9, "bold"), bg=INDIGO_ACCENT, fg="#FFFFFF", padx=12, pady=5, relief="flat", cursor="hand2", command=run_both_systems)
    btn_run_both.pack(side="left", padx=(12, 4))

    btn_diag = tk.Button(
        ctrl_row,
        text="🔍 Diagnostics",
        font=("Segoe UI", 9, "bold"),
        bg="#F1F5F9",
        fg=TEXT_MAIN,
        padx=10,
        pady=5,
        relief="flat",
        cursor="hand2",
        command=lambda: show_diagnostics_dialog(root, config_path),
    )
    btn_diag.pack(side="right")

    # Real-time statistics counters strip
    stat_row = tk.Frame(control_strip, bg=BG_CARD)
    stat_row.pack(fill="x", pady=(4, 0))

    stat_queue_var = tk.StringVar(value="Queue: 0 pending | Active: None")
    stat_processed_var = tk.StringVar(value="Processed: 0/0")
    stat_gnb_var = tk.StringVar(value="GNB Rejections: 0")

    tk.Label(stat_row, textvariable=stat_queue_var, font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=BG_CARD).pack(side="left", padx=(0, 16))
    tk.Label(stat_row, textvariable=stat_processed_var, font=("Segoe UI", 8, "bold"), fg=PRIMARY_COLOR, bg=BG_CARD).pack(side="left", padx=(0, 16))
    tk.Label(stat_row, textvariable=stat_gnb_var, font=("Segoe UI", 8, "bold"), fg=SUCCESS_COLOR, bg=BG_CARD).pack(side="left")

    # 5. DETERMINATE PROGRESS BAR
    prog_frame = tk.Frame(main_container, bg=BG_MAIN)
    prog_frame.pack(fill="x", pady=(0, 10))

    progress_bar = ttk.Progressbar(prog_frame, mode="determinate", style="TProgressbar")
    progress_bar.pack(fill="x")

    # 6. DUAL LIVE TERMINALS (SIDE-BY-SIDE CONSOLES)
    consoles_container = tk.Frame(main_container, bg=BG_MAIN)
    consoles_container.pack(fill="both", expand=True)
    consoles_container.columnconfigure(0, weight=1)
    consoles_container.columnconfigure(1, weight=1)
    consoles_container.rowconfigure(0, weight=1)

    # --- OTC Terminal (Left) ---
    otc_term_card = tk.LabelFrame(
        consoles_container,
        text="  🖥️ System A — OTC Live Console (BPS Operations)  ",
        font=("Segoe UI", 9, "bold"),
        fg="#1E3A8A",
        bg=BG_CARD,
        padx=8,
        pady=6,
        relief="solid",
        bd=1,
    )
    otc_term_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

    otc_log_text = tk.Text(
        otc_term_card,
        font=("Consolas", 9),
        bg="#0F172A",
        fg="#93C5FD",
        wrap="word",
        relief="flat",
        padx=8,
        pady=6,
    )
    otc_scroll = ttk.Scrollbar(otc_term_card, command=otc_log_text.yview)
    otc_log_text.configure(yscrollcommand=otc_scroll.set)
    otc_scroll.pack(side="right", fill="y")
    otc_log_text.pack(side="left", fill="both", expand=True)

    # --- GNB Terminal (Right) ---
    gnb_term_card = tk.LabelFrame(
        consoles_container,
        text="  🏦 System B — GNB Live Console (Core Banking)  ",
        font=("Segoe UI", 9, "bold"),
        fg="#065F46",
        bg=BG_CARD,
        padx=8,
        pady=6,
        relief="solid",
        bd=1,
    )
    gnb_term_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

    gnb_log_text = tk.Text(
        gnb_term_card,
        font=("Consolas", 9),
        bg="#061A14",
        fg="#86EFAC",
        wrap="word",
        relief="flat",
        padx=8,
        pady=6,
    )
    gnb_scroll = ttk.Scrollbar(gnb_term_card, command=gnb_log_text.yview)
    gnb_log_text.configure(yscrollcommand=gnb_scroll.set)
    gnb_scroll.pack(side="right", fill="y")
    gnb_log_text.pack(side="left", fill="both", expand=True)

    def append_log_line(msg: str) -> None:
        def do_append():
            line = str(msg).strip()
            if not line:
                return

            # Clean duplicate prefixes
            while line.startswith("[GNB] [GNB]"):
                line = "[GNB] " + line[11:].strip()
            while line.startswith("[OTC] [OTC]"):
                line = "[OTC] " + line[11:].strip()

            lower = line.lower()
            is_global = (
                lower.startswith("[ubp bot]")
                or lower.startswith("[system]")
                or "launching both systems" in lower
                or "both systems" in lower
            )
            is_gnb = (
                "[gnb]" in lower
                or "gnb" in lower
                or "core banking" in lower
                or ":8765" in lower
                or "tx id" in lower
            )
            is_otc = (
                "[otc]" in lower
                or "[bps]" in lower
                or "otc" in lower
                or "bps" in lower
                or "consumer" in lower
                or "check bill" in lower
                or ":5173" in lower
                or "monitoring" in lower
                or "queue" in lower
                or "batch" in lower
            )

            if is_global:
                otc_log_text.insert("end", f"{line}\n")
                otc_log_text.see("end")
                gnb_log_text.insert("end", f"{line}\n")
                gnb_log_text.see("end")
            elif is_gnb and not is_otc:
                gnb_log_text.insert("end", f"{line}\n")
                gnb_log_text.see("end")
            elif is_otc and not is_gnb:
                otc_log_text.insert("end", f"{line}\n")
                otc_log_text.see("end")
            elif is_gnb and is_otc:
                if lower.startswith("[gnb]") or "gnb" in lower.split()[:2]:
                    gnb_log_text.insert("end", f"{line}\n")
                    gnb_log_text.see("end")
                else:
                    otc_log_text.insert("end", f"{line}\n")
                    otc_log_text.see("end")
            else:
                otc_log_text.insert("end", f"{line}\n")
                otc_log_text.see("end")

        root.after(0, do_append)

    set_ui_log_callback(append_log_line)
    append_log_line("[UBP Bot] Enterprise Dashboard initialized. Ready for Phase 1 dual operations.")

    return root


def launch_dashboard(config_path: Optional[Path] = None) -> None:
    """Launch the enterprise operations dashboard mainloop."""
    app = create_desktop_dashboard(config_path)
    app.mainloop()
