# UBP Bot Portable Deployment Guide for Restricted Windows Workstations

## Overview
UBP Bot Portable is designed for high-security enterprise environments (such as bank
branches and corporate financial back-offices) where users do not have administrator
privileges, cannot install Python system-wide, and cannot run arbitrary MSI/EXE installers.

## Zero-Admin Architecture
1. **Embedded Executable:** Uses `UBP-Bot.exe` with bundled Python runtime.
2. **Private Browser Runtime:** Bundles Chromium inside `browsers/` using `PLAYWRIGHT_BROWSERS_PATH`.
3. **Zero System Writes:** All reads and writes occur inside the application directory (`input/`, `output/`, `logs/`, `checkpoints/`).
4. **No Registry Writes:** Does not touch Windows Registry or protected system directories (`C:\Program Files`, `C:\Windows`).
5. **No Credential Persistence in Binaries:** Credentials, OTPs, and cookies are never compiled into code.

## Quick Start (User Mode)
1. Copy or extract `UBP-Bot-Portable` folder to any user directory (e.g., `D:\UBP-Bot` or `C:\Users\<Username>\UBP-Bot`).
2. Double-click `run_ubp_bot.bat` or `UBP-Bot.exe`.
3. Place transaction spreadsheet in `input/` folder:
   - `OTC_Transactions.xlsx` for OTC system
   - `GNB_Transactions.xlsx` for GNB system
4. In the application UI, click **▶ Start OTC**, **▶ Start GNB**, or **⚡ Run Both Simultaneously**.
5. Extracted rejected transactions will appear in `output/`:
   - `OTC_Rejected_Transactions.xlsx`
   - `GNB_Rejected_Transactions.xlsx`

## Bank IT & Security Whitelisting Guide
If your workstation uses Microsoft AppLocker, CrowdStrike Falcon, or Windows Defender Application Control (WDAC):

### Option 1: Whitelist the Portable Application Directory (Recommended)
- Path Rule: Allow execution from `<User_Dir>\UBP-Bot-Portable\*`
- Publisher / Hash Rule: Whitelist `UBP-Bot.exe` and `browsers\chromium-*\chrome-win\chrome.exe`.

### Option 2: Use Pre-installed Microsoft Edge (Zero Custom Browser Binaries)
If IT security prohibits running portable browser binaries, configure `config/config.json`:
```json
"browser": {
  "headless": false,
  "channel": "msedge"
}
```
This instructs UBP Bot to use the official, IT-managed Microsoft Edge browser (`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`).

### Option 3: Chrome DevTools Protocol (CDP) Remote Debugging
If subprocess creation is completely disabled by corporate policy:
1. Launch Edge/Chrome manually with: `msedge.exe --remote-debugging-port=9222`
2. In `config/config.json`, set:
```json
"browser": {
  "cdp_url": "http://localhost:9222"
}
```

## Pre-flight Diagnostics
Run `verify_environment.bat` or run from command line:
```cmd
UBP-Bot.exe --diagnostics
```
This inspects folder permissions, browser binary availability, and portal network reachability.
