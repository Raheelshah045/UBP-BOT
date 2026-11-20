# Testing & Validation Strategy — UBP Bot Phase 1

This document outlines the testing architecture, validation methodology, and verification commands for UBP Bot.

---

## 1. Test Suite Organization

The test suite is structured into dedicated categories under `tests/`:

```text
tests/
│
├── unit/
│   ├── test_config_dynamic_directories.py  # Path validation, permission probes, persistence
│   ├── test_secret_manager.py              # Credential isolation and serialization scrubbing
│   ├── test_log_sanitizer.py               # PII, CNIC, card, and password masking
│   ├── test_otc_client_unit.py             # Strict 95/98 exclusion and bank matching
│   └── test_excel_reporter_unit.py         # Formula injection defense and atomic backups
│
├── integration/
│   ├── test_dual_system_pipeline.py        # Cross-system data isolation and report generation
│   ├── test_end_to_end_mock.py             # Complete browser automation against mock portal
│   ├── test_gnb_integration.py             # Dedicated GNB worker and table scraping
│   └── test_cross_system_isolation.py      # Concurrency and profile separation verification
│
├── regression/
│   ├── test_phase1_regression_suite.py     # Code 95/98 exclusion matrix & file hash deduplication
│   ├── test_controlled_remediation.py      # Session recovery and stability under network delays
│   └── test_final_remediation.py           # Checkpoint recovery and row-level resumption
│
└── fixtures/
    ├── sample_input.xlsx                   # Standard OTC input format fixture
    └── FORMAT_FOR_OTC.xlsx                 # Canonical reference spreadsheet format
```

---

## 2. Test Execution Commands

### Run Full Test Suite (104 Tests)
```powershell
pytest
```

### Run Unit Tests Only
```powershell
pytest tests/unit
```

### Run Integration Tests Only
```powershell
pytest tests/integration
```

### Run Regression Tests Only
```powershell
pytest tests/regression
```

### Run with Verbose Test Names and Timing
```powershell
pytest -v --durations=10
```

---

## 3. Performance Profiling & Benchmarking

The baseline benchmark script (`scripts/benchmark_performance.py`) measures timings across 4 execution scenarios against a local portal fixture:
```powershell
python scripts/benchmark_performance.py
```

### Measured Baseline Metrics
- **Benchmark 1 (OTC 20-Record Search)**: 4.22 seconds (~0.21s per transaction search).
- **Benchmark 2 (OTC 100-Record Search)**: 17.20 seconds (~0.17s per transaction search).
- **Benchmark 3 (GNB Rejection Extraction)**: 2.12 seconds total pipeline execution.
- **Benchmark 4 (Dual Simultaneous Run)**: 2.61 seconds for concurrent OTC + GNB execution.

---

## 4. Static Code Analysis & Security Scans

### Linting & Formatting Check (Ruff)
```powershell
ruff check .
```

### Security Vulnerability Scan (Bandit)
```powershell
bandit -r src/
```

*Note: Bandit scan checks for insecure subprocess usage, SQL string concatenation, hardcoded passwords, and weak cryptographic hashes.*
