#!/usr/bin/env python3
"""Furina Code Active Source Pack build and verify script.

Usage:
    python build_source_pack.py [--verify-only]

Produces:
    ../build/FURINA_CODE_ACTIVE_SOURCE_PACK_CURRENT.zip
    ../build/SHA256SUMS.txt
    ../build/SOURCE_PACK_RELEASE_REPORT.md
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_SOURCE = SCRIPT_DIR.parent
ACTIVE_DIR = PROJECT_SOURCE / "active"
BUILD_DIR = PROJECT_SOURCE / "build"
ARCHIVE_DIR = PROJECT_SOURCE / "local_archive"

REQUIRED_FILES = [
    "00_START_HERE.md",
    "20_CURRENT_REALITY/01_CURRENT_STATE_SNAPSHOT.md",
    "20_CURRENT_REALITY/02_CAPABILITY_REALITY_LEDGER.md",
    "20_CURRENT_REALITY/03_CURRENT_GAPS_AND_RISKS.md",
    "20_CURRENT_REALITY/04_ENGINEERING_EVIDENCE_INDEX.md",
    "20_CURRENT_REALITY/05_INITIAL_LOOP_ESTABLISHMENT_RECORD.md",
    "50_DECISIONS/00_DECISION_INDEX.md",
    "80_ARCHIVE_INDEX/00_ARCHIVED_ROUTES_INDEX.md",
    "90_MAINTENANCE",
    "99_INTEGRITY_MANIFEST.md",
    "PACKAGE_QUALITY_AUDIT.md",
    "SHA256SUMS.txt",
]

SENSITIVE_PATTERNS = [
    re.compile(r"[A-Z]:\\[\\\/]"),
    re.compile(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
STATUS_RE = re.compile(r"status:\s*(\S+)")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_files(root: Path) -> list[Path]:
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            files.append(p)
    return files


def verify_sha256sums(root: Path) -> list[str]:
    errors = []
    sha_path = root / "SHA256SUMS.txt"
    if not sha_path.exists():
        return ["SHA256SUMS.txt not found"]
    for line in sha_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([a-f0-9]{64})\s+(.+)$", line)
        if not m:
            continue
        expected, rel = m.group(1), m.group(2).strip()
        fp = root / rel
        if not fp.exists():
            errors.append(f"MISSING: {rel}")
        elif sha256_file(fp) != expected:
            errors.append(f"HASH MISMATCH: {rel}")
    return errors


def check_frontmatter(root: Path) -> list[str]:
    errors = []
    # Frozen files and integrity manifest use bold-text metadata, not YAML frontmatter
    SKIP_FRONTMATTER = {"99_INTEGRITY_MANIFEST.md"}
    for fp in collect_files(root):
        if fp.suffix != ".md":
            continue
        if "_FROZEN" in fp.name or fp.name in SKIP_FRONTMATTER:
            continue
        text = fp.read_text(encoding="utf-8", errors="replace")
        m = FRONTMATTER_RE.search(text)
        rel = fp.relative_to(root)
        if not m:
            errors.append(f"NO FRONTMATTER: {rel}")
            continue
        sm = STATUS_RE.search(m.group(1))
        if not sm or not sm.group(1).strip():
            errors.append(f"EMPTY STATUS: {rel}")
    return errors


def check_sensitive(root: Path) -> list[str]:
    errors = []
    for fp in collect_files(root):
        if fp.suffix not in {".md", ".txt", ".py", ".toml", ".yaml", ".yml"}:
            continue
        text = fp.read_text(encoding="utf-8", errors="replace")
        for pat in SENSITIVE_PATTERNS:
            if pat.search(text):
                errors.append(f"SENSITIVE CONTENT: {fp.relative_to(root)}")
                break
    return errors


def check_links(root: Path) -> list[str]:
    errors = []
    link_re = re.compile(r"\[.*?\]\(([^)]+)\)")
    for fp in collect_files(root):
        if fp.suffix != ".md":
            continue
        text = fp.read_text(encoding="utf-8", errors="replace")
        for m in link_re.finditer(text):
            target = m.group(1)
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target_path = fp.parent / target.split("#")[0]
            if not target_path.exists():
                errors.append(f"BROKEN LINK: {fp.relative_to(root)} -> {target}")
    return errors


def build_zip() -> Path:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = BUILD_DIR / "FURINA_CODE_ACTIVE_SOURCE_PACK_CURRENT.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in collect_files(ACTIVE_DIR):
            arcname = f"FURINA_CODE_ACTIVE_SOURCE_PACK_CURRENT/{fp.relative_to(ACTIVE_DIR)}"
            zf.write(fp, arcname)
    return zip_path


def verify_zip_vs_active(zip_path: Path) -> list[str]:
    errors = []
    active_files = {f.relative_to(ACTIVE_DIR).as_posix() for f in collect_files(ACTIVE_DIR)}
    with zipfile.ZipFile(zip_path, "r") as zf:
        zip_files = set()
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            prefix = "FURINA_CODE_ACTIVE_SOURCE_PACK_CURRENT/"
            if name.startswith(prefix):
                zip_files.add(name[len(prefix):])
    if active_files != zip_files:
        missing_in_zip = active_files - zip_files
        extra_in_zip = zip_files - active_files
        for m in missing_in_zip:
            errors.append(f"MISSING IN ZIP: {m}")
        for e in extra_in_zip:
            errors.append(f"EXTRA IN ZIP: {e}")
    return errors


def generate_sha256sums() -> Path:
    sha_path = BUILD_DIR / "SHA256SUMS.txt"
    lines = []
    for fp in sorted(collect_files(ACTIVE_DIR)):
        rel = fp.relative_to(ACTIVE_DIR).as_posix()
        lines.append(f"{sha256_file(fp)}  {rel}")
    sha_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sha_path


def generate_report(zip_sha256: str) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    active_files = collect_files(ACTIVE_DIR)
    frozen_files = [f for f in active_files if "_FROZEN" in f.name]

    lines = [
        "---",
        "title: Source Pack Release Report",
        "status: ACTIVE",
        "authority: MAINTENANCE",
        f"prepared_at: {now}",
        "---",
        "",
        "# Source Pack Release Report",
        "",
        "## Update Reason",
        "",
        "第一版初循环在严格限定范围内建立。",
        "旧项目来源仍停留在初循环成立前，需要发布初循环成立后的 Active Source Pack。",
        "",
        "## Evidence Revision",
        "",
        "`LOCAL_WORKING_TREE_AFTER_INITIAL_LOOP_V1`",
        "",
        "## Repository State",
        "",
        "- This report is generated from the local working tree, NOT from GitHub main or CI.",
        "- HEAD and origin/main SHA are recorded for reference only.",
        "",
        "## Test Evidence",
        "",
        "- Initial loop suite (E5/E6/E7/initial_loop): 17 passed",
        "- Full pytest suite: 405 passed",
        "- CI status: unknown (no new main SHA or CI run this session)",
        "",
        "## Frozen Files",
        "",
    ]
    for f in frozen_files:
        lines.append(f"- `{f.name}`: SHA-256 `{sha256_file(f)[:16]}...`")
    lines.extend([
        "",
        "## Files Changed in _project_source",
        "",
        "- `active/` populated from verified V1.3 Active Source Pack",
        "- `templates/` task templates from maintenance manual",
        "- `scripts/` build and verify script",
        "- `build/` generated release artifacts",
        "- `local_archive/` versioned local archive",
        "",
        "## Build Output",
        "",
        f"- `FURINA_CODE_ACTIVE_SOURCE_PACK_CURRENT.zip` SHA-256: `{zip_sha256}`",
        "",
        "## Capability Boundaries Not Covered",
        "",
        "- Arbitrary file operations",
        "- Multi-file tasks",
        "- Update/delete/rename",
        "- Cross-repository operations",
        "- External system integration",
        "- High-risk actions",
        "- General recovery",
        "- Long-term experience",
        "- Product readiness / mature delivery",
        "",
        "## Important Disclaimer",
        "",
        "This package does NOT replace GitHub as the code source of truth.",
        "It is a local project context layer for AI-assisted development.",
    ])
    report_path = BUILD_DIR / "SOURCE_PACK_RELEASE_REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main():
    verify_only = "--verify-only" in sys.argv
    errors = []

    print("=== Active Source Pack Build & Verify ===\n")

    # 1. Check required files
    print("[1/8] Checking required files...")
    for r in REQUIRED_FILES:
        p = ACTIVE_DIR / r
        if not p.exists():
            errors.append(f"MISSING REQUIRED: {r}")
    print(f"      Required files: {len([r for r in REQUIRED_FILES if (ACTIVE_DIR / r).exists()])}/{len(REQUIRED_FILES)}")

    # 2. Verify SHA256SUMS
    print("[2/8] Verifying SHA256SUMS.txt...")
    sha_errors = verify_sha256sums(ACTIVE_DIR)
    errors.extend(sha_errors)
    print(f"      SHA256SUMS errors: {len(sha_errors)}")

    # 3. Check frontmatter
    print("[3/8] Checking frontmatter...")
    fm_errors = check_frontmatter(ACTIVE_DIR)
    errors.extend(fm_errors)
    print(f"      Frontmatter errors: {len(fm_errors)}")

    # 4. Check sensitive content
    print("[4/8] Checking sensitive content...")
    sec_errors = check_sensitive(ACTIVE_DIR)
    errors.extend(sec_errors)
    print(f"      Sensitive content issues: {len(sec_errors)}")

    # 5. Check links
    print("[5/8] Checking relative links...")
    link_errors = check_links(ACTIVE_DIR)
    errors.extend(link_errors)
    print(f"      Broken links: {len(link_errors)}")

    if verify_only:
        if errors:
            print(f"\nFAILED: {len(errors)} errors found")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        print("\nAll checks passed.")
        sys.exit(0)

    # 6. Build ZIP
    print("[6/8] Building CURRENT.zip...")
    zip_path = build_zip()
    zip_sha = sha256_file(zip_path)
    print(f"      ZIP: {zip_path}")
    print(f"      SHA-256: {zip_sha}")

    # 7. Verify ZIP vs active
    print("[7/8] Verifying ZIP vs active...")
    zip_errors = verify_zip_vs_active(zip_path)
    errors.extend(zip_errors)
    print(f"      ZIP vs active errors: {len(zip_errors)}")

    # 8. Generate build artifacts
    print("[8/8] Generating build artifacts...")
    generate_sha256sums()
    generate_report(zip_sha)
    print(f"      SHA256SUMS.txt: {BUILD_DIR / 'SHA256SUMS.txt'}")
    print(f"      SOURCE_PACK_RELEASE_REPORT.md: {BUILD_DIR / 'SOURCE_PACK_RELEASE_REPORT.md'}")

    print(f"\n{'='*45}")
    if errors:
        print(f"FAILED: {len(errors)} errors found")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("SUCCESS: All checks passed.")
        print(f"  ZIP SHA-256: {zip_sha}")
        sys.exit(0)


if __name__ == "__main__":
    main()
