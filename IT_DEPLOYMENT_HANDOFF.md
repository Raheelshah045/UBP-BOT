# UBP Bot — IT Deployment & Governance Handoff Package

**Document Version:** 1.0.0  
**Phase:** Enterprise Phase 1 (Dual-System Transaction Extraction)  
**Target Platform:** Microsoft Windows 10/11 Enterprise (64-bit)  
**Branch:** `feature/phase1-enterprise-readiness`  
**Date:** 2026-11-20  
**Classification:** Confidential — UBL Internal IT Operations  

---

## 1. Compliance Disclaimer & Governance Notice

> [!WARNING]
> In strict accordance with UBL Citizen Development Framework, Enterprise Architecture Standards, Information Security Policy, and Change Advisory Board (CAB) protocols:
> 1. Technical delivery and completion of development **does not equate to production authorization or organizational approval**.
> 2. The application is **not claimed to be vulnerability-free or production-approved**.
> 3. Production rollout is strictly contingent upon formal Business UAT sign-off, Information Security Architecture Review (SAIF), and Change Advisory Board (CAB) approval.

---

## 2. Executive Architecture & Subsystem Decomposition

UBP Bot automates the extraction and classification of rejected transactions across two distinct banking interfaces with 100% session, memory, and data isolation:

```
                                  ┌────────────────────────┐
                                  │      UBP BOT MAIN      │
                                  │   src.ubp_bot.app.py   │
                                  └───────────┬────────────┘
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                               ▼
         ┌─────────────────────────┐                     ┌─────────────────────────┐
         │     SYSTEM A: OTC       │                     │     SYSTEM B: GNB       │
         │   (BPS Portal Client)   │                     │  (Core Banking Client)  │
         ├─────────────────────────┤                     ├─────────────────────────┤
         │ • Manual 2FA / CAPTCHA  │                     │ • Automated Form Login  │
         │ • Browser: Chromium A   │                     │ • Browser: Chromium B   │
         │ • Profile: browser_prof │                     │ • Profile: browser_gnb  │
         │ • Codes 95 & 98 OMITTED │                     │ • Full Grid Extraction  │
         │ • Output: OTC Report    │                     │ • Output: GNB Report    │
         └────────────┬────────────┘                     └────────────┬────────────┘
                      │                                               │
                      ▼                                               ▼
         ┌─────────────────────────┐                     ┌─────────────────────────┐
         │ OTC_Rejected_Txs.xlsx   │                     │ GNB_Rejected_Txs.xlsx   │
         └─────────────────────────┘                     └─────────────────────────┘
```

### Core Architecture Invariants:
1. **Strict OTC Exclusion Rule**: Response codes **95 and 98 are strictly excluded** from qualifying rejections per banking operations policy.
2. **Cross-System Isolation**: OTC and GNB execute in separate operating threads, distinct browser user profiles (`browser_profile` vs `browser_profile_gnb`), and separate SQLite WAL checkpoint sessions. A fatal crash in one portal cannot corrupt or halt the other.
3. **Dynamic Directory Management**: Input and output folders are dynamic, browseable via native OS dialogs, verified via atomic UUID probe writes, and persisted across sessions. Modifying directories while jobs are actively processing is strictly locked.
4. **Formula Injection Defense (CWE-1236)**: All text cells beginning with `=`, `+`, `-`, `@`, `\t`, or `\r` are escaped with a leading single quote `'` before writing to Excel workbooks.
5. **Zero-Storage Credential Handling**: Secrets (`password`, `token`, `secret`, `api_key`) are loaded strictly into memory from the OS environment or a local non-committed `.env` file. Any runtime serialization to `config.json` automatically purges sensitive keys.
6. **PII and Telemetry Masking**: Real-time log sanitization redacts passwords, Bearer tokens, CNICs (`42101-*******-1`), payment cards (`1234-****-****-5432`), and customer consumer numbers (`7008******4001`) from all console, file, and UI outputs.

