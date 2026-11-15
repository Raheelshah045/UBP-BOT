"""Packaging and build script for UBP Bot Portable Enterprise Distribution.

Compiles standalone executable bundle using PyInstaller and stages a complete,
zero-install, non-administrative portable application directory.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def build_portable_distribution() -> Path:
    """Build the standalone PyInstaller executable and assemble the portable folder."""
    project_root = Path(__file__).resolve().parent.parent
    dist_dir = project_root / "dist"
    portable_root = dist_dir / "UBP-Bot-Portable"

    print(f"[*] Packaging UBP Bot from: {project_root}")
    print(f"[*] Target portable distribution: {portable_root}")

    # Step 1: Run PyInstaller to build onedir bundle
    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=UBP-Bot",
        "--onedir",
        "--noconfirm",
        "--clean",
        "--collect-all=playwright",
        "--hidden-import=pandas",
        "--hidden-import=openpyxl",
        "--hidden-import=tkinter",
        "--hidden-import=urllib.request",
        "--hidden-import=sqlite3",
        str(project_root / "main.py"),
    ]

    print("[*] Running PyInstaller compilation...")
    res = subprocess.run(pyinstaller_cmd, cwd=str(project_root), check=True)
    if res.returncode != 0:
        raise RuntimeError("PyInstaller build failed.")

    built_app_dir = dist_dir / "UBP-Bot"

    # Step 2: Prepare the final portable directory structure
    if portable_root.exists():
        try:
            shutil.rmtree(portable_root)
        except Exception:
            pass
    portable_root.mkdir(parents=True, exist_ok=True)

    # Move/Copy built onedir files into portable root
    print("[*] Assembling portable application directory...")
    for item in built_app_dir.iterdir():
        dest = portable_root / item.name
        if item.is_dir():
            shutil.copytree(str(item), str(dest), dirs_exist_ok=True)
        else:
            shutil.copy2(str(item), str(dest))

    # Step 3: Bundle required portable browser runtime (Chromium + FFmpeg) into portable_root/browsers
    # Mandatory Check: Stop build with a clear error if Chromium is missing
    browsers_dest = portable_root / "browsers"
    browsers_dest.mkdir(parents=True, exist_ok=True)
    local_app_playwright = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"

    bundled_chromium = False
    if local_app_playwright.exists():
        for ch_dir in local_app_playwright.glob("chromium-*"):
            target_ch = browsers_dest / ch_dir.name
            if not target_ch.exists():
                print(f"[*] Bundling portable browser: {ch_dir.name}...")
                shutil.copytree(str(ch_dir), str(target_ch), dirs_exist_ok=True)
            bundled_chromium = True

        for ch_head in local_app_playwright.glob("chromium_headless_shell-*"):
            target_head = browsers_dest / ch_head.name
            if not target_head.exists():
                print(f"[*] Bundling headless shell: {ch_head.name}...")
                shutil.copytree(str(ch_head), str(target_head), dirs_exist_ok=True)

        for ff_dir in local_app_playwright.glob("ffmpeg-*"):
            target_ff = browsers_dest / ff_dir.name
            if not target_ff.exists():
                print(f"[*] Bundling support runtime: {ff_dir.name}...")
                shutil.copytree(str(ff_dir), str(target_ff), dirs_exist_ok=True)

    if not bundled_chromium:
        # Check if existing browsers_dest already has it
        existing_chrome = list(browsers_dest.glob("chromium-*/chrome-win/chrome.exe"))
        if not existing_chrome:
            raise RuntimeError(
                "[ERROR] Mandatory browser runtime missing: Playwright Chromium is not installed!\n"
                "A genuinely portable OTC-BOT deployment requires offline Chromium binaries.\n"
                "Please run 'playwright install chromium' before building the portable package."
            )

    # Step 4: Create standard runtime directories
    for dir_name in ["input", "output", "logs", "checkpoints", "processing", "completed", "failed", "config"]:
        d_path = portable_root / dir_name
        d_path.mkdir(parents=True, exist_ok=True)
        gitkeep = d_path / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

    # Step 5: Copy configuration and sample input files
    sample_src = project_root / "sample_input.xlsx"
    if sample_src.exists():
        shutil.copy2(str(sample_src), str(portable_root / "sample_input.xlsx"))
        shutil.copy2(str(sample_src), str(portable_root / "input" / "sample_input.xlsx"))

    cfg_src = project_root / "config" / "config.json"
    if not cfg_src.exists():
        cfg_src = project_root / "config.json"
    if cfg_src.exists():
        (portable_root / "config").mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(cfg_src), str(portable_root / "config" / "config.json"))
        # Provide root copy for legacy backward compatibility in portable bundle
        shutil.copy2(str(cfg_src), str(portable_root / "config.json"))

    # Step 6: Create Windows batch launch scripts
    # None of these launchers call global python, py, or venv.
    # They invoke OTC-BOT.exe directly using application-relative path %~dp0.
    # A) Main Launcher
    bat_launcher = portable_root / "run_otc_bot.bat"
    bat_launcher.write_text(
        "@echo off\r\n"
        "title OTC-BOT - Portable Non-Admin Deployment\r\n"
        "cd /d \"%~dp0\"\r\n"
        "set PLAYWRIGHT_BROWSERS_PATH=%~dp0browsers\r\n"
        "echo ============================================================\r\n"
        "echo   Starting UBP Bot in Portable Non-Admin Mode\r\n"
        "echo ============================================================\r\n"
        "start \"\" \"%~dp0UBP-Bot.exe\" %*\r\n"
        "exit /b 0\r\n",
        encoding="ascii",
    )

    # B) Diagnostics Launcher
    bat_diag = portable_root / "verify_environment.bat"
    bat_diag.write_text(
        "@echo off\r\n"
        "title UBP Bot - Environment Diagnostics\r\n"
        "cd /d \"%~dp0\"\r\n"
        "set PLAYWRIGHT_BROWSERS_PATH=%~dp0browsers\r\n"
        "\"%~dp0UBP-Bot.exe\" --diagnostics\r\n"
        "echo.\r\n"
        "pause\r\n",
        encoding="ascii",
    )

    # C) Mock Portal Launcher
    bat_mock = portable_root / "run_mock_portal.bat"
    bat_mock.write_text(
        "@echo off\r\n"
        "title UBP Bot - Local Mock Portal\r\n"
        "cd /d \"%~dp0\"\r\n"
        "echo Starting Mock Portal at http://127.0.0.1:8080 ...\r\n"
        "\"%~dp0UBP-Bot.exe\" --mock\r\n"
        "pause\r\n",
        encoding="ascii",
    )

    # Step 7: Create Documentation
    doc_file = portable_root / "PORTABLE_DEPLOYMENT_GUIDE.md"
    doc_content = (
        "# UBP Bot Portable Deployment Guide for Restricted Windows Workstations\n\n"
        "## Overview\n"
        "UBP Bot Portable is designed for high-security enterprise environments (such as bank\n"
        "branches and corporate financial back-offices) where users do not have administrator\n"
        "privileges, cannot install Python system-wide, and cannot run arbitrary MSI/EXE installers.\n\n"
        "## Zero-Admin Architecture\n"
        "1. **Embedded Executable:** Uses `UBP-Bot.exe` with bundled Python runtime.\n"
        "2. **Private Browser Runtime:** Bundles Chromium inside `browsers/` using `PLAYWRIGHT_BROWSERS_PATH`.\n"
        "3. **Zero System Writes:** All reads and writes occur inside the application directory (`input/`, `output/`, `logs/`, `checkpoints/`).\n"
        "4. **No Registry Writes:** Does not touch Windows Registry or protected system directories (`C:\\Program Files`, `C:\\Windows`).\n"
        "5. **No Credential Persistence in Binaries:** Credentials, OTPs, and cookies are never compiled into code.\n\n"
        "## Quick Start (User Mode)\n"
        "1. Copy or extract `UBP-Bot-Portable` folder to any user directory (e.g., `D:\\UBP-Bot` or `C:\\Users\\<Username>\\UBP-Bot`).\n"
        "2. Double-click `run_ubp_bot.bat` or `UBP-Bot.exe`.\n"
        "3. Place transaction spreadsheet in `input/` folder:\n"
        "   - `OTC_Transactions.xlsx` for OTC system\n"
        "   - `GNB_Transactions.xlsx` for GNB system\n"
        "4. In the application UI, click **▶ Start OTC**, **▶ Start GNB**, or **⚡ Run Both Simultaneously**.\n"
        "5. Extracted rejected transactions will appear in `output/`:\n"
        "   - `OTC_Rejected_Transactions.xlsx`\n"
        "   - `GNB_Rejected_Transactions.xlsx`\n\n"
        "## Bank IT & Security Whitelisting Guide\n"
        "If your workstation uses Microsoft AppLocker, CrowdStrike Falcon, or Windows Defender Application Control (WDAC):\n\n"
        "### Option 1: Whitelist the Portable Application Directory (Recommended)\n"
        "- Path Rule: Allow execution from `<User_Dir>\\UBP-Bot-Portable\\*`\n"
        "- Publisher / Hash Rule: Whitelist `UBP-Bot.exe` and `browsers\\chromium-*\\chrome-win\\chrome.exe`.\n\n"
        "### Option 2: Use Pre-installed Microsoft Edge (Zero Custom Browser Binaries)\n"
        "If IT security prohibits running portable browser binaries, configure `config.json`:\n"
        "```json\n"
        "\"browser\": {\n"
        "  \"headless\": false,\n"
        "  \"channel\": \"msedge\"\n"
        "}\n"
        "```\n"
        "This instructs UBP Bot to use the official, IT-managed Microsoft Edge browser (`C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe`).\n\n"
        "### Option 3: Chrome DevTools Protocol (CDP) Remote Debugging\n"
        "If subprocess creation is completely disabled by corporate policy:\n"
        "1. Launch Edge/Chrome manually with: `msedge.exe --remote-debugging-port=9222`\n"
        "2. In `config.json`, set:\n"
        "```json\n"
        "\"browser\": {\n"
        "  \"cdp_url\": \"http://localhost:9222\"\n"
        "}\n"
        "```\n\n"
        "## Pre-flight Diagnostics\n"
        "Run `verify_environment.bat` or run from command line:\n"
        "```cmd\n"
        "UBP-Bot.exe --diagnostics\n"
        "```\n"
        "This inspects folder permissions, browser binary availability, and portal network reachability.\n"
    )
    doc_file.write_text(doc_content, encoding="utf-8")
    shutil.copy2(str(doc_file), str(project_root / "PORTABLE_DEPLOYMENT_GUIDE.md"))

    print(f"[✓] Portable distribution built successfully at:\n    {portable_root}")
    return portable_root


if __name__ == "__main__":
    build_portable_distribution()
