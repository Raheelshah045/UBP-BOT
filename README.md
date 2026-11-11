# OTC Transaction Monitoring & Rejection Extraction Bot

A professional, modular, production-ready Python browser automation bot designed to process high-volume Bill Payment System (BPS) transactions from Over-the-Counter (OTC) banking portals with **continuous input directory monitoring** and **existing browser session detection**.

---

## Workspace Directory Layout

The bot automatically initializes and maintains the following lifecycle directory structure:

```text
OTC_Bot/
│
├── input/                      # Drop newly arrived .xlsx, .xls, or .csv files here
├── processing/                 # Holds active file while search automation runs
├── completed/                  # Successfully processed spreadsheets archived here
├── failed/                     # Malformed, corrupt, or failed files archived here
├── output/                     # Generated 4-sheet timestamped Excel reports
├── logs/                       # Daily execution logs with masked consumer numbers
├── checkpoints/                # SQLite deduplication & row-level resume database
│   └── browser_profile/        # Persistent Chromium profile preserving authenticated session
└── config/                     # Central JSON configuration
    └── config.json
```

---

## Key Features & New Capabilities

### 1. Continuous Folder Monitoring & Stability Detection
- **Continuous Watcher**: Actively monitors `input/` for new `.xlsx`, `.xls`, or `.csv` files.
- **File Stability Detection**: Detects file arrival, waits until size stops changing across multiple intervals, verifies read locks, and tests file integrity before enqueuing.
- **Temporary File Filtering**: Automatically ignores temporary Office and swap files (e.g. `~$*.xlsx`, `.tmp`).
- **Automatic Lifecycle Transitions**: Moves files from `input/` $\rightarrow$ `processing/` $\rightarrow$ `completed/` (or `failed/`). Never deletes original files.
- **Automatic Startup Scanning**: Automatically scans `input/` on startup to ingest any files placed while the bot was closed.
- **Duplicate Protection**: Uses SHA-256 content hashing in SQLite to prevent accidental reprocessing of duplicate files.

### 2. Existing OTC Portal Login Detection
The bot inspects the current browser state using prioritized DOM and element detection before asking for credentials:
- **Situation A: Portal Already Logged In**: Detects active session (`AUTHENTICATED_DASHBOARD`, `CHECK_BILL_STATUS`, `BPS_NAVIGATION`). Skips login, verifies BPS navigation, and immediately begins processing without page reloads or session disruption.
- **Situation B: Portal Login Page Open**: Displays an alert for manual authentication (Credentials, CAPTCHA, OTP), polls the browser state, and automatically detects successful authentication without requiring the user to click Continue.
- **Situation C: Browser Not Open**: Launches Chromium using the persistent profile (`checkpoints/browser_profile`), navigates to the portal, and checks whether saved session cookies allow instant entry.

### 3. Persistent Browser Profile & Remote Debugging (CDP)
- **Persistent Profile**: Uses Playwright's `launch_persistent_context` to preserve cookies and session state across restarts.
- **Session Reuse**: Keeps the browser session alive between files instead of spinning up new browser instances for each file or input row.
- **Existing Chrome Remote Debugging**:
  To attach to an existing Chrome instance, start Google Chrome with remote debugging:
  ```bash
  chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\ChromeProfile"
  ```
  Then set `"cdp_url": "http://127.0.0.1:9222"` in `config.json`.

---

## Business Classification Rules

The bot evaluates **Transaction Status** and **Response Code** together:

| Transaction Status | Response Code | Classification | Target Excel Sheet |
|---|---|---|---|
| Approved / Successful | `00` | Approved | **Sheet 2: Processing Summary** |
| Rejected | `95` | Excluded Code 95 | **Sheet 3: Exceptions & Manual Review** |
| Rejected | `98` | Excluded Code 98 | **Sheet 3: Exceptions & Manual Review** |
| Rejected | Any other code (`51`, `05`, `14`, `54`) | Rejected | **Sheet 1: Rejected Transactions** |
| Pending | Any code | Pending | **Sheet 3: Exceptions & Manual Review** |
| Unknown / Unhandled | Any code | Manual Review | **Sheet 3: Exceptions & Manual Review** |

---

## Desktop User Interface

Launch via:
```bash
python main.py
```

### Controls & Indicators
- **Directory Monitoring**: Monitored path, Watcher status, Queued file count, Active filename.
- **Portal Session**: Browser engine status, Current screen indicator, Session health badge.
- **Batch Record Statistics**: Progress bar, Total rows, Processed, Rejections, Approved, Errors.
- **Actions**:
  - `▶ Start Monitoring`: Launches background watcher and startup scan.
  - `⏹ Stop Monitoring`: Gracefully terminates folder watcher without interrupting active searches.
  - `⏸ Pause` / `▶ Resume`: Pauses queue and record processing safely.
  - `📂 Open Input`: Opens `input/` in Windows Explorer for file dropping.
  - `📂 Open Output`: Opens `output/` to inspect generated Excel reports.
  - `🔄 Reconnect Browser`: Reconnects or re-launches the persistent browser profile.

---

## Command Line Usage

### 1. Continuous Directory Monitoring Mode
```bash
python main.py --monitor
```

### 2. Single-File CLI Batch Mode
```bash
python main.py --cli --input sample_input.csv --output output
```

### 3. Start Local Mock OTC Portal
```bash
python main.py --mock
```

### 4. Run Test Suite
```bash
pytest -v
```