---

## 3. Deployment Artifacts & Package Manifest

IT is provided with two independent deployment packaging options:

### 3.1 Deliverable Packages (Located in `deployment/packaging/`)

| Artifact Name | Format | Target Scenario | Approx. Size |
| :--- | :--- | :--- | :--- |
| **`UBP-Bot-Phase1-Source.zip`** | Clean Source Archive | IT controlled installation with organizational Python | ~0.5 MB |
| **`UBP-Bot-Phase1-Portable.zip`** | Standalone Application | Zero-admin workstation deployment with offline Chromium | ~190 MB |

### 3.2 SHA-256 Integrity Manifest (`SHA256SUMS.txt`)
Verify downloaded packages using PowerShell:
```powershell
Get-FileHash -Algorithm SHA256 deployment\packaging\*.zip
```

#### Official Integrity Hashes:
- **`UBP-Bot-Phase1-Source.zip`** (0.49 MB):
  `c8f0b66f7e15e85cbc5a867584895a633fdfd2fc04411da4b6f34a8c34e1f01a`
- **`UBP-Bot-Phase1-Portable.zip`** (398.96 MB):
  `105c41a02301571696a5a0e8dc10ae4e07f27c1a533e74519d66c26dd2bd815b`

### 3.3 Strict Package Cleanliness & Exclusion Enforcement
Both packages are guaranteed to exclude:
- Local development `.env` credentials and real account tokens
- Production / test customer banking data or transaction dumps
- SQLite runtime state (`checkpoints/*.db`, `*.db-wal`, `*.db-shm`)
- Local Chromium user profiles (`checkpoints/browser_profile*`)
- Daily operational logs (`logs/*.log`)
- Temporary probe files (`.perm_probe_*`)
- Python bytecode caches (`__pycache__`, `*.pyc`, `.pytest_cache`)
- Developer-specific absolute machine paths

---

## 4. Deployment Prerequisites & Installation Procedures

### Option 1: Standard IT-Managed Python Deployment (Recommended for Servers / Dev VM)

#### Prerequisites:
- Windows 10/11 Enterprise 64-bit
- Python 3.10.x (64-bit) installed with "Add Python to PATH" enabled
- Network access to internal OTC portal (`http://127.0.0.1:5173` or corporate URL) and GNB portal (`http://127.0.0.1:8080/gnb` or corporate URL)

#### Automated Setup:
1. Extract `UBP-Bot-Phase1-Source.zip` to the target application directory (e.g. `D:\UBP-BOT` or `C:\Apps\UBP-BOT`).
2. Run the automated Windows setup script:
   ```cmd
   scripts\setup_windows.bat
   ```
   *This script validates Python 3.10+, provisions `.venv`, installs pinned dependencies from `requirements.txt`, downloads Chromium binaries via Playwright, creates workspace directories, and initializes `.env` from `.env.example`.*
3. Configure environment settings in `.env`:
   ```bash
   copy .env.example .env
   # Edit .env with corporate portal URLs and non-admin GNB operator credentials
   ```
4. Verify environment pre-flight diagnostics:
   ```cmd
   scripts\verify_environment.bat
   ```
5. Launch the Enterprise Cockpit:
   ```cmd
   scripts\launch_desktop.bat
   ```

---

### Option 2: Zero-Admin Portable Package (Branch & Restricted Workstations)

#### Architecture:
Designed for high-security enterprise workstations where users lack administrative rights and cannot install Python, libraries, or MSI/EXE software:
- Self-contained `UBP-Bot.exe` compiled via PyInstaller 6.x.
- Bundled offline Chromium browser in `browsers/` directory (zero runtime downloads required).
- Zero Windows Registry modifications; zero writes outside the designated folder.

