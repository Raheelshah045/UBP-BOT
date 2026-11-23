# Security Controls & Compliance — UBP Bot

## 1. Compliance Disclaimer & Governance Notice

> [!WARNING]
> In strict accordance with UBL Citizen Development, Enterprise Architecture, Information Security, and Change Management policies, development completion **does not** constitute organizational approval or production authorization. The application is **not claimed to be vulnerability-free or production-approved**. Production deployment requires formal Information Security review, UAT sign-off, and CAB approval.

---

## 2. Threat Mitigation Matrix

| Threat Category | Potential Impact | Implemented Security Control | Enforcing Module |
| :--- | :--- | :--- | :--- |
| **Credential Exposure** | Unauthorized access to portal accounts | Zero hardcoded passwords; passwords read from OS environment or `.env`; all passwords scrubbed before saving config | `src/ubp_bot/security/secret_manager.py` |
| **Cross-System Bleed** | Session hijacking or data corruption between OTC & GNB | Separate Playwright instances, independent execution threads, separate user data profiles (`browser_profile` vs `browser_profile_gnb`) | `src/ubp_bot/services/browser_manager.py` |
| **PII / Data Leakage in Logs** | Regulatory penalty (SBNP/PCI-DSS) | Regex-based automatic sanitization of CNICs, card numbers, passwords, bearer tokens, and utility consumer numbers in all logs & UI | `src/ubp_bot/security/log_sanitizer.py` |
| **Excel Formula Injection** | Remote code execution on bank workstations viewing reports | Strings beginning with `=`, `+`, `-`, `@`, `\t`, or `\r` (including leading whitespace) are prepended with a single quote `'` | `src/ubp_bot/services/excel_reporter.py` |
| **Report Corruption / Partial Write** | Loss of audit records during crashes | Atomic writing to hidden `.tmp_*` files, file swap, and automatic generation of previous-run backup copy (`*_prev.xlsx`) | `src/ubp_bot/services/excel_reporter.py` |
| **Directory Tampering** | Writing to unauthorized system folders | Dynamic validation testing directory creation, directory traversal, and atomic probe file creation/unlinking before accepting path | `src/ubp_bot/core/config.py` |
| **Duplicate Processing** | Re-running already processed files | Cryptographic SHA-256 hashing of incoming spreadsheets; completed file hashes are blocked from re-execution | `src/ubp_bot/core/file_detector.py` |
| **Restricted Workstation Policies** | AppLocker / Group Policy blocking custom binaries | Configurable `channel: "msedge"` or `channel: "chrome"` uses sanctioned, pre-installed Windows corporate browsers | `src/ubp_bot/services/browser_manager.py` |

---

## 3. Detail of Security Subsystems

### 3.1. Credential Management & Zero-Storage Invariants
- Configuration files (`config/config.json`) saved by the application are scrubbed recursively via `sanitize_config_for_storage()`. Any dictionary key containing `password`, `secret`, `token`, `api_key`, or `auth` has its value overwritten with an empty string `""` before disk serialization.
- Credentials for GNB automated extraction are injected strictly at runtime via environment variables (`GNB_USERNAME`, `GNB_PASSWORD`) or a locally-secured `.env` file that is excluded by `.gitignore`.

### 3.2. Formula Injection Sanitization
Spreadsheet injection (CWE-1236) occurs when user-supplied transaction data or response descriptions contain arithmetic or shell execution symbols. UBP Bot sanitizes every text cell before passing it to `openpyxl`:
```python
def sanitize_cell_value(val: Any) -> Any:
    if isinstance(val, str) and val:
        stripped = val.lstrip()
        if stripped and stripped[0] in ("=", "+", "-", "@", "\t", "\r"):
            return f"'{val}"
    return val
```

### 3.3. Log Masking Invariants
All log entries passing through `get_logger()` and UI event callbacks pass through `mask_sensitive_text()`:
- **Credentials**: `password=***REDACTED***`, `"password": "***REDACTED***"`
- **Bearer Tokens**: `Bearer ***REDACTED***`
- **Pakistani CNIC**: `42101-*******-1`
- **16-Digit Card / Account Numbers**: `1234-****-****-5432`
- **Consumer Numbers in log context** (e.g., `consumer: 70085296314001`, `consumer_number=70085296314001`): `7008******4001`

Consumer numbers are masked when they appear adjacent to the keyword `consumer` in log messages. Standalone 14-digit strings not preceded by this keyword are not automatically masked — callers must invoke `mask_consumer_number()` explicitly when logging consumer IDs in isolation.

### 3.4. Browser & Context Isolation
- OTC runs with persistent user profile in `checkpoints/browser_profile`.
- GNB runs with persistent user profile in `checkpoints/browser_profile_gnb`.
- Cross-origin and cross-system cookies, IndexedDB, local storage, and service workers are physically separated into distinct Windows filesystem trees.
- Stale browser locks (`SingletonLock`, `SingletonCookie`) created by abnormal power loss or process kill are cleared safely with process PID verification before session initialization.
