# Deployment Readiness & Governance Guide — UBP Bot Phase 1

## 1. Governance & Authorization Notice

> [!IMPORTANT]
> Formal delivery of Phase 1 enterprise readiness **does not equate to production authorization or organizational sign-off**. In compliance with IT Governance, Enterprise Architecture, Information Security, and Change Advisory Board (CAB) protocols, the following prerequisites must be fulfilled before deployment to branch workstations:
> 1. Comprehensive UAT execution by designated operations business owners.
> 2. Information Security SAIF/Risk assessment and architecture audit.
> 3. Standard Change Request (CR) submission and approval.

---

## 2. Deployment Packaging Options

UBP Bot supports two deployment models:

### Option A: Standard Python Corporate Deployment
1. **Target Machine Requirements**:
   - Windows 10/11 Enterprise 64-bit.
   - Python 3.10.x (64-bit).
   - Network connectivity to internal BPS and GNB portal hostnames/IPs.
2. **Setup Commands**:
   ```powershell
   git clone https://github.com/Raheelshah045/UBP-BOT.git
   cd UBP-BOT
   git checkout feature/phase1-enterprise-readiness
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   playwright install chromium
   ```
3. **Configuration**:
   Copy `.env.example` to `.env` and set environment variables as necessary:
   ```powershell
   Copy-Item .env.example .env
   ```

### Option B: Standalone Portable Binary (PyInstaller)
For workstations with restricted administrative privileges or where installing Python is restricted by AppLocker:
1. Build the standalone portable package:
   ```powershell
   python scripts/build_portable_package.py
   ```
2. The compiled standalone binary and bundled configuration will be placed in `deployment/dist/UBP-Bot/`.
3. Copy the folder to target workstation (e.g. `C:\Users\<User>\AppData\Local\Programs\UBP-Bot`).
4. Set `"channel": "msedge"` in `config/config.json` to utilize the sanctioned, pre-installed Windows corporate browser without requiring external Chromium downloads.

---

## 3. UAT Execution Checklist

Before granting production authorization, execute the following UAT test cases:

- [ ] **TC-01: Directory Permission Validation**
  - Launch application without configured directories.
  - Verify mandatory first-launch setup appears.
  - Point to a valid folder -> Verify write probe passes.
  - Point to a read-only folder -> Verify error message displays and folder is rejected.
- [ ] **TC-02: OTC Manual Authentication**
  - Click "Start OTC" with valid file in input directory.
  - Verify browser opens to BPS login page.
  - Enter credentials, CAPTCHA, and OTP.
  - Verify bot automatically detects authentication and transitions to Check Bill Status.
- [ ] **TC-03: Strict Exclusion of Codes 95 & 98**
  - Run input file containing records with expected response codes 95 and 98.
  - Verify resulting `output/OTC_Rejected_Transactions.xlsx` **omits codes 95 and 98**.
- [ ] **TC-04: Formula Injection Protection**
  - Provide input file with consumer numbers or response text prefixed with `=`, `+`, `-`, `@`.
  - Open generated Excel report and verify symbols are escaped with a leading single quote `'` and do not execute.
- [ ] **TC-05: GNB System Independence**
  - Run GNB extraction while OTC is running or stopped.
  - Verify separate browser profile (`browser_profile_gnb`) is used.
  - Verify separate report (`GNB_Rejected_Transactions.xlsx`) is generated.
- [ ] **TC-06: File Idempotency & Deduplication**
  - Re-place an identical input spreadsheet into `input/`.
  - Verify the bot identifies matching SHA-256 hash and immediately archives it to `completed/` without re-running queries.
- [ ] **TC-07: Resumption from Checkpoint**
  - Interrupt batch mid-run (click "Stop OTC" or close app).
  - Restart bot and click "Start OTC".
  - Verify previously completed rows are skipped and processing resumes from the uncompleted row.

---

## 4. Rollback Procedure

If operational abnormalities, portal changes, or unforeseen network regressions occur during rollout:

1. **Immediate Service Halt**:
   - Click **⏹ Stop OTC** and **⏹ Stop GNB** in the dashboard, or terminate the process.
   - Run process cleanup:
     ```powershell
     Get-Process chrome, msedge | Where-Object { $_.CommandLine -like "*browser_profile*" } | Stop-Process -Force
     ```
2. **Preserve Checkpoint & Audit State**:
   - Copy `checkpoints/` and `logs/` to a backup location:
     ```powershell
     Copy-Item -Recurse checkpoints checkpoints_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')
     Copy-Item -Recurse logs logs_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')
     ```
3. **Revert Application Code**:
   - If rolling back from git branch:
     ```powershell
     git checkout main
     ```
   - If rolling back portable executable, replace the folder with the previously archived stable release folder.
4. **Notify Incident Management**:
   - Record batch ID and attach relevant sanitized log file from `logs/`.