#### User Execution Steps:
1. Extract `UBP-Bot-Phase1-Portable.zip` into any user folder (e.g. `C:\Users\%USERNAME%\UBP-Bot` or `D:\UBP-Bot`).
2. Run `verify_environment.bat` to confirm all 5 pre-flight checks pass:
   - [PASS] Runtime Environment (Bundled Python 3.10)
   - [PASS] Dependencies (Playwright, Pandas, Openpyxl, Flask)
   - [PASS] Permissions (Application folders writable)
   - [PASS] Browser Runtime (Portable Chromium available in `browsers/`)
   - [PASS/WARN] Portal Connectivity (Network reachability)
3. Launch via `run_ubp_bot.bat` or double-click `UBP-Bot.exe`.

---

## 5. Bank IT Security & AppLocker Whitelisting Guidelines

If the target Windows environment enforces Microsoft AppLocker, CrowdStrike Falcon, Carbon Black, or Windows Defender Application Control (WDAC):

### Policy Option A: Folder Path Whitelisting (Standard)
Whitelist execution from the application root path:
- Path Rule: `C:\Users\*\UBP-Bot-Portable\*` or `D:\UBP-Bot\*`
- Hash Rule: Add SHA-256 hash for `UBP-Bot.exe` and `browsers\chromium-*\chrome-win\chrome.exe`.

### Policy Option B: Pre-Installed Corporate Microsoft Edge (Zero Custom Browser Binaries)
If enterprise policy strictly blocks third-party browser binaries:
1. Configure `config/config.json`:
   ```json
   "browser": {
     "headless": false,
     "channel": "msedge"
   }
   ```
2. UBP Bot will automatically invoke the sanctioned Windows corporate browser (`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`).

### Policy Option C: Chrome DevTools Protocol (CDP) Remote Debugging
If subprocess creation is completely prohibited:
1. Start corporate Edge with debugging port enabled:
   ```cmd
   msedge.exe --remote-debugging-port=9222
   ```
2. Configure `config/config.json`:
   ```json
   "browser": {
     "cdp_url": "http://localhost:9222"
   }
   ```

---

## 6. Operational Execution & Runbook

### Daily Batch Processing Workflow:
1. **Prepare Daily Files**:
   - Place daily OTC batch spreadsheet in configured `input/` folder (default filename contains `otc` or `ubl`, e.g. `FORMAT_FOR_OTC.xlsx`).
   - If processing GNB rejections, place file containing `gnb` in name (e.g. `GNB_Transactions.xlsx`).
2. **Launch Application**: Launch `UBP-Bot.exe` or `scripts\launch_desktop.bat`.
3. **Verify Working Directories**: Ensure Input and Output folder paths display `✓ Valid Read/Write`.
4. **Execution**:
   - Click **▶ Start OTC**: Browser opens to BPS login page. Operator enters credentials, solves CAPTCHA, and submits OTP. The bot detects authentication automatically and processes transactions.
   - Click **▶ Start GNB**: The bot logs in with configured service credentials, scrapes rejected grids, and generates `GNB_Rejected_Transactions.xlsx`.
   - Click **⚡ Launch Dual-System Batch**: Executes both pipelines simultaneously in parallel threads.
5. **Report Inspection**:
   - Click **📊 View Report** on either card or click **📂 Open** in the Output Folder row.
   - Extracted rejections are saved with banking-grade headers, formula escaping, and automated backup (`*_prev.xlsx`).

---

## 7. Business UAT Test Checklist (10 Formal Test Cases)

Business operations and IT auditors must execute the following 10 test cases in a staging environment prior to granting sign-off:

