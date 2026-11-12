"""Entry point for the OTC Transaction Monitoring & Rejection Extraction Bot.

Supports running the continuous monitoring desktop GUI, headless folder watcher,
single-file CLI execution, and the local mock portal server.
"""

import argparse
import sys
import time
from pathlib import Path

from src.config import ensure_workspace_directories, load_config
from src.diagnostics import format_diagnostics_report, run_full_system_diagnostics
from src.queue_manager import set_monitoring_state, start_continuous_monitoring_worker
from src.runner import run_batch_automation
from src.ui import launch_gui


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments for the application.

    Returns:
        argparse.Namespace: Parsed command line parameters.
    """
    parser = argparse.ArgumentParser(
        description="OTC Bot — Portable Enterprise Transaction Monitor"
    )
    parser.add_argument(
        "--monitor", action="store_true", help="Run continuous directory monitoring in CLI mode."
    )
    parser.add_argument("--cli", action="store_true", help="Process a single file in CLI mode.")
    parser.add_argument(
        "--input",
        type=str,
        default="sample_input.xlsx",
        help="Path to the input Excel or CSV file for single-file mode.",
    )
    parser.add_argument(
        "--output", type=str, default="output", help="Directory to save resulting Excel reports."
    )
    parser.add_argument(
        "--config", type=str, default="config.json", help="Path to JSON configuration file."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Start the local mock OTC portal web server on port 8080.",
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
    ensure_workspace_directories()

    if args.diagnostics:
        results = run_full_system_diagnostics(Path(args.config) if args.config else None)
        print(format_diagnostics_report(results))
        sys.exit(0 if results["overall_status"] != "FAIL" else 1)

    if args.mock:
        from mock_portal.app import app

        print("Starting Mock OTC Portal at http://127.0.0.1:8080 ...")
        app.run(host="127.0.0.1", port=8080, debug=False)
        return

    config_path = Path(args.config)
    config = load_config(config_path)

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

    elif args.cli:
        input_path = Path(args.input)
        output_dir = Path(args.output)
        print(f"Executing OTC Bot CLI mode for: {input_path}")
        report = run_batch_automation(
            config=config,
            input_file_path=input_path,
            output_dir=output_dir,
            on_message=lambda msg: print(f"[*] {msg}"),
        )
        if report:
            print(f"[SUCCESS] Report generated at: {report}")
            sys.exit(0)
        else:
            print("[FAILURE] Batch automation failed or was aborted.")
            sys.exit(1)
    else:
        print("Launching Desktop User Interface...")
        launch_gui(config_path)


if __name__ == "__main__":
    main()
