"""Furina Code world — project metadata observation."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 1_000_000  # 1 MB


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


def _safe_read(path: Path, repo_root: Path, max_bytes: int = MAX_FILE_BYTES) -> str | None:
    """Read a file with symlink/size/root checks. Returns None if missing."""
    try:
        resolved = _safe_resolve_check(path, repo_root)
    except ValueError:
        return None
    if not resolved.is_file():
        return None
    if resolved.stat().st_size > max_bytes:
        return None
    return resolved.read_text(encoding="utf-8", errors="replace")


def _safe_sha256(path: Path, repo_root: Path) -> str | None:
    """Compute SHA-256 with symlink/size/root checks."""
    try:
        resolved = _safe_resolve_check(path, repo_root)
    except ValueError:
        return None
    if not resolved.is_file():
        return None
    if resolved.stat().st_size > MAX_FILE_BYTES:
        return None
    return "sha256:" + hashlib.sha256(resolved.read_bytes()).hexdigest()


def observe_project(workspace: str) -> dict[str, Any]:
    """Observe project metadata from a workspace directory.

    Returns dict with: pyproject_exists, pyproject_sha256, requires_python,
    runtime_deps, dev_deps, pytest_testpaths, ci_config_exists, ci_config_sha256,
    blind_spots.
    """
    ws = Path(workspace)
    repo_root = ws.resolve()

    blind_spots: list[str] = []
    requires_python: str | None = None
    runtime_deps: list[str] = []
    dev_deps: list[str] = []
    pytest_testpaths: list[str] = ["tests"]

    # pyproject.toml
    pyproject_path = ws / "pyproject.toml"
    pyproject_content = _safe_read(pyproject_path, repo_root)
    pyproject_exists = pyproject_content is not None
    pyproject_sha256 = _safe_sha256(pyproject_path, repo_root) if pyproject_exists else None

    if pyproject_exists:
        try:
            import tomllib
            data = tomllib.loads(pyproject_content)
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
            requires_python = None
            runtime_deps = []
            dev_deps = []
    else:
        blind_spots.append("pyproject.toml missing — cannot determine Python version or dependencies")

    # CI config
    ci_paths = [
        ws / ".github" / "workflows" / "ci.yml",
        ws / ".github" / "workflows" / "ci.yaml",
        ws / ".gitlab-ci.yml",
    ]
    ci_config_exists = False
    ci_config_sha256 = None
    for cp in ci_paths:
        try:
            resolved = _safe_resolve_check(cp, repo_root)
            if resolved.is_file():
                ci_config_exists = True
                ci_config_sha256 = _safe_sha256(cp, repo_root)
                break
        except ValueError:
            blind_spots.append(f"CI config path rejected: {cp.name}")
            continue

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
    }
