"""Enterprise Light Glassmorphism Dashboard for UBP Bot (Phase 1 Dual-System Operations).

Provides a modern banking operations cockpit:
- 8px grid layout system with authentic light glassmorphism visual styling
- Elevated frosted white card containers with refined borders and subtle shadows
- High-contrast, accessible enterprise banking palette (Navy, Slate, Emerald, Rose)
- Dynamic input/output directory selection with read/write permission verification
- Directory lock enforcement during active processing
- Side-by-side isolated OTC and GNB configuration, execution, and live telemetry consoles
- Elevated KPI metric cards, determinate progress bar, and responsive async execution
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
    get_application_root,
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


def open_file_in_default_app(file_path: Path) -> None:
    """Open a report file in its default OS viewer (e.g. Excel)."""
    if file_path.exists():
        if os.name == "nt":
            os.startfile(str(file_path))
        else:
            subprocess.run(["xdg-open", str(file_path)], check=False)
    else:
        messagebox.showinfo(
            "Report Not Found",
            f"No report file has been generated yet at:\n\n{file_path}\n\n"
            "Run a batch extraction to generate this report.",
        )


def create_glass_card(parent: tk.Widget, bg: str = "#FFFFFF", border_color: str = "#CBD5E1", pad_x: int = 16, pad_y: int = 12) -> tk.Frame:
    """Create a styled translucent card with soft border simulating glass elevation."""
    outer = tk.Frame(parent, bg=border_color, padx=1, pady=1)
    inner = tk.Frame(outer, bg=bg, padx=pad_x, pady=pad_y)
    inner.pack(fill="both", expand=True)
    return outer


def create_desktop_dashboard(config_path: Optional[Path] = None) -> tk.Tk:
    """Initialize and construct the UBP Bot enterprise operations dashboard."""
    config = load_config(config_path)
    ensure_workspace_directories(config=config)

    root = tk.Tk()
    root.title("UBP Bot — Enterprise Operations Cockpit (Phase 1 Dual-System)")
    root.geometry("1200x920")
    root.minsize(1080, 800)
    root.configure(bg="#F1F5F9")

    # Prompt mandatory directory setup on first launch if unconfigured
    prompt_mandatory_directory_setup(root, config, config_path)
    config = load_config(config_path)

    # Enterprise Glassmorphism Color Palette (8px Grid, WCAG AAA compliant contrast)
    BG_CANVAS = "#F1F5F9"       # Cool slate background
    BG_CARD = "#FFFFFF"         # Crisp frosted white surface
    BG_SUBTLE = "#F8FAFC"       # Light tinted card surface
    _BORDER_LIGHT = "#E2E8F0"   # Subtle glass divider
    BORDER_ACCENT = "#CBD5E1"   # Defined container border
    TEXT_MAIN = "#0F172A"       # Deep slate for primary text
    TEXT_MUTED = "#475569"      # Slate for secondary labels
    PRIMARY_NAVY = "#0A2540"    # Deep banking navy
    ACCENT_BLUE = "#0284C7"     # Sky blue for OTC
    SUCCESS_TEAL = "#059669"    # Emerald green for GNB
    DANGER_ROSE = "#E11D48"     # Rose red for stop / errors
    WARNING_AMBER = "#D97706"   # Amber for warnings / waiting

    style = ttk.Style()
    style.theme_use("clam")
    style.configure(
        "TProgressbar",
        troughcolor="#E2E8F0",
        background="#0284C7",
        thickness=8,
    )

    # =========================================================================
    # 1. COMPACT ENTERPRISE HEADER
    # =========================================================================
    navbar_outer = tk.Frame(root, bg="#071829")
    navbar_outer.pack(fill="x")

    navbar = tk.Frame(navbar_outer, bg=PRIMARY_NAVY, padx=24, pady=10)
    navbar.pack(fill="x")

    nav_left = tk.Frame(navbar, bg=PRIMARY_NAVY)
    nav_left.pack(side="left")

    brand_lbl = tk.Label(
        nav_left,
        text="UBP BOT",
        font=("Segoe UI", 15, "bold"),
        fg="#FFFFFF",
        bg=PRIMARY_NAVY,
    )
    brand_lbl.pack(side="left")

    nav_right = tk.Frame(navbar, bg=PRIMARY_NAVY)
    nav_right.pack(side="right")

    global_status_badge = tk.Label(
        nav_right,
        text="● System Ready",
        font=("Segoe UI", 9, "bold"),
        fg="#065F46",
        bg="#D1FAE5",
        padx=12,
        pady=5,
    )
    global_status_badge.pack(side="right", padx=(8, 0))

    btn_diag = tk.Button(
        nav_right,
        text="🔍 Diagnostics",
        font=("Segoe UI", 9, "bold"),
        bg="#1E3A8A",
        fg="#FFFFFF",
        padx=10,
        pady=4,
        relief="flat",
        cursor="hand2",
        command=lambda: show_diagnostics_dialog(root, config_path),
    )
    btn_diag.pack(side="right")

    # =========================================================================
    # MAIN SCROLLABLE/EXPANDABLE WORKSPACE CONTAINER
    # =========================================================================
    main_container = tk.Frame(root, bg=BG_CANVAS, padx=20, pady=12)
    main_container.pack(fill="both", expand=True)

    # Operational state tracking
    is_otc_running = False
    is_gnb_running = False
    gnb_stop_event: Optional[threading.Event] = None

    def is_any_system_running() -> bool:
        return is_otc_running or is_gnb_running

    def update_global_badge():
        if is_otc_running and is_gnb_running:
            global_status_badge.configure(text="● Dual Systems Active", bg="#E0F2FE", fg="#0369A1")
        elif is_otc_running:
            global_status_badge.configure(text="● OTC Active", bg="#E0F2FE", fg="#0369A1")
        elif is_gnb_running:
            global_status_badge.configure(text="● GNB Active", bg="#D1FAE5", fg="#065F46")
        else:
            global_status_badge.configure(text="● System Ready", bg="#D1FAE5", fg="#065F46")

    # =========================================================================
    # 2. KPI METRICS GLASS STRIP (4 Glass Cards)
    # =========================================================================
    kpi_frame = tk.Frame(main_container, bg=BG_CANVAS)
    kpi_frame.pack(fill="x", pady=(0, 10))
    for i in range(4):
        kpi_frame.columnconfigure(i, weight=1, uniform="kpi")

    # Metric variables
    stat_queue_count = tk.StringVar(value="0 Files")
    stat_queue_sub = tk.StringVar(value="Queue: 0 pending | Active: None")
    stat_otc_count = tk.StringVar(value="0 / 0")
    stat_otc_sub = tk.StringVar(value="Rows Processed | 0 Rejected")
    stat_qual_count = tk.StringVar(value="0 Extracted")
    stat_qual_sub = tk.StringVar(value="Codes 95 & 98 Excluded")
    stat_gnb_count = tk.StringVar(value="0 Extracted")
    stat_gnb_sub = tk.StringVar(value="Core Banking Rejections")

    def make_kpi_card(parent: tk.Widget, col: int, title: str, top_color: str, val_var: tk.StringVar, sub_var: tk.StringVar, icon: str):
        card_border = tk.Frame(parent, bg=BORDER_ACCENT, padx=1, pady=1)
        card_border.grid(row=0, column=col, sticky="nsew", padx=4)

        card_inner = tk.Frame(card_border, bg=BG_CARD)
        card_inner.pack(fill="both", expand=True)

        # Top Accent Ribbon
        ribbon = tk.Frame(card_inner, bg=top_color, height=3)
        ribbon.pack(fill="x")

        body = tk.Frame(card_inner, bg=BG_CARD, padx=12, pady=8)
        body.pack(fill="both", expand=True)

        head_row = tk.Frame(body, bg=BG_CARD)
        head_row.pack(fill="x")
        tk.Label(head_row, text=icon, font=("Segoe UI", 10), bg=BG_CARD).pack(side="left")
        tk.Label(head_row, text=f" {title}", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=BG_CARD).pack(side="left")

        val_lbl = tk.Label(body, textvariable=val_var, font=("Segoe UI", 15, "bold"), fg=TEXT_MAIN, bg=BG_CARD)
        val_lbl.pack(anchor="w", pady=(2, 0))

        sub_lbl = tk.Label(body, textvariable=sub_var, font=("Segoe UI", 7), fg=TEXT_MUTED, bg=BG_CARD)
        sub_lbl.pack(anchor="w")

    make_kpi_card(kpi_frame, 0, "INPUT QUEUE", WARNING_AMBER, stat_queue_count, stat_queue_sub, "📂")
    make_kpi_card(kpi_frame, 1, "OTC EXTRACTION", ACCENT_BLUE, stat_otc_count, stat_otc_sub, "📊")
    make_kpi_card(kpi_frame, 2, "QUALIFYING REJECTIONS", "#6366F1", stat_qual_count, stat_qual_sub, "⚡")
    make_kpi_card(kpi_frame, 3, "GNB EXTRACTION", SUCCESS_TEAL, stat_gnb_count, stat_gnb_sub, "🏦")

    # =========================================================================
    # 3. DYNAMIC WORKING DIRECTORIES PANEL (Glassmorphism Card)
    # =========================================================================
    dir_card_border = tk.Frame(main_container, bg=BORDER_ACCENT, padx=1, pady=1)
    dir_card_border.pack(fill="x", pady=(0, 10))

    dir_card = tk.Frame(dir_card_border, bg=BG_CARD, padx=14, pady=8)
    dir_card.pack(fill="both", expand=True)

    dir_header = tk.Frame(dir_card, bg=BG_CARD)
    dir_header.pack(fill="x", pady=(0, 6))

    tk.Label(
        dir_header,
        text="📁 Dynamic Working Directory Hub",
        font=("Segoe UI", 9, "bold"),
        fg=TEXT_MAIN,
        bg=BG_CARD,
    ).pack(side="left")

    tk.Label(
        dir_header,
        text="Atomic Write Probe & Persistence Active",
        font=("Segoe UI", 7, "bold"),
        fg="#0369A1",
        bg="#E0F2FE",
        padx=6,
        pady=1,
    ).pack(side="left", padx=10)

    dirs_cfg = config.get("directories", {})
    input_path_var = tk.StringVar(value=str(resolve_app_path(dirs_cfg.get("input_dir", "input"))))
    output_path_var = tk.StringVar(value=str(resolve_app_path(dirs_cfg.get("output_dir", "output"))))
    input_perm_var = tk.StringVar(value="✓ Valid Read/Write")
    output_perm_var = tk.StringVar(value="✓ Valid Read/Write")

    # Row 1: Input Directory
    in_row = tk.Frame(dir_card, bg=BG_CARD)
    in_row.pack(fill="x", pady=2)

    tk.Label(
        in_row,
        text="Input Folder:",
        font=("Segoe UI", 8, "bold"),
        fg=TEXT_MUTED,
        bg=BG_CARD,
        width=12,
        anchor="w",
    ).pack(side="left")

    in_entry = tk.Entry(
        in_row,
        textvariable=input_path_var,
        font=("Consolas", 8),
        bg=BG_SUBTLE,
        fg=TEXT_MAIN,
        relief="solid",
        bd=1,
        state="readonly",
    )
    in_entry.pack(side="left", fill="x", expand=True, padx=(2, 6))

    in_badge = tk.Label(
        in_row,
        textvariable=input_perm_var,
        font=("Segoe UI", 7, "bold"),
        bg="#D1FAE5",
        fg="#065F46",
        padx=6,
        pady=1,
    )
    in_badge.pack(side="left", padx=(0, 6))

    def on_change_input_dir():
        if is_any_system_running():
            messagebox.showwarning(
                "Processing Active",
                "Directory paths cannot be altered while batch extraction is active.",
                parent=root,
            )
            return
        changed, new_path = browse_and_validate_directory(
            root, "Select Dynamic Input Folder", input_path_var.get()
        )
        if changed and new_path:
            input_path_var.set(str(new_path))
            try:
                update_configured_directories(new_path, output_path_var.get(), config_path)
                append_log_line(f"[SYSTEM] Dynamic Input Folder updated to: {new_path}")
                in_badge.configure(bg="#D1FAE5", fg="#065F46")
                input_perm_var.set("✓ Valid Read/Write")
            except Exception as e:
                in_badge.configure(bg="#FEE2E2", fg="#991B1B")
                input_perm_var.set("⚠ Permission Error")
                messagebox.showerror("Error", str(e), parent=root)

    btn_browse_in = tk.Button(
        in_row,
        text="📁 Browse...",
        font=("Segoe UI", 8, "bold"),
        bg="#E2E8F0",
        fg=TEXT_MAIN,
        padx=8,
        pady=2,
        relief="flat",
        cursor="hand2",
        command=on_change_input_dir,
    )
    btn_browse_in.pack(side="left", padx=2)

    btn_open_in = tk.Button(
        in_row,
        text="📂 Open",
        font=("Segoe UI", 8, "bold"),
        bg="#EFF6FF",
        fg=ACCENT_BLUE,
        padx=8,
        pady=2,
        relief="flat",
        cursor="hand2",
        command=lambda: open_folder_in_explorer(Path(input_path_var.get())),
    )
    btn_open_in.pack(side="left")

    # Row 2: Output Directory
    out_row = tk.Frame(dir_card, bg=BG_CARD)
    out_row.pack(fill="x", pady=2)

    tk.Label(
        out_row,
        text="Output Folder:",
        font=("Segoe UI", 8, "bold"),
        fg=TEXT_MUTED,
        bg=BG_CARD,
        width=12,
        anchor="w",
    ).pack(side="left")

    out_entry = tk.Entry(
        out_row,
        textvariable=output_path_var,
        font=("Consolas", 8),
        bg=BG_SUBTLE,
        fg=TEXT_MAIN,
        relief="solid",
        bd=1,
        state="readonly",
    )
    out_entry.pack(side="left", fill="x", expand=True, padx=(2, 6))

    out_badge = tk.Label(
        out_row,
        textvariable=output_perm_var,
        font=("Segoe UI", 7, "bold"),
        bg="#D1FAE5",
        fg="#065F46",
        padx=6,
        pady=1,
    )
    out_badge.pack(side="left", padx=(0, 6))

    def on_change_output_dir():
        if is_any_system_running():
            messagebox.showwarning(
                "Processing Active",
                "Directory paths cannot be altered while batch extraction is active.",
                parent=root,
            )
            return
        changed, new_path = browse_and_validate_directory(
            root, "Select Dynamic Output Folder", output_path_var.get()
        )
        if changed and new_path:
            output_path_var.set(str(new_path))
            try:
                update_configured_directories(input_path_var.get(), new_path, config_path)
                append_log_line(f"[SYSTEM] Dynamic Output Folder updated to: {new_path}")
                out_badge.configure(bg="#D1FAE5", fg="#065F46")
                output_perm_var.set("✓ Valid Read/Write")
            except Exception as e:
                out_badge.configure(bg="#FEE2E2", fg="#991B1B")
                output_perm_var.set("⚠ Permission Error")
                messagebox.showerror("Error", str(e), parent=root)

    btn_browse_out = tk.Button(
        out_row,
        text="📁 Browse...",
        font=("Segoe UI", 8, "bold"),
        bg="#E2E8F0",
        fg=TEXT_MAIN,
        padx=8,
        pady=2,
        relief="flat",
        cursor="hand2",
        command=on_change_output_dir,
    )
    btn_browse_out.pack(side="left", padx=2)

    btn_open_out = tk.Button(
        out_row,
        text="📂 Open",
        font=("Segoe UI", 8, "bold"),
        bg="#EFF6FF",
        fg=ACCENT_BLUE,
        padx=8,
        pady=2,
        relief="flat",
        cursor="hand2",
        command=lambda: open_folder_in_explorer(Path(output_path_var.get())),
    )
    btn_open_out.pack(side="left")

    def update_dir_button_states():
        active = is_any_system_running()
        state = "disabled" if active else "normal"
        btn_browse_in.configure(state=state)
        btn_browse_out.configure(state=state)

    # =========================================================================
    # 4. DUAL-SYSTEM PORTAL COCKPITS (Side-by-Side Floating Glass Cards)
    # =========================================================================
    portals_frame = tk.Frame(main_container, bg=BG_CANVAS)
    portals_frame.pack(fill="x", pady=(0, 10))
    portals_frame.columnconfigure(0, weight=1, uniform="portal")
    portals_frame.columnconfigure(1, weight=1, uniform="portal")

    # -------------------------------------------------------------------------
    # System A: OTC Portal Card (Left)
    # -------------------------------------------------------------------------
    otc_border = tk.Frame(portals_frame, bg=BORDER_ACCENT, padx=1, pady=1)
    otc_border.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

    otc_card = tk.Frame(otc_border, bg=BG_CARD)
    otc_card.pack(fill="both", expand=True)

    otc_ribbon = tk.Frame(otc_card, bg=ACCENT_BLUE, height=4)
    otc_ribbon.pack(fill="x")

    otc_body = tk.Frame(otc_card, bg=BG_CARD, padx=14, pady=10)
    otc_body.pack(fill="both", expand=True)

    # OTC Header
    otc_head_row = tk.Frame(otc_body, bg=BG_CARD)
    otc_head_row.pack(fill="x", pady=(0, 6))

    tk.Label(
        otc_head_row,
        text="SYSTEM A",
        font=("Segoe UI", 7, "bold"),
        fg="#FFFFFF",
        bg=ACCENT_BLUE,
        padx=5,
        pady=1,
    ).pack(side="left")

    tk.Label(
        otc_head_row,
        text=" OTC BPS Portal",
        font=("Segoe UI", 10, "bold"),
        fg=TEXT_MAIN,
        bg=BG_CARD,
    ).pack(side="left")

    otc_auth_var = tk.StringVar(value="Waiting Auth")
    otc_auth_badge = tk.Label(
        otc_head_row,
        textvariable=otc_auth_var,
        font=("Segoe UI", 7, "bold"),
        fg="#854D0E",
        bg="#FEF9C3",
        padx=6,
        pady=1,
    )
    otc_auth_badge.pack(side="right")

    otc_proc_var = tk.StringVar(value="Idle")
    otc_task_badge = tk.Label(
        otc_head_row,
        textvariable=otc_proc_var,
        font=("Segoe UI", 7, "bold"),
        fg="#1E293B",
        bg="#E2E8F0",
        padx=6,
        pady=1,
    )
    otc_task_badge.pack(side="right", padx=(0, 6))

    # OTC URL row
    otc_url_row = tk.Frame(otc_body, bg=BG_CARD)
    otc_url_row.pack(fill="x", pady=(0, 8))

    otc_url_var = tk.StringVar(
        value=config.get("portal", {}).get("login_url", "http://localhost:5173/")
    )
    tk.Label(
        otc_url_row,
        text="Endpoint URL:",
        font=("Segoe UI", 8, "bold"),
        fg=TEXT_MUTED,
        bg=BG_CARD,
        width=11,
        anchor="w",
    ).pack(side="left")

    otc_url_entry = tk.Entry(
        otc_url_row,
        textvariable=otc_url_var,
        font=("Consolas", 8),
        bg=BG_SUBTLE,
        fg=TEXT_MAIN,
        relief="solid",
        bd=1,
    )
    otc_url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

    def on_save_otc_url():
        new_url = otc_url_var.get().strip()
        config.setdefault("portal", {})["login_url"] = new_url
        config["portal"]["base_url"] = new_url
        save_config(config)
        append_log_line(f"[OTC] Endpoint URL saved: {new_url}")

    def on_open_otc():
        on_save_otc_url()
        url = otc_url_var.get().strip()
        append_log_line(f"[OTC] Launching independent OTC browser session: {url}...")
        threading.Thread(
            target=lambda: launch_persistent_browser_session(
                config.get("browser", {}), initial_url=url, system_name="otc"
            ),
            daemon=True,
        ).start()

    tk.Button(
        otc_url_row,
        text="💾 Save",
        font=("Segoe UI", 7, "bold"),
        bg="#E2E8F0",
        fg=TEXT_MAIN,
        padx=6,
        pady=1,
        relief="flat",
        cursor="hand2",
        command=on_save_otc_url,
    ).pack(side="left", padx=(0, 4))

    tk.Button(
        otc_url_row,
        text="🌐 Browser",
        font=("Segoe UI", 7, "bold"),
        bg="#EFF6FF",
        fg=ACCENT_BLUE,
        padx=6,
        pady=1,
        relief="flat",
        cursor="hand2",
        command=on_open_otc,
    ).pack(side="left")

    # OTC Action Buttons
    otc_ctrl_row = tk.Frame(otc_body, bg=BG_CARD)
    otc_ctrl_row.pack(fill="x", pady=(2, 0))

    def start_otc_worker():
        nonlocal is_otc_running
        if is_otc_running:
            return
        is_otc_running = True
        update_dir_button_states()
        update_global_badge()
        otc_proc_var.set("Active")
        otc_task_badge.configure(bg="#E0F2FE", fg="#0369A1")
        btn_start_otc.configure(state="disabled")
        btn_stop_otc.configure(state="normal")
        set_monitoring_state(True)
        set_stop_state(False)

        def update_queue(q_count: int, cur_file: str = "") -> None:
            root.after(0, lambda: [
                stat_queue_count.set(f"{q_count} Files"),
                stat_queue_sub.set(f"Queue: {q_count} pending | Active: {cur_file if cur_file else 'None'}"),
            ])

        def update_progress(data: Dict[str, Any]) -> None:
            tot = data.get("total_rows", 1)
            prc = data.get("processed_count", 0)
            c_num = data.get("consumer_number", "")
            root.after(0, lambda: [
                progress_bar.configure(maximum=tot, value=prc),
                stat_otc_count.set(f"{prc} / {tot}"),
                stat_otc_sub.set(f"Row {prc}/{tot} | Active: {c_num[:4]}..."),
                prog_label_var.set(f"Processing row {prc} of {tot} ({round(prc/tot*100 if tot else 0)}%)"),
            ])

        def update_portal_state(state_str: str) -> None:
            root.after(0, lambda: [
                otc_auth_var.set(state_str),
                otc_auth_badge.configure(
                    bg="#D1FAE5" if "Auth" in state_str else "#FEF9C3",
                    fg="#065F46" if "Auth" in state_str else "#854D0E",
                ),
            ])

        append_log_line("[OTC] Continuous monitoring and extraction started.")

        def otc_msg(msg: str) -> None:
            s = str(msg).strip()
            append_log_line(s if s.startswith("[OTC]") else f"[OTC] {s}")

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

    btn_start_otc = tk.Button(
        otc_ctrl_row,
        text="▶ Start OTC",
        font=("Segoe UI", 9, "bold"),
        bg=PRIMARY_NAVY,
        fg="#FFFFFF",
        padx=12,
        pady=4,
        relief="flat",
        cursor="hand2",
        command=start_otc_worker,
    )
    btn_start_otc.pack(side="left", padx=(0, 6))

    btn_stop_otc = tk.Button(
        otc_ctrl_row,
        text="⏹ Stop",
        font=("Segoe UI", 9, "bold"),
        bg=DANGER_ROSE,
        fg="#FFFFFF",
        padx=10,
        pady=4,
        relief="flat",
        cursor="hand2",
        state="disabled",
        command=stop_otc_worker,
    )
    btn_stop_otc.pack(side="left", padx=(0, 6))

    def on_view_otc_report():
        out_p = resolve_app_path(load_config(config_path).get("directories", {}).get("output_dir", "output"))
        open_file_in_default_app(out_p / "OTC_Rejected_Transactions.xlsx")

    btn_rep_otc = tk.Button(
        otc_ctrl_row,
        text="📊 View Report",
        font=("Segoe UI", 8, "bold"),
        bg="#F1F5F9",
        fg=TEXT_MAIN,
        padx=8,
        pady=4,
        relief="flat",
        cursor="hand2",
        command=on_view_otc_report,
    )
    btn_rep_otc.pack(side="left")

    # -------------------------------------------------------------------------
    # System B: GNB Portal Card (Right)
    # -------------------------------------------------------------------------
    gnb_border = tk.Frame(portals_frame, bg=BORDER_ACCENT, padx=1, pady=1)
    gnb_border.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

    gnb_card = tk.Frame(gnb_border, bg=BG_CARD)
    gnb_card.pack(fill="both", expand=True)

    gnb_ribbon = tk.Frame(gnb_card, bg=SUCCESS_TEAL, height=4)
    gnb_ribbon.pack(fill="x")

    gnb_body = tk.Frame(gnb_card, bg=BG_CARD, padx=14, pady=10)
    gnb_body.pack(fill="both", expand=True)

    # GNB Header
    gnb_head_row = tk.Frame(gnb_body, bg=BG_CARD)
    gnb_head_row.pack(fill="x", pady=(0, 6))

    tk.Label(
        gnb_head_row,
        text="SYSTEM B",
        font=("Segoe UI", 7, "bold"),
        fg="#FFFFFF",
        bg=SUCCESS_TEAL,
        padx=5,
        pady=1,
    ).pack(side="left")

    tk.Label(
        gnb_head_row,
        text=" GNB Core Banking",
        font=("Segoe UI", 10, "bold"),
        fg=TEXT_MAIN,
        bg=BG_CARD,
    ).pack(side="left")

    gnb_auth_var = tk.StringVar(value="Waiting Auth")
    gnb_auth_badge = tk.Label(
        gnb_head_row,
        textvariable=gnb_auth_var,
        font=("Segoe UI", 7, "bold"),
        fg="#854D0E",
        bg="#FEF9C3",
        padx=6,
        pady=1,
    )
    gnb_auth_badge.pack(side="right")

    gnb_proc_var = tk.StringVar(value="Idle")
    gnb_task_badge = tk.Label(
        gnb_head_row,
        textvariable=gnb_proc_var,
        font=("Segoe UI", 7, "bold"),
        fg="#1E293B",
        bg="#E2E8F0",
        padx=6,
        pady=1,
    )
    gnb_task_badge.pack(side="right", padx=(0, 6))

    # GNB URL row
    gnb_url_row = tk.Frame(gnb_body, bg=BG_CARD)
    gnb_url_row.pack(fill="x", pady=(0, 8))

    gnb_url_var = tk.StringVar(
        value=config.get("gnb", {}).get("login_url", "http://127.0.0.1:8080/gnb/login")
    )
    tk.Label(
        gnb_url_row,
        text="Endpoint URL:",
        font=("Segoe UI", 8, "bold"),
        fg=TEXT_MUTED,
        bg=BG_CARD,
        width=11,
        anchor="w",
    ).pack(side="left")

    gnb_url_entry = tk.Entry(
        gnb_url_row,
        textvariable=gnb_url_var,
        font=("Consolas", 8),
        bg=BG_SUBTLE,
        fg=TEXT_MAIN,
        relief="solid",
        bd=1,
    )
    gnb_url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

    def on_save_gnb_url():
        new_url = gnb_url_var.get().strip()
        config.setdefault("gnb", {})["login_url"] = new_url
        config["gnb"]["rejected_transactions_url"] = new_url
        save_config(config)
        append_log_line(f"[GNB] Endpoint URL saved: {new_url}")

    def on_open_gnb():
        on_save_gnb_url()
        url = gnb_url_var.get().strip()
        append_log_line(f"[GNB] Launching independent GNB browser session: {url}...")
        threading.Thread(
            target=lambda: launch_persistent_browser_session(
                config.get("browser", {}), initial_url=url, system_name="gnb"
            ),
            daemon=True,
        ).start()

    tk.Button(
        gnb_url_row,
        text="💾 Save",
        font=("Segoe UI", 7, "bold"),
        bg="#E2E8F0",
        fg=TEXT_MAIN,
        padx=6,
        pady=1,
        relief="flat",
        cursor="hand2",
        command=on_save_gnb_url,
    ).pack(side="left", padx=(0, 4))

    tk.Button(
        gnb_url_row,
        text="🏦 Browser",
        font=("Segoe UI", 7, "bold"),
        bg="#F0FDF4",
        fg=SUCCESS_TEAL,
        padx=6,
        pady=1,
        relief="flat",
        cursor="hand2",
        command=on_open_gnb,
    ).pack(side="left")

    # GNB Action Buttons
    gnb_ctrl_row = tk.Frame(gnb_body, bg=BG_CARD)
    gnb_ctrl_row.pack(fill="x", pady=(2, 0))

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
                root.after(0, lambda: [
                    gnb_auth_var.set("Authenticating..."),
                    gnb_auth_badge.configure(bg="#FEF9C3", fg="#854D0E"),
                ])
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
                    root.after(0, lambda: [
                        gnb_proc_var.set("Stopped"),
                        gnb_task_badge.configure(bg="#E2E8F0", fg="#1E293B"),
                    ])
                    append_log_line("[GNB] Extraction cancelled.")
                    return

                root.after(0, lambda: [
                    gnb_auth_var.set("Authenticated"),
                    gnb_auth_badge.configure(bg="#D1FAE5", fg="#065F46"),
                ])
                out_p = resolve_app_path(active_cfg.get("directories", {}).get("output_dir", "output"))
                rep = generate_gnb_rejected_report(out_p, txs)
                root.after(0, lambda: [
                    gnb_proc_var.set(f"Done ({len(txs)})"),
                    stat_gnb_count.set(f"{len(txs)} Extracted"),
                    stat_gnb_sub.set(f"Report: {rep.name}"),
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

    btn_start_gnb = tk.Button(
        gnb_ctrl_row,
        text="▶ Start GNB",
        font=("Segoe UI", 9, "bold"),
        bg=SUCCESS_TEAL,
        fg="#FFFFFF",
        padx=12,
        pady=4,
        relief="flat",
        cursor="hand2",
        command=start_gnb_worker,
    )
    btn_start_gnb.pack(side="left", padx=(0, 6))

    btn_stop_gnb = tk.Button(
        gnb_ctrl_row,
        text="⏹ Stop",
        font=("Segoe UI", 9, "bold"),
        bg=DANGER_ROSE,
        fg="#FFFFFF",
        padx=10,
        pady=4,
        relief="flat",
        cursor="hand2",
        state="disabled",
        command=stop_gnb_worker,
    )
    btn_stop_gnb.pack(side="left", padx=(0, 6))

    def on_view_gnb_report():
        out_p = resolve_app_path(load_config(config_path).get("directories", {}).get("output_dir", "output"))
        open_file_in_default_app(out_p / "GNB_Rejected_Transactions.xlsx")

    btn_rep_gnb = tk.Button(
        gnb_ctrl_row,
        text="📊 View Report",
        font=("Segoe UI", 8, "bold"),
        bg="#F1F5F9",
        fg=TEXT_MAIN,
        padx=8,
        pady=4,
        relief="flat",
        cursor="hand2",
        command=on_view_gnb_report,
    )
    btn_rep_gnb.pack(side="left")

    # =========================================================================
    # 5. UNIVERSAL BATCH ORCHESTRATION & PROGRESS BAR
    # =========================================================================
    orch_card_border = tk.Frame(main_container, bg=BORDER_ACCENT, padx=1, pady=1)
    orch_card_border.pack(fill="x", pady=(0, 10))

    orch_card = tk.Frame(orch_card_border, bg=BG_CARD, padx=14, pady=8)
    orch_card.pack(fill="both", expand=True)

    orch_top = tk.Frame(orch_card, bg=BG_CARD)
    orch_top.pack(fill="x", pady=(0, 6))

    def run_both_systems():
        append_log_line("[*] Launching BOTH systems concurrently in isolated pipelines...")
        start_otc_worker()
        start_gnb_worker()

    btn_run_both = tk.Button(
        orch_top,
        text="⚡ Launch Dual-System Batch (Simultaneous OTC + GNB)",
        font=("Segoe UI", 9, "bold"),
        bg="#4338CA",
        fg="#FFFFFF",
        padx=16,
        pady=5,
        relief="flat",
        cursor="hand2",
        command=run_both_systems,
    )
    btn_run_both.pack(side="left")

    prog_label_var = tk.StringVar(value="Ready for batch execution.")
    tk.Label(
        orch_top,
        textvariable=prog_label_var,
        font=("Segoe UI", 8, "bold"),
        fg=TEXT_MUTED,
        bg=BG_CARD,
    ).pack(side="right")

    progress_bar = ttk.Progressbar(orch_card, mode="determinate", style="TProgressbar")
    progress_bar.pack(fill="x")

    # =========================================================================
    # 6. DUAL LIVE TELEMETRY CONSOLES (Side-by-Side Frosted Slate)
    # =========================================================================
    consoles_container = tk.Frame(main_container, bg=BG_CANVAS)
    consoles_container.pack(fill="both", expand=True)
    consoles_container.columnconfigure(0, weight=1, uniform="console")
    consoles_container.columnconfigure(1, weight=1, uniform="console")
    consoles_container.rowconfigure(0, weight=1)

    # --- OTC Live Console (Left) ---
    otc_term_border = tk.Frame(consoles_container, bg=BORDER_ACCENT, padx=1, pady=1)
    otc_term_border.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

    otc_term_card = tk.Frame(otc_term_border, bg=BG_CARD)
    otc_term_card.pack(fill="both", expand=True)

    otc_term_head = tk.Frame(otc_term_card, bg="#0F172A", padx=10, pady=5)
    otc_term_head.pack(fill="x")

    tk.Label(
        otc_term_head,
        text="🖥️ OTC BPS Telemetry Console",
        font=("Segoe UI", 8, "bold"),
        fg="#38BDF8",
        bg="#0F172A",
    ).pack(side="left")

    def clear_otc_log():
        otc_log_text.delete("1.0", "end")

    tk.Button(
        otc_term_head,
        text="Clear",
        font=("Segoe UI", 7),
        bg="#1E293B",
        fg="#94A3B8",
        padx=6,
        pady=1,
        relief="flat",
        command=clear_otc_log,
    ).pack(side="right")

    otc_log_frame = tk.Frame(otc_term_card, bg="#0B1329")
    otc_log_frame.pack(fill="both", expand=True)

    otc_log_text = tk.Text(
        otc_log_frame,
        font=("Consolas", 8),
        bg="#0B1329",
        fg="#BAE6FD",
        insertbackground="#38BDF8",
        wrap="word",
        relief="flat",
        padx=8,
        pady=6,
    )
    otc_scroll = ttk.Scrollbar(otc_log_frame, command=otc_log_text.yview)
    otc_log_text.configure(yscrollcommand=otc_scroll.set)
    otc_scroll.pack(side="right", fill="y")
    otc_log_text.pack(side="left", fill="both", expand=True)

    # --- GNB Live Console (Right) ---
    gnb_term_border = tk.Frame(consoles_container, bg=BORDER_ACCENT, padx=1, pady=1)
    gnb_term_border.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

    gnb_term_card = tk.Frame(gnb_term_border, bg=BG_CARD)
    gnb_term_card.pack(fill="both", expand=True)

    gnb_term_head = tk.Frame(gnb_term_card, bg="#062419", padx=10, pady=5)
    gnb_term_head.pack(fill="x")

    tk.Label(
        gnb_term_head,
        text="🏦 GNB Core Banking Telemetry Console",
        font=("Segoe UI", 8, "bold"),
        fg="#4ADE80",
        bg="#062419",
    ).pack(side="left")

    def clear_gnb_log():
        gnb_log_text.delete("1.0", "end")

    tk.Button(
        gnb_term_head,
        text="Clear",
        font=("Segoe UI", 7),
        bg="#0F3826",
        fg="#86EFAC",
        padx=6,
        pady=1,
        relief="flat",
        command=clear_gnb_log,
    ).pack(side="right")

    gnb_log_frame = tk.Frame(gnb_term_card, bg="#031A12")
    gnb_log_frame.pack(fill="both", expand=True)

    gnb_log_text = tk.Text(
        gnb_log_frame,
        font=("Consolas", 8),
        bg="#031A12",
        fg="#BBF7D0",
        insertbackground="#4ADE80",
        wrap="word",
        relief="flat",
        padx=8,
        pady=6,
    )
    gnb_scroll = ttk.Scrollbar(gnb_log_frame, command=gnb_log_text.yview)
    gnb_log_text.configure(yscrollcommand=gnb_scroll.set)
    gnb_scroll.pack(side="right", fill="y")
    gnb_log_text.pack(side="left", fill="both", expand=True)

    # =========================================================================
    # 7. LOG DISPATCHER & SANITIZED STREAMING
    # =========================================================================
    def append_log_line(msg: str) -> None:
        def do_append():
            line = str(msg).strip()
            if not line:
                return

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

    # =========================================================================
    # 8. ENTERPRISE FOOTER STATUS BAR
    # =========================================================================
    footer = tk.Frame(root, bg="#E2E8F0", height=24, padx=16, pady=3)
    footer.pack(fill="x", side="bottom")

    app_root_str = str(get_application_root())
    tk.Label(
        footer,
        text=f"Root: {app_root_str}",
        font=("Segoe UI", 7),
        fg=TEXT_MUTED,
        bg="#E2E8F0",
    ).pack(side="left")

    tk.Label(
        footer,
        text="UBL Citizen Development • Phase 1 Enterprise Isolation Active",
        font=("Segoe UI", 7, "bold"),
        fg="#0F4C81",
        bg="#E2E8F0",
    ).pack(side="right")

    set_ui_log_callback(append_log_line)
    append_log_line("[UBP Bot] Enterprise Glassmorphism Operations Cockpit ready.")

    return root


def launch_dashboard(config_path: Optional[Path] = None) -> None:
    """Launch the enterprise operations dashboard mainloop."""
    app = create_desktop_dashboard(config_path)
    app.mainloop()
