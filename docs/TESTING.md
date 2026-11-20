# Testing & Validation Strategy — UBP Bot Phase 1

This document outlines the testing architecture, validation methodology, and verification commands for UBP Bot.

---

## 1. Test Suite Organization

The test suite is split into two layers:

- **New enterprise tests** (`tests/unit/`, `tests/integration/`, `tests/regression/`) target the canonical `src/ubp_bot/` package.
- **Legacy tests** (`tests/test_*.py`) target the original `src/` modules and are preserved unchanged.

### 1.1 New Enterprise Tests (`src/ubp_bot/` — 26 tests)

```text
tests/
├── unit/                                           (21 tests)
│   ├── test_config_dynamic_directories.py          # Path validation, permission probes, persistence (4)
│   ├── test_secret_manager.py                      # Credential isolation and config scrubbing (4)
│   ├── test_log_sanitizer.py                       # PII, CNIC, card, consumer number masking (3)
│   ├── test_otc_client_unit.py                     # Strict 95/98 exclusion and bank matching (6)
│   └── test_excel_reporter_unit.py                 # Formula injection defense and atomic backups (4)
│
├── integration/                                    (2 tests)
│   └── test_dual_system_pipeline.py                # Cross-system data isolation and report generation
│
└── regression/                                     (3 tests)
    └── test_phase1_regression_suite.py             # Code 95/98 exclusion matrix & file hash idempotency
```

### 1.2 Legacy Tests (`src/` modules — 78 tests, all passing, unchanged)

```text
tests/
├── test_canonical_configuration.py    # src.config — config path resolution (4)
├── test_checkpoint.py                 # src.checkpoint — SQLite lifecycle (1)
├── test_classifier.py                 # src.classifier — OTC classification (8)
├── test_controlled_remediation.py     # src.* — broad cross-module remediation (20)
├── test_cross_system_isolation.py     # src.file_detector — system target routing (2)
├── test_diagnostics.py                # src.diagnostics — environment checks (4)
├── test_end_to_end_mock.py            # src.* — mock-portal browser automation (2)
├── test_excel_reporter.py             # src.excel_reporter — report generation (1)
├── test_existing_session_situations.py# src.auth_manager — session detection (3)
├── test_file_detector.py              # src.file_detector — SHA-256, stability (7)
├── test_final_remediation.py          # src.* — pagination, timeouts, checkpoint (10)
├── test_gnb_integration.py            # src.gnb_client — GNB pipeline mock (1)
├── test_input_processor.py            # src.input_processor — parsing (6)
├── test_phase1_dual_systems.py        # src.excel_reporter — dual report generation (3)
├── test_queue_manager.py              # src.queue_manager — FIFO queue (2)
└── test_state_detector.py             # src.state_detector — portal state detection (4)
```

> [!IMPORTANT]
> Legacy tests import from `src.*`. New enterprise tests import from `src.ubp_bot.*`.
> Both layers must pass on every commit to `feature/phase1-enterprise-readiness`.

---

## 2. Test Execution Commands

### Run Full Test Suite (104 Tests — 78 legacy + 26 new)
```powershell
python -m pytest --tb=short -q
```

### Run New Enterprise Tests Only (26 Tests)
```powershell
python -m pytest tests/unit tests/integration tests/regression -q
```

### Run Unit Tests Only (21 Tests)
```powershell
python -m pytest tests/unit -q
```

### Run Integration Tests Only (2 Tests)
```powershell
python -m pytest tests/integration -q
```

### Run Regression Tests Only (3 Tests)
```powershell
python -m pytest tests/regression -q
```

### Run Legacy Tests Only (78 Tests)
```powershell
python -m pytest tests/test_*.py -q
```

### Run with Verbose Test Names and Timing
```powershell
python -m pytest -v --durations=10
```

---

## 3. Performance Profiling & Benchmarking

The baseline benchmark script (`scripts/benchmark_performance.py`) measures timings across 4 execution scenarios against a local mock portal fixture:

```powershell
python scripts/benchmark_performance.py
```

> [!IMPORTANT]
> The benchmark script uses the **mock portal** (Flask server on `http://127.0.0.1:8080`) and synthetic consumer numbers.
> Timings measure browser automation latency against an in-process server — **not live portal latency**.
> Live portal timings will differ substantially due to network round trips, real CAPTCHA flows, and portal server load.
> Establish a live baseline during UAT before using timings for SLA decisions.

### Measured Mock-Portal Baseline Metrics
- **Benchmark 1 (OTC 20-Record Search — mock portal)**: 4.22 seconds (~0.21s per transaction search).
- **Benchmark 2 (OTC 100-Record Search — mock portal)**: 17.20 seconds (~0.17s per transaction search).
- **Benchmark 3 (GNB Rejection Extraction — mock portal)**: 2.12 seconds total pipeline execution.
- **Benchmark 4 (Dual Simultaneous Run — mock portal)**: 2.61 seconds for concurrent OTC + GNB execution.

---

## 4. Static Code Analysis & Security Scans

### Linting & Formatting Check (Ruff — new package)
```powershell
python -m ruff check src/ubp_bot/
```

### Security Vulnerability Scan (Bandit — medium and high only)
```powershell
python -m bandit -r src/ubp_bot/ -ll --quiet
```

*Note: Bandit scan checks for insecure subprocess usage, SQL string concatenation, hardcoded passwords, and weak cryptographic hashes. The legacy `src/` modules are pre-existing and are not subject to new-commit quality gates.*
