"""System diagnostics and pre-flight validation module for UBP Bot.

Inspects the runtime environment, directory permissions, browser binaries,
configuration validity, and network connectivity without requiring admin privileges.
Provides actionable diagnostics for restricted enterprise Windows workstations.
"""

import os
import platform
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.ubp_bot.core.config import get_application_root, load_config


def check_python_environment() -> Dict[str, Any]:
    """Inspect the Python execution environment."""
    is_frozen = getattr(sys, "frozen", False)
    is_64bit = sys.maxsize > 2**32
    version_str = platform.python_version()
    major, minor, _ = [int(v) for v in version_str.split(".")[:3]]
    is_compatible = (major == 3 and minor >= 9) or is_frozen

    return {
        "is_frozen": is_frozen,
        "is_64bit": is_64bit,
        "python_version": version_str,
        "executable_path": str(sys.executable),
        "status": "PASS" if is_compatible and is_64bit else "WARN",
        "detail": (
            "Standalone Portable Executable"
            if is_frozen
            else f"Python {version_str} ({'64-bit' if is_64bit else '32-bit'})"
        ),
    }


def check_dependencies() -> Dict[str, Any]:
    """Verify presence of all mandatory third-party libraries."""
    required = ["playwright", "pandas", "openpyxl", "tkinter"]
    missing: List[str] = []
    versions: Dict[str, str] = {}

    for pkg in required:
        try:
            if pkg == "tkinter":
                import tkinter

                versions["tkinter"] = str(tkinter.TkVersion)
            elif pkg == "playwright":
                import playwright

                versions["playwright"] = getattr(playwright, "__version__", "installed")
            elif pkg == "pandas":
                import pandas

                versions["pandas"] = pandas.__version__
            elif pkg == "openpyxl":
                import openpyxl

                versions["openpyxl"] = openpyxl.__version__
        except ImportError:
            missing.append(pkg)

    return {
        "status": "FAIL" if missing else "PASS",
        "missing": missing,
        "versions": versions,
        "detail": f"All {len(required)} core libraries present" if not missing else f"Missing: {missing}",
    }


def check_directory_permissions() -> Dict[str, Any]:
    """Test read/write permissions for all operational folders."""
    app_root = get_application_root()
    folders = ["input", "output", "logs", "checkpoints", "processing", "completed", "failed"]
    failures: List[str] = []

    for name in folders:
        dir_p = app_root / name
        try:
            dir_p.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=dir_p, prefix=".test_perm_", delete=True) as tf:
                tf.write(b"ok")
        except Exception as exc:
            failures.append(f"{name} ({exc})")

    return {
        "status": "FAIL" if failures else "PASS",
        "app_root": str(app_root),
        "failures": failures,
        "detail": "Application folders writable" if not failures else f"Write errors: {failures}",
    }


