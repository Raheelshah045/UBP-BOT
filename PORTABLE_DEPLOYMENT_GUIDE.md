# OTC-BOT Portable Deployment Guide for Restricted Windows Workstations

## Overview
OTC-BOT Portable is designed for high-security enterprise environments (such as bank
branches and corporate financial back-offices) where users do not have administrator
privileges, cannot install Python system-wide, and cannot run arbitrary MSI/EXE installers.

## Zero-Admin Architecture
1. **Embedded Executable:** Uses `OTC-BOT.exe` with bundled Python runtime.
2. **Private Browser Runtime:** Bundles Chromium inside `browsers/` using `PLAYWRIGHT_BROWSERS_PATH`.
3. **Zero System Writes:** All reads and writes occur inside the application directory (`input/`, `output/`, `logs/`, `checkpoints/`).
4. **No Registry Writes:** Does not touch Windows Registry or protected system directories (`C:\Program Files`, `C:\Windows`).
5. **No Credential Persistence in Binaries:** Credentials, OTPs, and cookies are never compiled into code.

## Quick Start (User Mode)
1. Copy or extract `OTC-BOT-Portable` folder to any user directory (e.g., `D:\OTC-BOT` or `C:\Users\<Username>\OTC-BOT`).
2. Double-click `run_otc_bot.bat` or `OTC-BOT.exe`.
3. Place transaction spreadsheet (`.xlsx`) in `input/` folder.
4. In the application UI, click **▶ Start Monitoring**.
5. Extracted rejected transactions will appear in `output/Rejected_Transaction_Details.xlsx`.

## Bank IT & Security Whitelisting Guide
If your workstation uses Microsoft AppLocker, CrowdStrike Falcon, or Windows Defender Application Control (WDAC):

### Option 1: Whitelist the Portable Application Directory (Recommended)
- Path Rule: Allow execution from `<User_Dir>\OTC-BOT-Portable\*`
- Publisher / Hash Rule: Whitelist `OTC-BOT.exe` and `browsers\chromium-*\chrome-win\chrome.exe`.

### Option 2: Use Pre-installed Microsoft Edge (Zero Custom Browser Binaries)
If IT security prohibits running portable browser binaries, configure `config.json`:
```json
"browser": {
  "headless": false,
  "channel": "msedge"
}
```
This instructs OTC-BOT to use the official, IT-managed Microsoft Edge browser (`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`).

### Option 3: Chrome DevTools Protocol (CDP) Remote Debugging
If subprocess creation is completely disabled by corporate policy:
1. Launch Edge/Chrome manually with: `msedge.exe --remote-debugging-port=9222`
2. In `config.json`, set:
```json
"browser": {
  "cdp_url": "http://localhost:9222"
}
```

## Pre-flight Diagnostics
Run `verify_environment.bat` or run from command line:
```cmd
OTC-BOT.exe --diagnostics
```
This inspects folder permissions, browser binary availability, and portal network reachability.
