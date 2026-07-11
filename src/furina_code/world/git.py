"""Furina Code world — Git repository observation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from ..contracts.errors import ContractInvalid


def _run_git(workspace: str, *args: str) -> str:
    """Run a git command in the workspace with safety constraints."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    try:
        result = subprocess.run(
            ["git", "-C", workspace, *args],
            capture_output=True,
            text=True,
            shell=False,
            timeout=30,
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise ContractInvalid(
            f"Git command timed out: git {' '.join(args)}",
            {"command": args},
        )
    except FileNotFoundError:
        raise ContractInvalid("Git executable not found", {"command": args})
    if result.returncode != 0:
        raise ContractInvalid(
            f"Git command failed: git {' '.join(args)}",
            {"returncode": result.returncode, "stderr": result.stderr.strip()},
        )
    return result.stdout.strip()


def resolve_repository_root(workspace: str) -> str:
    """Resolve the real repository root via git rev-parse --show-toplevel."""
    return _run_git(workspace, "rev-parse", "--show-toplevel")


def observe_git(workspace: str) -> dict[str, Any]:
    """Observe a Git repository without modifying it.

    Uses git rev-parse --show-toplevel to resolve the real root.
    Uses git status --porcelain=v2 for status.
    Uses GIT_OPTIONAL_LOCKS=0 and shell=False.

    Returns dict with: repository_root, head_sha, branch, status_lines,
    tracked_count, untracked_count, is_clean.
    """
    ws = Path(workspace)
    if not ws.is_dir():
        raise ContractInvalid(f"Workspace does not exist: {workspace}")

    # Resolve real repository root
    repo_root = resolve_repository_root(workspace)

    head_sha = _run_git(workspace, "rev-parse", "HEAD")
    if len(head_sha) != 40 or not all(c in "0123456789abcdef" for c in head_sha):
        raise ContractInvalid(f"Invalid HEAD SHA: {head_sha}")

    branch = _run_git(workspace, "branch", "--show-current")
    if not branch:
        branch = f"detached@{head_sha[:12]}"

    # Use porcelain=v2 for machine-readable output
    status_raw = _run_git(workspace, "status", "--porcelain=v2")
    status_lines = tuple(line for line in status_raw.splitlines() if line.strip()) if status_raw else ()

    ls_files_raw = _run_git(workspace, "ls-files")
    tracked_count = len(ls_files_raw.splitlines()) if ls_files_raw else 0

    ls_others_raw = _run_git(workspace, "ls-files", "--others", "--exclude-standard")
    untracked_count = len(ls_others_raw.splitlines()) if ls_others_raw else 0

    return {
        "repository_root": repo_root,
        "head_sha": head_sha,
        "branch": branch,
        "status_lines": status_lines,
        "tracked_count": tracked_count,
        "untracked_count": untracked_count,
        "is_clean": len(status_lines) == 0,
    }
