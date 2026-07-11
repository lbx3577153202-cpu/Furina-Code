"""Furina Code world — project metadata observation."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def _safe_read(path: Path, max_bytes: int = 1_000_000) -> str | None:
    """Read a file with size limit. Returns None if missing or too large."""
    if not path.is_file():
        return None
    if path.stat().st_size > max_bytes:
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def observe_project(workspace: str) -> dict[str, Any]:
    """Observe project metadata from a workspace directory.

    Returns dict with: pyproject_exists, pyproject_sha256, requires_python,
    runtime_deps, dev_deps, pytest_testpaths, ci_config_exists, ci_config_sha256,
    blind_spots.
    """
    ws = Path(workspace)

    # pyproject.toml
    pyproject_path = ws / "pyproject.toml"
    pyproject_content = _safe_read(pyproject_path)
    pyproject_exists = pyproject_content is not None
    pyproject_sha256 = _sha256_file(pyproject_path) if pyproject_exists else None

    requires_python = None
    runtime_deps: list[str] = []
    dev_deps: list[str] = []
    pytest_testpaths: list[str] = ["tests"]

    if pyproject_exists:
        # Parse with tomllib (stdlib 3.11+)
        try:
            import tomllib
            data = tomllib.loads(pyproject_content)
            project = data.get("project", {})
            requires_python = project.get("requires-python")
            runtime_deps = list(project.get("dependencies", []))
            dev_section = project.get("optional-dependencies", {})
            dev_deps = list(dev_section.get("dev", []))

            # pytest config
            pytest_section = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
            tp = pytest_section.get("testpaths")
            if tp:
                pytest_testpaths = list(tp)
        except Exception:
            pass  # Best effort

    # CI config
    ci_paths = [
        ws / ".github" / "workflows" / "ci.yml",
        ws / ".github" / "workflows" / "ci.yaml",
        ws / ".gitlab-ci.yml",
    ]
    ci_config_exists = False
    ci_config_sha256 = None
    for cp in ci_paths:
        if cp.is_file():
            ci_config_exists = True
            ci_config_sha256 = _sha256_file(cp)
            break

    blind_spots: list[str] = []
    if not pyproject_exists:
        blind_spots.append("pyproject.toml missing — cannot determine Python version or dependencies")
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