def find_system_browsers() -> Dict[str, Optional[str]]:
    """Locate pre-installed system browsers available on Windows."""
    paths: Dict[str, Optional[str]] = {"msedge": None, "chrome": None}

    candidates_edge = [
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
        / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    for p in candidates_edge:
        if p.exists():
            paths["msedge"] = str(p)
            break

    candidates_chrome = [
        Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for p in candidates_chrome:
        if p.exists():
            paths["chrome"] = str(p)
            break

    return paths


def check_browser_runtime(config: Dict[str, Any]) -> Dict[str, Any]:
    """Inspect Playwright browser runtime and alternative execution channels."""
    app_root = get_application_root()
    browser_cfg = config.get("browser", {})
    cdp_url = browser_cfg.get("cdp_url")
    channel = browser_cfg.get("channel")

    system_browsers = find_system_browsers()
    local_browsers_dir = app_root / "browsers"
    has_local_chromium = False
    chromium_path: Optional[str] = None

    if local_browsers_dir.exists():
        for ch_dir in local_browsers_dir.glob("chromium-*"):
            exe = ch_dir / "chrome-win" / "chrome.exe"
            if exe.exists():
                has_local_chromium = True
                chromium_path = str(exe)
                break

    # Fallback check ms-playwright in LOCALAPPDATA
    if not has_local_chromium:
        local_app = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
        if local_app.exists():
            for ch_dir in local_app.glob("chromium-*"):
                exe = ch_dir / "chrome-win" / "chrome.exe"
                if exe.exists():
                    has_local_chromium = True
                    chromium_path = str(exe)
                    break

    status = "PASS"
    remedy: Optional[str] = None

    if cdp_url:
        detail = f"CDP Remote Debugging Mode -> {cdp_url}"
    elif channel:
        sys_path = system_browsers.get(channel)
        if sys_path:
            detail = f"Configured System Browser: '{channel}' -> {sys_path}"
        else:
            status = "WARN"
            detail = f"Configured channel '{channel}' not found in default paths"
            remedy = "Verify browser is installed or switch channel to 'msedge' or 'chrome'."
    elif has_local_chromium:
        detail = f"Portable Chromium available -> {chromium_path}"
    elif system_browsers["msedge"]:
        status = "WARN"
        detail = f"Bundled Chromium missing, but system Edge detected at {system_browsers['msedge']}"
        remedy = "Set 'channel': 'msedge' in config.json to run without bundled Chromium."
    elif system_browsers["chrome"]:
        status = "WARN"
        detail = f"Bundled Chromium missing, but system Chrome detected at {system_browsers['chrome']}"
        remedy = "Set 'channel': 'chrome' in config.json to run without bundled Chromium."
    else:
        status = "FAIL"
        detail = "No usable browser runtime found (portable or system-installed)"
        remedy = "Install Chromium into browsers/ or enable CDP mode in config.json."

    return {
        "status": status,
        "channel": channel,
        "cdp_url": cdp_url,
        "has_local_chromium": has_local_chromium,
        "chromium_path": chromium_path,
        "system_browsers": system_browsers,
        "detail": detail,
        "remedy": remedy,
    }


def check_portal_connectivity(config: Dict[str, Any]) -> Dict[str, Any]:
    """Check connectivity to the configured OTC Portal URL."""
    portal_url = config.get("portal", {}).get("login_url", "http://localhost:5173/")
    reachable = False
    status_code: Optional[int] = None
    note: Optional[str] = None

    try:
        parsed = urllib.parse.urlparse(portal_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Disallowed URL scheme: {parsed.scheme}")
        req = urllib.request.urlopen(portal_url, timeout=3)  # nosec B310
        status_code = req.status
        reachable = True
        detail = f"Reachable (HTTP {status_code}) -> {portal_url}"
    except Exception as exc:
        detail = f"Unreachable -> {portal_url} ({exc})"
        note = "If using local test portal, run with --mock or start your web portal service."

    return {
        "status": "PASS" if reachable else "WARN",
        "portal_url": portal_url,
        "reachable": reachable,
        "http_status": status_code,
        "detail": detail,
        "note": note,
    }


def run_full_system_diagnostics(
    config_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute all pre-flight diagnostic tests and return a comprehensive summary.

    Args:
        config_path: Optional path to config.json.

    Returns:
        Dict[str, Any]: Structured diagnostics result dictionary.
    """
    try:
        config = load_config(config_path)
    except Exception:
        config = {}

    env_check = check_python_environment()
    dep_check = check_dependencies()
    perm_check = check_directory_permissions()
    browser_check = check_browser_runtime(config)
    net_check = check_portal_connectivity(config)

    statuses = [
        env_check["status"],
        dep_check["status"],
        perm_check["status"],
        browser_check["status"],
    ]

    overall_status = "PASS"
    if "FAIL" in statuses:
        overall_status = "FAIL"
    elif "WARN" in statuses:
        overall_status = "WARN"

    return {
        "overall_status": overall_status,
        "environment": env_check,
        "dependencies": dep_check,
        "permissions": perm_check,
        "browser": browser_check,
        "network": net_check,
    }


def format_diagnostics_report(diagnostics: Dict[str, Any]) -> str:
    """Format structured diagnostics data into a human-readable text report."""
    overall = diagnostics.get("overall_status", "UNKNOWN")
    env = diagnostics.get("environment", {})
    deps = diagnostics.get("dependencies", {})
    perms = diagnostics.get("permissions", {})
    br = diagnostics.get("browser", {})
    net = diagnostics.get("network", {})

    status_icon = "[OK]" if overall == "PASS" else ("[WARN]" if overall == "WARN" else "[FAIL]")

    lines = [
        "============================================================",
        f"  UBP Bot Portable Pre-flight Diagnostics {status_icon}",
        "============================================================",
        f"Application Root: {perms.get('app_root', 'N/A')}",
        "",
        f"[1] Runtime Environment: [{env.get('status', 'N/A')}]",
        f"    {env.get('detail', '')}",
        f"    Executable: {env.get('executable_path', '')}",
        "",
        f"[2] Dependencies: [{deps.get('status', 'N/A')}]",
        f"    {deps.get('detail', '')}",
        "",
        f"[3] Permissions: [{perms.get('status', 'N/A')}]",
        f"    {perms.get('detail', '')}",
        "",
        f"[4] Browser Runtime: [{br.get('status', 'N/A')}]",
        f"    {br.get('detail', '')}",
    ]
    if br.get("remedy"):
        lines.append(f"    Remedy: {br.get('remedy')}")

    lines.extend([
        "",
        f"[5] Portal Connectivity: [{net.get('status', 'N/A')}]",
        f"    {net.get('detail', '')}",
    ])
    if net.get("note"):
        lines.append(f"    Note: {net.get('note')}")

    lines.append("============================================================")
    return "\n".join(lines)
