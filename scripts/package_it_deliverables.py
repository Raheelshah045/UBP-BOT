"""IT Deployment Packaging Script for UBP Bot Phase 1.

Generates:
1. UBP-Bot-Phase1-Source.zip (Complete sanitized source package for IT review)
2. UBP-Bot-Phase1-Portable.zip (Validated zero-admin portable package with offline Chromium)
3. SHA-256 Integrity Hashes manifest
"""

import hashlib
import os
import sys
import zipfile
from pathlib import Path
from typing import List, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DEPLOYMENT_DIR = PROJECT_ROOT / "deployment"
PACKAGING_DIR = DEPLOYMENT_DIR / "packaging"

EXCLUDED_DIR_NAMES: Set[str] = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    "browser_profile",
    "browser_profile_gnb",
}

EXCLUDED_FILE_PATTERNS: List[str] = [
    ".env",
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.tmp",
    "*.db",
    "*.db-wal",
    "*.db-shm",
    "screenshot_test.png",
]


def calculate_sha256(file_path: Path) -> str:
    """Calculate cryptographic SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def should_exclude_path(rel_path: Path) -> bool:
    """Check if relative path matches any exclusion criteria."""
    parts = rel_path.parts
    for p in parts:
        if p in EXCLUDED_DIR_NAMES:
            return True
        if "browser_profile" in p:
            return True

    name = rel_path.name
    if name == ".env":
        return True
    if name.endswith(".pyc") or name.endswith(".pyo"):
        return True
    if name.endswith(".log") and "logs" in parts:
        return True
    if name.endswith(".db") or name.endswith(".db-wal") or name.endswith(".db-shm"):
        return True
    if name.startswith(".perm_probe_"):
        return True

    return False


def build_source_zip() -> Path:
    """Create clean Source ZIP archive for IT review."""
    PACKAGING_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = PACKAGING_DIR / "UBP-Bot-Phase1-Source.zip"
    if zip_path.exists():
        zip_path.unlink()

    print(f"[*] Packaging Clean Source Archive into: {zip_path.name}...")
    file_count = 0

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(PROJECT_ROOT):
            rel_dir = Path(root).relative_to(PROJECT_ROOT)

            # Prune excluded directories
            dirs[:] = [d for d in dirs if not should_exclude_path(rel_dir / d)]

            for file_name in files:
                file_rel = rel_dir / file_name
                if should_exclude_path(file_rel):
                    continue

                abs_file = PROJECT_ROOT / file_rel
                arc_name = f"UBP-BOT/{file_rel.as_posix()}"
                zf.write(abs_file, arc_name)
                file_count += 1

    print(f"[✓] Source ZIP created successfully with {file_count} files.")
    return zip_path


def build_portable_zip() -> Path:
    """Run PyInstaller build and create portable package archive."""
    from scripts.build_portable_package import build_portable_distribution

    print("[*] Initiating Portable Executable Compilation and Assembly...")
    portable_folder = build_portable_distribution()

    zip_path = PACKAGING_DIR / "UBP-Bot-Phase1-Portable.zip"
    if zip_path.exists():
        zip_path.unlink()

    print(f"[*] Compressing Portable Package into: {zip_path.name}...")
    file_count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(portable_folder):
            rel_dir = Path(root).relative_to(portable_folder)
            for f in files:
                abs_f = Path(root) / f
                arc_name = f"UBP-Bot-Portable/{ (rel_dir / f).as_posix() }"
                zf.write(abs_f, arc_name)
                file_count += 1

    print(f"[✓] Portable ZIP created successfully with {file_count} bundled components.")
    return zip_path


def main():
    print("===============================================================================")
    print("  UBP Bot — Enterprise IT Deployment Packaging Suite")
    print("===============================================================================")

    # 1. Source Package
    src_zip = build_source_zip()
    src_hash = calculate_sha256(src_zip)

    # 2. Portable Package
    portable_zip = build_portable_zip()
    port_hash = calculate_sha256(portable_zip)

    # 3. Generate SHA-256 Manifest
    manifest_path = PACKAGING_DIR / "SHA256SUMS.txt"
    manifest_content = (
        f"{src_hash} *{src_zip.name}\n"
        f"{port_hash} *{portable_zip.name}\n"
    )
    manifest_path.write_text(manifest_content, encoding="utf-8")

    print("\n" + "=" * 79)
    print("  PACKAGE INTEGRITY MANIFEST (SHA-256)")
    print("=" * 79)
    print(f"  Source ZIP:   {src_hash}  {src_zip.name} ({round(src_zip.stat().st_size / 1024 / 1024, 2)} MB)")
    print(f"  Portable ZIP: {port_hash}  {portable_zip.name} ({round(portable_zip.stat().st_size / 1024 / 1024, 2)} MB)")
    print("=" * 79)
    print(f"[✓] Manifest saved to: {manifest_path}")


if __name__ == "__main__":
    main()
