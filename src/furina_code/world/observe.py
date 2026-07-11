"""Furina Code world — project metadata observation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 1_000_000  # 1 MB


@dataclass(frozen=True)
class SafeFileObservation:
    """Structured result for safe file reads — replaces None-as-failure."""
    status: str  # present | missing | symlink_rejected | escape_rejected | git_internal_rejected | oversized | decode_failed | parse_failed
    sha256: str | None = None
    content: str | None = None
    size_bytes: int | None = None
    reason: str | None = None


def _safe_resolve_check(path: Path, repo_root: Path) -> Path:
    """Resolve path and verify it's within repo root, not a symlink, not in .git."""
    if path.is_symlink():
        raise ValueError(f"Path is a symlink: {path}")
    resolved = path.resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError:
        raise ValueError(f"Path escapes repository root: {path}")
    if ".git" in resolved.parts:
        raise ValueError(f"Path is inside .git: {path}")
    return resolved


def safe_observe_file(path: Path, repo_root: Path, max_bytes: int = MAX_FILE_BYTES) -> SafeFileObservation:
    """Read a file with structured status reporting.

    Strict protocol:
    - lstat/resolve/boundary check first
    - stat size before any read
    - oversized: return immediately, no read_bytes, sha256=None
    - present: single read_bytes, compute sha256 from same bytes, strict UTF-8 decode
    - No errors="replace" — invalid UTF-8 produces decode_failed
    """
    # Symlink check first (before resolve)
    if path.is_symlink():
        return SafeFileObservation(status="symlink_rejected", reason=f"Path is a symlink: {path}")

    resolved = path.resolve()

    # Escape check
    try:
        resolved.relative_to(repo_root)
    except ValueError:
        return SafeFileObservation(status="escape_rejected", reason=f"Path escapes repository root: {path}")

    # .git internal check
    if ".git" in resolved.parts:
        return SafeFileObservation(status="git_internal_rejected", reason=f"Path is inside .git: {path}")

    # Missing check
    if not resolved.is_file():
        return SafeFileObservation(status="missing", reason=f"File not found: {path}")

    # Size check — do NOT read_bytes for oversized files
    size = resolved.stat().st_size
    if size > max_bytes:
        return SafeFileObservation(
            status="oversized", sha256=None, content=None, size_bytes=size,
            reason=f"File too large: {size} bytes (max {max_bytes})",
        )

    # Single read_bytes for both sha256 and content
    raw_bytes = resolved.read_bytes()
    sha = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()

    # Strict UTF-8 decode — no errors="replace"
    try:
        content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return SafeFileObservation(
            status="decode_failed", sha256=None, content=None, size_bytes=size,
            reason=f"Invalid UTF-8: {exc}",
        )

    return SafeFileObservation(status="present", sha256=sha, content=content, size_bytes=size)


def _safe_read(path: Path, repo_root: Path, max_bytes: int = MAX_FILE_BYTES) -> str | None:
    """Read a file with symlink/size/root checks. Returns None if missing or rejected."""
    obs = safe_observe_file(path, repo_root, max_bytes)
    return obs.content if obs.status == "present" else None


def _safe_sha256(path: Path, repo_root: Path) -> str | None:
    """Compute SHA-256 with symlink/size/root checks."""
    obs = safe_observe_file(path, repo_root)
    return obs.sha256 if obs.status == "present" else None


def observe_project(workspace: str, repository_root: str | None = None) -> dict[str, Any]:
    """Observe project metadata from a workspace directory.

    Uses repository_root (from observe_git) as the canonical root if provided,
    otherwise resolves from workspace. This ensures all file observations use
    the same root as git observation.

    Returns dict with: pyproject_exists, pyproject_sha256, requires_python,
    runtime_deps, dev_deps, pytest_testpaths, ci_config_exists, ci_config_sha256,
    blind_spots, file_observations.
    """
    ws = Path(workspace)
    repo_root = Path(repository_root).resolve() if repository_root else ws.resolve()

    blind_spots: list[str] = []
    file_observations: dict[str, SafeFileObservation] = {}
    requires_python: str | None = None
    runtime_deps: list[str] = []
    dev_deps: list[str] = []
    pytest_testpaths: list[str] = ["tests"]

    # pyproject.toml — always read from repository_root
    pyproject_path = repo_root / "pyproject.toml"
    pyproject_obs = safe_observe_file(pyproject_path, repo_root)
    file_observations["pyproject.toml"] = pyproject_obs
    pyproject_exists = pyproject_obs.status == "present"
    pyproject_sha256 = pyproject_obs.sha256 if pyproject_exists else None

    if pyproject_obs.status == "present":
        try:
            import tomllib
            data = tomllib.loads(pyproject_obs.content)
            project = data.get("project", {})
            requires_python = project.get("requires-python")
            runtime_deps = list(project.get("dependencies", []))
            dev_section = project.get("optional-dependencies", {})
            dev_deps = list(dev_section.get("dev", []))

            pytest_section = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
            tp = pytest_section.get("testpaths")
            if tp:
                pytest_testpaths = list(tp)
        except Exception as exc:
            blind_spots.append(f"pyproject.toml parse failed: {type(exc).__name__}: {exc}")
            file_observations["pyproject.toml"] = SafeFileObservation(
                status="parse_failed", sha256=pyproject_obs.sha256,
                content=pyproject_obs.content, size_bytes=pyproject_obs.size_bytes,
                reason=f"Parse failed: {type(exc).__name__}: {exc}",
            )
            requires_python = None
            runtime_deps = []
            dev_deps = []
    elif pyproject_obs.status == "missing":
        blind_spots.append("pyproject.toml missing — cannot determine Python version or dependencies")
    else:
        blind_spots.append(f"pyproject.toml {pyproject_obs.status}: {pyproject_obs.reason}")

    # CI config — always read from repository_root
    ci_paths = [
        repo_root / ".github" / "workflows" / "ci.yml",
        repo_root / ".github" / "workflows" / "ci.yaml",
        repo_root / ".gitlab-ci.yml",
    ]
    ci_config_exists = False
    ci_config_sha256 = None
    for cp in ci_paths:
        cp_obs = safe_observe_file(cp, repo_root)
        file_observations[cp.name] = cp_obs
        if cp_obs.status == "present":
            ci_config_exists = True
            ci_config_sha256 = cp_obs.sha256
            break
        elif cp_obs.status not in ("missing",):
            blind_spots.append(f"CI config {cp.name} {cp_obs.status}: {cp_obs.reason}")

    if not ci_config_exists:
        blind_spots.append("no CI configuration found")

    return {
        "pyproject_exists": pyproject_exists,
        "pyproject_sha256": pyproject_sha256,
        "requires_python": requires_python,
        "runtime_deps": tuple(runtime_deps),
        "dev_deps": tuple(dev_deps),
        "pytest_testpaths": tuple(pytest_testpaths),
        "ci_config_exists": ci_config_exists,
        "ci_config_sha256": ci_config_sha256,
        "blind_spots": tuple(blind_spots),
        "file_observations": file_observations,
    }
