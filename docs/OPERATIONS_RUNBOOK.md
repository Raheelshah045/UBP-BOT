# Operations Runbook — UBP Bot Phase 1

This runbook provides end-to-end operational instructions for Bank Operations Specialists using UBP Bot.

---

## 1. Daily Preparation & Pre-Flight Check

1. Open PowerShell or a command terminal in the application directory.
2. Run the system diagnostics check before processing transactions:
   ```powershell
   python main.py --diagnostics
   ```
   Confirm all checks return `[PASS]`. If any check reports `[FAIL]`, consult Section 6 (Troubleshooting).
3. Start the application:
   ```powershell
   python main.py
   ```

---

## 2. Directory Configuration

1. On first launch, the **Working Directory Configuration** dialog will appear automatically.
2. Select an **Input Spreadsheet Folder** where incoming transaction files will be placed.
3. Select an **Output Reports Folder** where generated rejection reports will be saved.
4. Click **Confirm & Start Bot**. The bot verifies read and write permissions and creates dynamic paths.
5. To change directories later:
   - Click **📁 Change Input...** or **📁 Change Output...** in the top card.
   - Note: Path changes are disabled while active batch processing is running.

---

## 3. Standard Daily Processing Workflows

### 3.1. Workflow A: OTC Bill Payment Verification
1. Place the daily OTC input spreadsheet (e.g. `OTC_Transactions_20261120.xlsx`) into the configured **Input Folder**.
2. Click **▶ Start OTC**.
3. If an authenticated session is not already open, the bot prompts:
   `"Waiting for manual OTC login, CAPTCHA, and 2FA OTP..."`
4. The Chromium browser window opens to the BPS portal login screen.
5. **Enter your bank operator credentials, visual CAPTCHA, and 2FA SMS/App OTP.**
6. Once authenticated, the bot automatically detects session readiness, navigates to **BPS -> Check Bill Status**, and executes queries row-by-row.
7. Monitor progress on the **Determinate Progress Bar** and **OTC Live Console**.
8. Upon batch completion:
   - The original file is moved to `completed/`.
   - The qualifying rejection report is saved to `output/OTC_Rejected_Transactions.xlsx`.
   - Codes `95` and `98` are automatically excluded from the report.

### 3.2. Workflow B: GNB Core Banking Rejection Extraction
1. If processing specific GNB Transaction IDs, place a file with `GNB` in the filename (e.g. `GNB_Input.xlsx`) into the **Input Folder**.
2. Click **▶ Start GNB**.
3. The GNB worker launches an independent automated browser session.
4. The bot queries failed/rejected transactions and generates `output/GNB_Rejected_Transactions.xlsx`.
5. Progress and rejection counts appear in the green **GNB Live Console**.

### 3.3. Workflow C: Concurrent Dual-System Execution
1. To run both systems in parallel, click **⚡ Run Both Concurrently**.
2. OTC and GNB run in independent threads with dedicated browser contexts and isolated consoles.

---

## 4. Operational Controls (Pause, Stop, Resume)

- **Stopping a Run**: Click **⏹ Stop OTC** or **⏹ Stop GNB**. The bot safely finishes the currently processing row, commits the result to the SQLite checkpoint database, and pauses cleanly.
- **Resuming an Interrupted Run**: Simply re-click **▶ Start OTC**. The bot reads existing checkpoints from `checkpoints/processing_checkpoint.db` and immediately resumes from the first uncompleted row without re-querying completed transactions.

---

## 5. Locating and Opening Output Reports

1. Click **📊 Open** next to the Output Folder path in the dashboard to open Windows Explorer directly at the output location.
2. Two clean, formatted workbooks are produced:
   - `OTC_Rejected_Transactions.xlsx`: Bank navy header, contains all qualifying rejected bills (excluding codes 95 and 98).
   - `GNB_Rejected_Transactions.xlsx`: Forest green header, contains failed core banking transactions.
3. If a report with the same name existed previously, the bot automatically created a backup copy named `*_prev.xlsx`.

---

## 6. Troubleshooting Guide

| Issue / Symptom | Root Cause | Solution |
| :--- | :--- | :--- |
| **"Directory write permission denied"** | Selected folder is read-only or restricted by Windows ACL | Select a folder inside your user profile (e.g. `Documents` or `Desktop`), or request IT to grant write access. |
| **"File is currently in use or open in Excel"** | Input file is locked by a Microsoft Excel window | Close Excel on your workstation. The bot will automatically retry and move the file safely. |
| **"Session expired mid-batch"** | OTC portal session timed out during a long batch | Follow the prompt in the browser window to re-enter credentials/OTP. The bot will automatically detect login and resume from the current row. |
| **"AppLocker blocked Chromium binary"** | Workstation group policy forbids running binaries outside Program Files | In `config/config.json`, set `"channel": "msedge"`. The bot will automatically switch to the pre-installed corporate Microsoft Edge browser. |
| **"Stale browser profile lock detected"** | Previous run crashed or was killed via Task Manager | The bot automatically detects and clears `SingletonLock` on launch. If persistent, close all Chrome/Edge processes and restart. |
