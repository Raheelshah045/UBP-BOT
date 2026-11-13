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

### Zero-Admin Portable Deployment

- **Self-Contained Executable**: Bundled with embedded Python runtime via PyInstaller.
- **No System Python Required**: Operates without Python in PATH or administrative privileges.
- **Offline Chromium Binaries**: Uses application-controlled browser binaries in `browsers/`.
- **IT Whitelisting Compliant**: Fully compatible with AppLocker, CrowdStrike Falcon, and Microsoft Edge channels.

---

## Launching UBP Bot

### Desktop Interface (Recommended)
Double-click `run_ubp_bot.bat` or run:
```bash
python main.py
```

### Pre-flight Diagnostics
Double-click `verify_environment.bat` or run:
```bash
python main.py --diagnostics
```

### Mock Portals for Offline Testing
```bash
python main.py --mock
```
