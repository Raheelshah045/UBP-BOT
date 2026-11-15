# UBP Bot — Dual-System Operations & Rejection Extraction (Phase 1)

**UBP Bot** is an enterprise-grade desktop automation platform designed for high-security banking workstations. It provides independent, parallel transaction monitoring and rejection extraction across dual banking systems: **OTC System** and **GNB System**.

---

## Workspace Directory Layout

UBP Bot maintains one shared workspace with strict data isolation:

```text
UBP-Bot/
│
├── input/                      # Shared input directory for transaction spreadsheets
│                               # e.g., OTC_Transactions.xlsx, GNB_Transactions.xlsx
├── output/                     # Shared output folder for generated reports
│                               # - OTC_Rejected_Transactions.xlsx
│                               # - GNB_Rejected_Transactions.xlsx
├── processing/                 # Transient working directory during active batch processing
├── completed/                  # Archived successfully processed spreadsheets
├── failed/                     # Ambiguous or invalid files archived for manual review
├── logs/                       # Daily execution logs with masked identifiers
├── checkpoints/                # Deduplication and checkpoint recovery SQLite databases
│   ├── browser_profile/        # Persistent browser profile for OTC system
│   └── browser_profile_gnb/    # Isolated persistent browser profile for GNB system
└── config/                     # Central JSON configuration
    └── config.json
```

---

## Phase 1 Core Architecture

### Dual Independent Banking Systems

1. **System A: OTC System**
   - Configurable OTC portal URL on main dashboard.
   - Preserves manual authentication (Credentials, CAPTCHA, OTP) with automated session detection.
   - Extracts rejected transactions from Bill Payment System (BPS).
   - **Strict Exclusion Rule**: Response codes **95** and **98** are strictly excluded from output reports.
   - Output: `output/OTC_Rejected_Transactions.xlsx`.

2. **System B: GNB System**
   - Configurable GNB portal URL on main dashboard.
   - Autonomous or manual authentication flow.
   - Extracts rejected transactions directly into `output/GNB_Rejected_Transactions.xlsx`.
   - Complete browser session and context isolation from OTC.

### Portable Deployment Architecture

- **Standalone Executable**: Built with PyInstaller as a standalone executable bundle (`UBP-Bot.exe`).
- **No System Python Required**: Operates using its bundled Python runtime without requiring Python in PATH.
- **Offline Chromium Binaries**: Uses portable browser binaries packaged in `browsers/` or connects to system browsers.
- **Flexible Browser Integration**:
  - **Bundled Chromium (Default)**: Offline Chromium binaries located in `browsers/`.
  - **System Microsoft Edge**: Set `"channel": "msedge"` in `config/config.json` to utilize the local IT-managed Edge browser.
  - **Chrome DevTools Protocol (CDP)**: Set `"cdp_url": "http://localhost:9222"` in `config/config.json` to connect to an existing running browser instance.

---

## Launching UBP Bot

### Desktop Interface (Recommended)
In the portable distribution, double-click `run_ubp_bot.bat`, or from source run:
```bash
python main.py
```

### Pre-flight Diagnostics
In the portable distribution, double-click `verify_environment.bat`, or from source run:
```bash
python main.py --diagnostics
```
Pre-flight diagnostics verify directory write permissions, core library availability, browser runtime paths, and portal reachability.

### Command-Line Execution
- **Process a Single Input Spreadsheet**:
  ```bash
  python main.py --cli --input tests/fixtures/sample_input.xlsx --output output
  ```
- **Continuous Input Directory Monitoring**:
  ```bash
  python main.py --monitor
  ```
- **Extract GNB System Rejections**:
  ```bash
  python main.py --gnb
  ```
- **Extract Both Systems Concurrently**:
  ```bash
  python main.py --all-systems
  ```
- **Run Local Mock Portal for Testing**:
  ```bash
  python main.py --mock
  ```
