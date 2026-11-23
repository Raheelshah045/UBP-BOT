# Module Reference — UBP Bot

This document provides a comprehensive technical reference for all source modules within `src/ubp_bot/`.

---

## 1. Core Package (`src/ubp_bot/core/`)

### `config.py`
- **Purpose**: Centralized path resolution, runtime environment initialization, and dynamic directory persistence.
- **Key Functions**:
  - `get_application_root() -> Path`: Resolves application root in both dev mode and PyInstaller frozen executables.
  - `validate_directory_permissions(path: Path | str) -> Tuple[bool, str]`: Tests existence, read directory listing, and atomic write/unlink permission probe.
  - `has_valid_directory_configuration(config: Dict) -> Tuple[bool, str]`: Checks if input/output directories are configured and valid without silent fallback.
  - `update_configured_directories(input_dir, output_dir, config_path) -> Dict`: Persists validated directory paths to `config.json`.
  - `load_config(config_path: Optional[Path]) -> Dict`: Loads JSON config and merges environment variable overrides.
  - `save_config(config_data: Dict, config_path: Optional[Path]) -> None`: Serializes configuration after recursively scrubbing all secrets.
- **Dependencies**: `json`, `os`, `sys`, `pathlib`, `tempfile`, `secret_manager`.
- **Callers**: `app.py`, `dashboard.py`, `dialogs.py`, `pipeline.py`, `queue_manager.py`.

### `pipeline.py`
- **Purpose**: Batch execution coordinator and SQLite checkpoint engine.
- **Key Functions**:
  - `compute_batch_id(input_file_path: Path) -> str`: Computes deterministic 12-character hex ID from file path and modification time.
  - `init_checkpoint_db(db_path: Path) -> None`: Prepares tables `file_history`, `batches`, `processed_rows`, and `raw_transactions` in WAL mode.
  - `register_batch(...)`, `record_row_result(...)`, `save_transactions(...)`: Atomic transaction recording.
  - `get_processed_row_numbers(db_path, batch_id) -> List[int]`: Returns set of already completed rows for resume capability.
  - `run_batch_automation(config, input_file_path, output_dir, ...) -> Optional[Path]`: Executes end-to-end OTC batch flow with progress, pause, and cancellation checks.
- **Dependencies**: `sqlite3`, `hashlib`, `time`, `otc_client`, `excel_reporter`, `browser_manager`, `log_sanitizer`.
- **Callers**: `app.py`, `queue_manager.py`, `dashboard.py`.

### `file_detector.py`
- **Purpose**: File ingestion, structural validation, stability detection, and archival.
- **Key Functions**:
  - `is_temporary_file(file_path: Path) -> bool`: Filters out `~$*`, `.~*`, and `*.tmp` files.
  - `is_file_locked_or_changing(file_path: Path) -> bool`: Verifies file write completion via multi-check stability and test open.
  - `compute_file_sha256(file_path: Path) -> str`: Generates SHA-256 hash for deduplication.
  - `validate_file_structure(file_path: Path) -> Dict`: Validates mandatory headers (`Consumer Number`, `Date` for OTC; `Transaction ID` for GNB).
  - `identify_system_target(file_path: Path) -> str`: Routes file to `'otc'` or `'gnb'` based on filename keywords.
  - `move_file_safely(source_file, target_dir) -> Path`: Moves file with retry mechanism and collision avoidance (`_YYYYMMDD_HHMMSS`).
- **Dependencies**: `hashlib`, `shutil`, `pandas`, `openpyxl`.
- **Callers**: `queue_manager.py`, `pipeline.py`.

### `queue_manager.py`
- **Purpose**: Continuous directory monitoring and sequential queue processing.
- **Key Functions**:
  - `set_monitoring_state(active: bool) -> None`: Activates or deactivates the directory monitoring loop.
  - `enqueue_file_if_new(file_path: Path) -> bool`: Thread-safely enqueues unique candidate files.
  - `process_queue_item(file_path, config, ...) -> bool`: Moves file to `processing/`, executes automation, and archives to `completed/` or `failed/`.
  - `start_continuous_monitoring_worker(...) -> None`: Continuous polling thread worker.
- **Dependencies**: `threading`, `time`, `file_detector`, `pipeline`, `gnb_client`.
- **Callers**: `app.py`, `dashboard.py`.

---

## 2. Portals Package (`src/ubp_bot/portals/`)

### `otc_client.py`
- **Purpose**: OTC BPS portal browser automation and rejection classification.
- **Key Functions**:
  - `classify_transaction(status: str, response_code: str, rules_config: Dict) -> Dict`:
    - Strict Exclusion: Codes `95` and `98` -> `is_qualifying_rejection = False`, `classification = 'Excluded Rejection'`.
    - Approved: Code `00` or status `APPROVED` -> `is_qualifying_rejection = False`.
    - Rejected: Any other rejected status/code (e.g. `51`, `05`) -> `is_qualifying_rejection = True`.
  - `ensure_portal_authenticated(...) -> bool`: Guides manual login, detects 2FA OTP completion, and transitions to search form.
  - `navigate_to_check_bill_status(page, selectors, direct_url) -> bool`: In-page dynamic click navigation without full page reload.
  - `execute_transaction_search(...) -> bool`: Selects bank, enters consumer number and date, and submits query.
  - `extract_all_transactions(page, selectors, max_pages) -> List[Dict]`: Extracts tabular data across pagination.
- **Dependencies**: `playwright.sync_api`, `time`.
- **Callers**: `pipeline.py`.

