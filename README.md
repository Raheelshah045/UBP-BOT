# UBP Bot — Phase 1 Enterprise Implementation

**UBP Bot** is an enterprise-grade desktop automation and transaction rejection extraction platform designed for high-security banking workstations. It delivers independent, parallel monitoring, query automation, and rejection extraction across dual banking systems: **System A: OTC BPS Portal** and **System B: GNB Core Banking Portal**.

---

## 1. Enterprise Architecture & Directory Organization

The codebase is organized into modular packages ensuring clear separation of responsibilities, strict cross-system data isolation, and comprehensive maintainability:

```text
UBP-BOT/
│
├── main.py                             # Root application entrypoint (delegates to src.ubp_bot.app)
├── README.md                           # Operational overview and quickstart
├── pyproject.toml                      # Modern packaging configuration (PEP 621)
├── requirements.txt                    # Locked dependency requirements
├── .env.example                        # Template for local environment variables
├── .gitignore                          # Excludes secrets, databases, reports, and binaries
│
├── src/
│   └── ubp_bot/                        # Canonical modular enterprise package
│       ├── __init__.py                 # Package metadata and version info
│       ├── app.py                      # Application orchestrator, CLI handler, and entrypoint
│       │
│       ├── ui/                         # Presentation Layer (Enterprise Light 8px Grid Theme)
│       │   ├── __init__.py
│       │   ├── dashboard.py            # Glassmorphism dashboard, dual terminals, live stats
│       │   └── dialogs.py              # Directory picker dialogs with read/write permission probes
│       │
│       ├── core/                       # Core Automation & Workflow Engine
│       │   ├── __init__.py
│       │   ├── config.py               # Path resolution, dynamic directory persistence, env loading
│       │   ├── queue_manager.py        # Asynchronous directory monitoring, queue lifecycle
│       │   ├── file_detector.py        # Ingestion, stability checks, hashing, archival moves
│       │   └── pipeline.py             # Batch coordinator, SQLite WAL checkpointing, resume logic
│       │
│       ├── portals/                    # Banking Portal Automation Clients
│       │   ├── __init__.py
│       │   ├── otc_client.py           # OTC manual login detection, search, pagination, 95/98 exclusion
│       │   └── gnb_client.py           # GNB isolated worker thread, automated login, query extraction
│       │
│       ├── services/                   # Shared Infrastructure & Utilities
│       │   ├── __init__.py
│       │   ├── excel_reporter.py       # Banking-grade Excel export with formula injection defense
│       │   ├── diagnostics.py          # Pre-flight environment, dependency, and network diagnostics
│       │   └── browser_manager.py      # Playwright browser lifecycle, persistent profile isolation
│       │
│       └── security/                   # Governance & Data Protection
│           ├── __init__.py
│           ├── secret_manager.py       # Credential scrubbing and zero-storage configuration
│           └── log_sanitizer.py        # Real-time masking of CNICs, card numbers, passwords, tokens
│
├── tests/                              # Comprehensive Automated Test Suite
│   ├── unit/                           # Isolated component unit tests
│   ├── integration/                    # Browser automation and cross-system isolation tests
│   ├── regression/                     # Response code 95/98 exclusion and idempotency tests
│   └── fixtures/                       # Test spreadsheets and canonical format fixtures
│
├── docs/                               # Enterprise Documentation Suite
│   ├── ARCHITECTURE.md                 # System architecture and data flow diagrams
│   ├── MODULE_REFERENCE.md             # Function-level technical reference for every module
│   ├── WORKFLOW_REFERENCE.md           # End-to-end workflows (OTC, GNB, Monitoring, Resumption)
│   ├── SECURITY_CONTROLS.md            # Threat model, PII masking, formula injection defenses
│   ├── TESTING.md                      # Test suite organization and execution commands
│   ├── OPERATIONS_RUNBOOK.md           # Step-by-step user guide for bank operations specialists
│   └── DEPLOYMENT_READINESS.md         # Packaging, UAT checklist, and rollback procedures
│
└── deployment/                         # Packaging & Build Specifications
    ├── build/
    └── packaging/
```

---

## 2. Core Functional Scope (Phase 1)

1. **Independent Dual-System Operations**:
   - **System A (OTC BPS Portal)**: Operator-assisted manual login (supporting visual CAPTCHA & 2FA OTP), dynamic in-page navigation, bill search, and multi-page table extraction.
   - **System B (GNB Portal)**: Automated or configured authentication in an isolated worker thread and profile.
   - Complete browser context, cookie, socket, and execution isolation between OTC and GNB.
2. **Strict Business Rule Enforcement**:
   - OTC response codes **`95` and `98` are strictly excluded** from output reports.
   - Code `00` and `APPROVED` transactions are marked approved (non-qualifying).
   - Only qualifying rejections (e.g. `51`, `05`) are compiled into `OTC_Rejected_Transactions.xlsx`.
3. **Dynamic Directory Management**:
   - Customizable Input and Output folders selectable via OS browse dialogs.
   - Selected folders are immediately probed for read and write permissions and persisted across restarts.
   - Path changes are locked during active batch execution to prevent race conditions.
4. **Security & Data Sanitization**:
   - Formulas starting with `=`, `+`, `-`, `@`, `\t`, `\r` are escaped with a leading single quote `'`.
   - Passwords and tokens are scrubbed before saving configuration to disk.
   - Pakistani CNICs, payment card/account numbers, passwords, and tokens are automatically masked in all logs and UI feeds.
5. **Idempotency & Checkpoint Recovery**:
   - Cryptographic SHA-256 deduplication prevents accidental duplicate file processing.
   - SQLite WAL-mode checkpoint database records row-by-row status, enabling instant resumption of interrupted batches.

---

## 3. Quickstart & Execution Guide

### Desktop GUI Mode (Recommended)
```powershell
python main.py
```
Launches the high-contrast enterprise light dashboard with side-by-side OTC and GNB cards, dynamic folder pickers, progress bar, and real-time consoles.

### Pre-Flight System Diagnostics
```powershell
python main.py --diagnostics
```
Validates Python runtime, library dependencies, browser executable paths, folder read/write permissions, and portal reachability.

### Automated Test Suite Execution
```powershell
pytest
```
Executes all unit, integration, and regression tests across the repository.

### Performance Benchmarking
```powershell
python scripts/benchmark_performance.py
```
Profiles startup, 20-record OTC batch, 100-record OTC batch, GNB extraction, and simultaneous dual execution against a local portal mock.

---

## 4. Documentation Links

- [Architecture Specification](docs/ARCHITECTURE.md)
- [Module Technical Reference](docs/MODULE_REFERENCE.md)
- [Workflow Reference](docs/WORKFLOW_REFERENCE.md)
- [Security Controls & Compliance](docs/SECURITY_CONTROLS.md)
- [Testing & Validation Strategy](docs/TESTING.md)
- [Operations Runbook](docs/OPERATIONS_RUNBOOK.md)
- [Deployment Readiness & UAT Checklist](docs/DEPLOYMENT_READINESS.md)