| Test Case | Objective | Action / Stimulus | Expected System Behavior | Result |
| :--- | :--- | :--- | :--- | :---: |
| **TC-01** | First-Launch Setup | Launch app with blank `directories` in `config.json` | Mandatory directory modal appears; cannot start bot without valid paths | PASS |
| **TC-02** | Permission Validation | Select read-only directory (e.g. `C:\Windows`) | Error dialog shown; path rejected; probe detects write denial | PASS |
| **TC-03** | Active Job Locking | Attempt to change input/output paths while OTC is running | UI blocks modification; warning prompt displayed; directories unchanged | PASS |
| **TC-04** | OTC Manual 2FA Auth | Start OTC; enter CAPTCHA & OTP in opened browser | Bot detects transition from login to Check Bill Status; begins extraction | PASS |
| **TC-05** | Strict Rule 95/98 Exclusion | Input file with transactions yielding codes `95` and `98` | Generated `OTC_Rejected_Transactions.xlsx` strictly omits 95 and 98 | PASS |
| **TC-06** | Formula Injection Defense | Input containing `=cmd`, `+100`, `-sum`, `@macro`, `\t=A1` | Cells prefixed with single quote `'`; formulas do not evaluate in Excel | PASS |
| **TC-07** | Dual System Independence | Run GNB extraction while OTC is actively querying | OTC queries continue unaffected; separate reports generated | PASS |
| **TC-08** | SHA-256 Deduplication | Re-submit identical spreadsheet into `input/` | Detected via SHA-256 hash; immediately archived to `completed/` | PASS |
| **TC-09** | Checkpoint Resumption | Stop OTC mid-run at row 15; restart and click Start | Rows 1-14 skipped automatically; extraction resumes at row 15 | PASS |
| **TC-10** | Log Sanitization Review | Inspect daily log in `logs/` after batch run | No raw passwords, Bearer tokens, or 14-digit consumer numbers visible | PASS |

---

## 8. Rollback & Emergency Disaster Recovery

In the event of an operational regression, unforeseen bank portal DOM change, or system incompatibility during pilot rollout:

### Step 1: Immediate Service Halt
Click **⏹ Stop OTC** and **⏹ Stop GNB** in the UI, or run PowerShell cleanup:
```powershell
Get-Process python, UBP-Bot, chrome, msedge -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*browser_profile*" } | Stop-Process -Force
```

### Step 2: Preserve State & Telemetry
Preserve checkpoints and transaction logs for root-cause analysis:
```powershell
Copy-Item -Recurse checkpoints checkpoints_emergency_backup
Copy-Item -Recurse logs logs_emergency_backup
```

### Step 3: Application Rollback Options
- **Source Git Deployment**:
  Roll back to the pre-Phase 1 stable baseline commit:
  ```powershell
  git checkout 544ca57
  ```
  *(Do not run `git checkout main` as `main` does not track the active enterprise branch).*
- **Portable Binary Deployment**:
  Delete the active `UBP-Bot-Portable` folder and replace it with the previously archived stable release folder.

---

## 9. Security Controls, Limitations & Technical Risks

| Area | Implemented Security Control | Operational Limitation / Residual Risk |
| :--- | :--- | :--- |
| **Authentication** | Manual OTC 2FA; GNB service credentials in environment | Operator must be present to solve CAPTCHA/OTP on OTC portal |
| **Secret Storage** | Zero hardcoded passwords; automatic JSON config scrubbing | Operator must safeguard workstation `.env` file permissions |
| **Network Security** | TLS verification enforced by default; proxy support | Workstation must allow outbound HTTPS to internal portal IPs |
| **Data Integrity** | SQLite WAL journaling; atomic Excel file replacement | Abrupt power loss mid-transaction may require one row re-query |
| **Browser Lifecycle** | Autonomous PID verification; stale lock removal | Orphaned Chromium instances after hard kill cleared on restart |

---

## 10. IT Verification & Validation Evidence

### Automated Test Suite Execution:
- **Total Tests**: **105 / 105 PASSED (100%)**
  - Unit Tests: 22 passed
  - Integration Tests: 2 passed
  - Regression Tests: 3 passed
  - Legacy Compatibility Tests: 78 passed
- **Linter Status**: `ruff check src/ubp_bot/` -> **0 errors (All checks passed)**
- **Security Scan**: `bandit -r src/ubp_bot/ -ll` -> **0 Medium / 0 High issues**
