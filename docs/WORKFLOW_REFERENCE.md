# Workflow Reference — UBP Bot Phase 1

This document describes the operational workflows for the UBP Bot system.

---

## 1. System A: OTC BPS Portal Workflow

The OTC workflow handles bill payment verification through the BPS web portal:

```mermaid
sequenceDiagram
    autonumber
    actor Operator as Bank Operator
    participant UI as Desktop Dashboard
    participant QM as Queue Manager
    participant Pipe as Pipeline Coordinator
    participant Browser as Browser Manager
    participant Portal as OTC BPS Portal
    participant DB as SQLite Checkpoint DB
    participant Excel as Excel Reporter

    Operator->>UI: Click "Start OTC"
    UI->>QM: Start monitoring worker (allowed: OTC)
    QM->>Pipe: Run batch on incoming file
    Pipe->>Browser: Launch persistent session (Profile: otc)
    Browser->>Portal: Open Portal URL

    alt Operator Not Logged In
        Pipe->>UI: Prompt operator to complete login, CAPTCHA, 2FA
        Operator->>Portal: Enter credentials, CAPTCHA, OTP
        Portal-->>Pipe: Detect authenticated state
    end

    Pipe->>Portal: In-page navigate to Check Bill Status
    loop For Each Consumer Number in Batch
        Pipe->>Portal: Fill bank, consumer number, date
        Pipe->>Portal: Submit search (Click / Enter)
        Portal-->>Pipe: Render results table
        Pipe->>Portal: Extract table rows across pagination
        Pipe->>Pipe: Classify transactions (Strict: Exclude 95 & 98)
        Pipe->>DB: Record row status & save extracted transactions (WAL commit)
        Pipe->>UI: Update progress counter & progress bar
    end

    Pipe->>Excel: Generate OTC_Rejected_Transactions.xlsx (Qualifying only)
    Excel-->>Pipe: Atomic file write (.tmp_ -> replace, backup created)
    Pipe->>QM: File completed
    QM->>UI: Update UI status badge & log completion
```

### Key Business Rule Enforcement
- **Excluded Codes**: If `response_code == '95'` or `response_code == '98'`, the transaction is labeled `Excluded Rejection` with `is_qualifying_rejection = False`. It is **omitted** from `OTC_Rejected_Transactions.xlsx`.
- **Approved Transactions**: Codes `00` or statuses containing `APPROVED`/`SUCCESSFUL` are labeled `Approved` with `is_qualifying_rejection = False`.
- **Qualifying Rejections**: Status `REJECTED`, `DECLINED`, `FAILED`, etc. with non-approved, non-excluded codes (e.g. `51`, `05`) are labeled `Rejected` with `is_qualifying_rejection = True` and exported to the final Excel report.

---

## 2. System B: GNB Core Banking Portal Workflow

The GNB workflow extracts rejected transactions from the core banking network:

```mermaid
sequenceDiagram
    autonumber
    participant UI as Desktop Dashboard
    participant GNB as GNB Client Worker (Thread)
    participant Browser as Playwright Context (Profile: gnb)
    participant Portal as GNB Web Portal
    participant Excel as Excel Reporter

    UI->>GNB: Click "Start GNB" / Trigger worker
    GNB->>Browser: Launch isolated Playwright instance
    GNB->>Portal: Navigate to GNB Login URL
    alt Automated Credentials Available
        GNB->>Portal: Submit username & password from secure env
    else Manual Login Required
        GNB->>UI: Prompt operator to authenticate in browser
    end
    Portal-->>GNB: Authenticated state detected

    GNB->>Portal: Navigate to Rejected Transactions URL
    GNB->>Portal: Query rejected transaction records
    GNB->>Portal: Scrape failed & rejected transactions
    GNB->>Excel: Generate GNB_Rejected_Transactions.xlsx
    Excel-->>GNB: Atomic file write (.tmp_ -> replace)
    GNB->>UI: Publish completion status & rejection count
    GNB->>Browser: Clean context shutdown
```

---

## 3. Continuous Directory Monitoring Workflow

```mermaid
flowchart TD
    Start([Continuous Directory Monitor]) --> Scan[Scan Configured Input Folder]
    Scan --> Find{Files Found?}
    Find -- No --> Sleep[Wait Poll Interval 3.0s] --> Scan
    Find -- Yes --> Filter[Filter out ~$ and .tmp files]
    Filter --> Stability[Check File Write Stability]
    Stability --> Stable{Size Stable & Unlocked?}
    Stable -- No --> Sleep
    Stable -- Yes --> Hash[Compute SHA-256 Hash]
    Hash --> Dedupe{Already Completed in DB?}
    Dedupe -- Yes --> MoveComp[Archive Duplicate to completed/] --> Sleep
    Dedupe -- No --> Struct[Validate Structure & Columns]
    Struct --> Valid{Headers Valid?}
    Valid -- No --> MoveFail[Move Invalid File to failed/] --> Sleep
    Valid -- Yes --> Route[Identify Target: OTC or GNB]
    Route --> MoveProc[Move to processing/]
    MoveProc --> Exec[Execute Subsystem Automation Pipeline]
    Exec --> Success{Extraction Succeeded?}
    Success -- Yes --> ArcComp[Archive to completed/ & Record Hash] --> Sleep
    Success -- No --> ArcFail[Move to failed/ & Record Error] --> Sleep
```

---

## 4. Dynamic Directory Configuration Workflow

```mermaid
flowchart LR
    Launch([App Launch]) --> Check{Directories Valid in config.json?}
    Check -- Yes --> Open[Open Dashboard]
    Check -- No --> Modal[Mandatory Setup Dialog]
    Modal --> Pick[User Selects Folders]
    Pick --> Verify[Probe Read & Write Permissions]
    Verify --> Ok{Valid R/W?}
    Ok -- No --> ShowErr[Display Error Dialog] --> Pick
    Ok -- Yes --> Save[Save to config.json & Open Dashboard]
    Open --> Change[User Clicks 'Change Input/Output']
    Change --> Active{Processing Active?}
    Active -- Yes --> Warn[Show Warning: Blocked During Run]
    Active -- No --> Browse[Folder Picker Dialog]
    Browse --> Canceled{User Canceled?}
    Canceled -- Yes --> Keep[Keep Prior Valid Path]
    Canceled -- No --> Validate[Verify Permissions]
    Validate --> Persist[Persist to config.json Immediately]
```

---

## 5. Checkpoint, Recovery, and Resumption Workflow

1. **Batch Identification**: A unique batch identifier is generated based on file path and last modification timestamp (`batch_<sha256[:12]>`).
2. **Batch Registration**: Inserted into `batches` table in SQLite (`processing_checkpoint.db`).
3. **Processed Rows Check**: Query `SELECT row_number FROM processed_rows WHERE batch_id = ?`.
4. **Row Skip**: If row index exists in completed row list, the bot skips to the next unprocessed row without repeated portal queries.
5. **Session Expiry Recovery**: If session expires during processing, automation halts, notifies operator, recovers authentication, navigates back to Check Bill Status, and resumes from current row.
6. **Graceful Stop**: If operator clicks "Stop OTC" or "Stop GNB", current row query finishes, row result is committed to DB, and batch is marked `STOPPED`. Checkpoint is preserved.