### `gnb_client.py`
- **Purpose**: GNB Core Banking portal automation and rejection extraction.
- **Key Functions**:
  - `run_gnb_extraction_pipeline(config, input_file_path, ...) -> List[Dict]`: Full GNB workflow in a dedicated worker thread.
  - `login_gnb_portal(...) -> bool`: Automated authentication via configured credentials or manual fallback.
  - `extract_gnb_transactions(...) -> List[Dict]`: Scrapes failed and rejected core banking transactions.
  - `release_stale_profile_lock(profile_dir: Path) -> None`: Terminates orphaned Chrome processes and unlinks stale locks (`SingletonLock`).
- **Dependencies**: `playwright.sync_api`, `threading`, `psutil`.
- **Callers**: `app.py`, `queue_manager.py`, `dashboard.py`.

---

## 3. Services Package (`src/ubp_bot/services/`)

### `browser_manager.py`
- **Purpose**: Browser runtime management and profile isolation.
- **Key Functions**:
  - `configure_portable_browsers_path(browser_config: Dict) -> Optional[Path]`: Sets `PLAYWRIGHT_BROWSERS_PATH` to portable bundled directory.
  - `verify_browser_runtime_available(browser_config: Dict) -> Tuple[bool, str]`: Pre-flight check for Chromium / system browser presence.
  - `launch_persistent_browser_session(browser_config, initial_url, system_name) -> Tuple[...]`: Launches isolated session for `'otc'` or `'gnb'`.
  - `close_browser_session() -> None`: Cleans up active OTC browser context.
  - `close_all_browser_sessions() -> None`: Cleans up all browser instances across systems.
- **Dependencies**: `playwright.sync_api`, `os`, `pathlib`.
- **Callers**: `pipeline.py`, `gnb_client.py`, `dashboard.py`.

### `excel_reporter.py`
- **Purpose**: Production Excel report generation with formula injection security.
- **Key Functions**:
  - `sanitize_cell_value(val: Any) -> Any`: Escapes dangerous characters (`=`, `+`, `-`, `@`, `\t`, `\r`) with a leading `'`.
  - `save_workbook_safely(workbook, target_path) -> Path`: Atomic write to `.tmp_*` followed by rename and creation of previous-run backup (`*_prev.xlsx`).
  - `generate_otc_rejected_report(output_dir, all_transactions) -> Path`: Generates `OTC_Rejected_Transactions.xlsx` containing only qualifying rejections.
  - `generate_gnb_rejected_report(output_dir, all_transactions) -> Path`: Generates `GNB_Rejected_Transactions.xlsx`.
- **Dependencies**: `openpyxl`, `shutil`, `pathlib`.
- **Callers**: `pipeline.py`, `queue_manager.py`, `dashboard.py`.

### `diagnostics.py`
- **Purpose**: System health inspection and pre-flight diagnostics.
- **Key Functions**:
  - `run_full_system_diagnostics(config_path) -> Dict`: Evaluates Python version, third-party libraries, browser binaries, write permissions, and portal reachability.
  - `format_diagnostics_report(results: Dict) -> str`: Formats results into a clean ASCII diagnostic table.
- **Dependencies**: `platform`, `sys`, `urllib.request`.
- **Callers**: `app.py`, `dialogs.py`.

---

## 4. Security Package (`src/ubp_bot/security/`)

### `secret_manager.py`
- **Purpose**: Secure credential storage and configuration sanitization.
- **Key Functions**:
  - `load_env_file(env_file_path: Path) -> Dict[str, str]`: Loads `.env` file without echoing values.
  - `get_secret(key, default) -> Optional[str]`: Reads credential from environment.
  - `sanitize_config_for_storage(data: Any) -> Any`: Recursively scrubs passwords and tokens before persisting config.
- **Dependencies**: `os`, `re`, `pathlib`.
- **Callers**: `config.py`.

### `log_sanitizer.py`
- **Purpose**: PII and sensitive token redaction.
- **Key Functions**:
  - `mask_sensitive_text(text: str) -> str`: Redacts passwords, API keys, Bearer tokens, CNICs (`42101-*******-1`), and payment cards (`1234-****-****-5432`).
  - `mask_consumer_number(consumer_number: str) -> str`: Masks utility consumer accounts (`1234******8901`).
  - `get_logger(name, logs_dir) -> logging.Logger`: Configured logger with sanitized stream and daily rolling file handler.
- **Dependencies**: `logging`, `re`, `pathlib`.
- **Callers**: All modules.

---

## 5. UI Package (`src/ubp_bot/ui/`)

### `dashboard.py`
- **Purpose**: Enterprise light-theme Tkinter operations dashboard.
- **Key Functions**:
  - `create_desktop_dashboard(config_path) -> tk.Tk`: Builds the full GUI interface.
  - `launch_dashboard(config_path) -> None`: Runs the main event loop.
- **Dependencies**: `tkinter`, `ttk`, `threading`, `core`, `portals`, `services`.
- **Callers**: `app.py`.

### `dialogs.py`
- **Purpose**: User dialogs for directory selection and diagnostics.
- **Key Functions**:
  - `browse_and_validate_directory(...) -> Tuple[bool, Optional[Path]]`: Folder picker with permission check and cancel preservation.
  - `prompt_mandatory_directory_setup(...) -> bool`: Modal prompt requiring valid directories on first launch.
  - `show_diagnostics_dialog(parent, config_path) -> None`: Displays diagnostic report.
- **Dependencies**: `tkinter`, `filedialog`, `messagebox`.
- **Callers**: `dashboard.py`.
