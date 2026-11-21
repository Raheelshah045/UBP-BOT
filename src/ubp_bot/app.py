"""Application orchestrator and entry point for UBP Bot Phase 1.

Supports:
- Desktop Enterprise GUI with dynamic folder configuration
- Continuous directory monitoring CLI
- Single-file CLI processing
- Dual-system (OTC and GNB) simultaneous or isolated extraction
- Local mock portal hosting
- Pre-flight system and browser diagnostics
"""

import argparse
import sys
import time
from pathlib import Path

from src.ubp_bot.core.config import (
    ensure_workspace_directories,
    get_application_root,
    initialize_environment,
    load_config,
    resolve_app_path,
)
from src.ubp_bot.core.pipeline import run_batch_automation
from src.ubp_bot.core.queue_manager import (
    set_monitoring_state,
    start_continuous_monitoring_worker,
)
from src.ubp_bot.portals.gnb_client import run_gnb_extraction_pipeline
from src.ubp_bot.services.diagnostics import (
    format_diagnostics_report,
    run_full_system_diagnostics,
)
from src.ubp_bot.services.excel_reporter import generate_gnb_rejected_report
from src.ubp_bot.ui.dashboard import launch_dashboard

initialize_environment()


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments for the application."""
    parser = argparse.ArgumentParser(
        description="UBP Bot — Phase 1 Enterprise Dual-System Operations"
    )
    parser.add_argument(
        "--monitor", action="store_true", help="Run continuous directory monitoring in CLI mode."
    )
    parser.add_argument("--cli", action="store_true", help="Process a single file in CLI mode.")
    parser.add_argument(
        "--input",
        type=str,
        default="tests/fixtures/sample_input.xlsx",
        help="Path to the input Excel or CSV file for single-file mode.",
    )
    parser.add_argument(
        "--output", type=str, default="output", help="Directory to save resulting Excel reports."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/config.json",
        help="Path to JSON configuration file (default: config/config.json).",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Start the local mock OTC portal web server on port 8080.",
    )
    parser.add_argument(
        "--gnb",
        action="store_true",
        help="Extract rejected transactions from the GNB system.",
    )
    parser.add_argument(
        "--all-systems",
        action="store_true",
        help="Run Phase 1 extraction across both OTC and GNB systems.",
    )
    parser.add_argument(
        "--diagnostics",
        "--check",
        action="store_true",
        dest="diagnostics",
        help="Run pre-flight environment and browser runtime diagnostics.",
    )
    return parser.parse_args()


def main() -> None:
    """Application main entry point."""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    args = parse_arguments()
    config_path = Path(args.config)
    if not config_path.exists():
        if config_path.name == "config.json" and (get_application_root() / "config" / "config.json").exists():
            config_path = get_application_root() / "config" / "config.json"

    # Diagnostics Mode
    if args.diagnostics:
        diag_path = config_path if config_path.exists() else None
        results = run_full_system_diagnostics(diag_path)
        print(format_diagnostics_report(results))
        sys.exit(0 if results["overall_status"] != "FAIL" else 1)

    # Local Mock Server Mode
    if args.mock:
        from mock_portal.app import app

        print("Starting Mock OTC Portal at http://127.0.0.1:8080 ...")
        app.run(host="127.0.0.1", port=8080, debug=False)
        return

    config = load_config(config_path)
    ensure_workspace_directories(config=config)

    # Continuous Monitor CLI Mode
    if args.monitor:
        print("[*] Starting continuous directory monitoring mode. Press Ctrl+C to terminate.")
        try:
            start_continuous_monitoring_worker(
                config=config,
                on_message=lambda msg: print(f"[*] {msg}"),
                on_queue_update=lambda count, cur: print(
                    f"[STATUS] Queue: {count} pending | Active: {cur}"
                ),
            )
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[!] Stopping directory monitor.")
            set_monitoring_state(False)
            sys.exit(0)

    # GNB System CLI Mode
    elif args.gnb:
        output_dir = resolve_app_path(args.output)
        input_path = resolve_app_path(args.input) if args.input and Path(args.input).exists() else None
        print("[*] Executing GNB System extraction...")
        gnb_txs = run_gnb_extraction_pipeline(
            config,
            input_file_path=input_path,
            on_message=lambda msg: print(f"[*] {msg}"),
        )
        report = generate_gnb_rejected_report(output_dir, gnb_txs)
        print(f"[SUCCESS] GNB Report generated at: {report}")
        sys.exit(0)

    # Dual System CLI Mode
    elif args.all_systems:
        output_dir = resolve_app_path(args.output)
        input_path = resolve_app_path(args.input)
        print("[*] Executing Phase 1 Extraction — System A: OTC & System B: GNB")

        # 1. OTC System
        print("\n--- System A: OTC Extraction ---")
        otc_rep = run_batch_automation(
            config=config,
            input_file_path=input_path,
            output_dir=output_dir,
            on_message=lambda msg: print(f"[*] {msg}"),
        )

        # 2. GNB System
        print("\n--- System B: GNB Extraction ---")
        gnb_in = input_path if "gnb" in input_path.name.lower() else None
        gnb_txs = run_gnb_extraction_pipeline(
            config,
            input_file_path=gnb_in,
            on_message=lambda msg: print(f"[*] {msg}"),
        )
        gnb_rep = generate_gnb_rejected_report(output_dir, gnb_txs)

        print("\n============================================================")
        print("  Phase 1 Extraction Complete!")
        print(f"  1. OTC Report: {otc_rep}")
        print(f"  2. GNB Report: {gnb_rep}")
        print("============================================================")
        sys.exit(0)

    # OTC Single File CLI Mode
    elif args.cli:
        input_path = resolve_app_path(args.input)
        output_dir = resolve_app_path(args.output)
        print(f"Executing OTC Bot CLI mode for: {input_path}")
        report = run_batch_automation(
            config=config,
            input_file_path=input_path,
            output_dir=output_dir,
            on_message=lambda msg: print(f"[*] {msg}"),
        )
        if report and report.exists():
            print(f"[SUCCESS] Report generated at: {report}")
            sys.exit(0)
        else:
            print("[FAILURE] Batch automation failed or was aborted.")
            sys.exit(1)

    # Desktop Dashboard GUI Mode
    else:
        print("Launching Enterprise Desktop Operations Dashboard...")
        launch_dashboard(config_path)


if __name__ == "__main__":
    main()
