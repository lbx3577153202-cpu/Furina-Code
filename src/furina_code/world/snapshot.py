"""Furina Code world — ProjectSnapshot creation."""

from __future__ import annotations

import hashlib
from typing import Any

from ..contracts.meta import canonical_json_dumps
from ..contracts.objects import ProjectSnapshot
from .git import observe_git
from .observe import observe_project


def create_project_snapshot(
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    workspace: str,
    snapshot_id: str | None = None,
    causation_ref: str | None = None,
) -> ProjectSnapshot:
    """Observe workspace and create a ProjectSnapshot formal object."""
    git_obs = observe_git(workspace)
    proj_obs = observe_project(workspace)

    # Merge all observations for snapshot hash
    all_obs: dict[str, Any] = {**git_obs}
    for k, v in proj_obs.items():
        if isinstance(v, tuple):
            all_obs[k] = list(v)
        else:
            all_obs[k] = v

    snapshot_sha256 = "sha256:" + hashlib.sha256(
        canonical_json_dumps(all_obs).encode("utf-8")
    ).hexdigest()

    return ProjectSnapshot.create(
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref=project_ref,
        correlation_id=correlation_id,
        head_sha=git_obs["head_sha"],
        branch=git_obs["branch"],
        status_lines=git_obs["status_lines"],
        tracked_count=git_obs["tracked_count"],
        untracked_count=git_obs["untracked_count"],
        is_clean=git_obs["is_clean"],
        pyproject_exists=proj_obs["pyproject_exists"],
        pyproject_sha256=proj_obs["pyproject_sha256"],
        requires_python=proj_obs["requires_python"],
        runtime_deps=proj_obs["runtime_deps"],
        dev_deps=proj_obs["dev_deps"],
        pytest_testpaths=proj_obs["pytest_testpaths"],
        ci_config_exists=proj_obs["ci_config_exists"],
        ci_config_sha256=proj_obs["ci_config_sha256"],
        blind_spots=proj_obs["blind_spots"],
        snapshot_sha256=snapshot_sha256,
        snapshot_id=snapshot_id,
        causation_ref=causation_ref,
    )
