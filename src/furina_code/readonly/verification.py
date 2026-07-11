"""Furina Code readonly — verification logic."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..contracts.errors import ContractInvalid
from ..contracts.meta import canonical_json_dumps
from ..contracts.objects import (
    EvidenceEnvelope,
    VerificationPlan,
    VerificationVerdict,
    ProjectSnapshot,
)

# Built-in verification step names
ALL_STEPS = (
    "snapshot_head_match",
    "snapshot_branch_match",
    "snapshot_clean_match",
    "snapshot_file_count_match",
    "snapshot_python_requires_match",
    "snapshot_runtime_deps_match",
    "snapshot_dev_deps_match",
    "snapshot_pytest_testpaths_match",
    "snapshot_ci_config_match",
    "snapshot_blind_spots_match",
)


def create_verification_plan(
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    candidate_ref: str,
    success_criteria: tuple[str, ...],
    steps: tuple[str, ...] | None = None,
    envelope_id: str | None = None,
) -> VerificationPlan:
    """Create a VerificationPlan with specified or default steps."""
    return VerificationPlan.create(
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref=project_ref,
        correlation_id=correlation_id,
        candidate_ref=candidate_ref,
        success_criteria=success_criteria,
        steps=steps or ALL_STEPS,
        envelope_id=envelope_id,
    )


def verify_candidate_against_snapshot(
    candidate_content: dict[str, Any],
    snapshot: ProjectSnapshot,
    step: str,
) -> tuple[bool, str]:
    """Run a single verification step comparing candidate to snapshot.

    Returns (passed, message).
    """
    c = candidate_content.get("content", {})

    checks = {
        "snapshot_head_match": (
            c.get("repository_head") == snapshot.head_sha,
            f"HEAD: candidate={c.get('repository_head')!r} snapshot={snapshot.head_sha!r}",
        ),
        "snapshot_branch_match": (
            c.get("branch") == snapshot.branch,
            f"branch: candidate={c.get('branch')!r} snapshot={snapshot.branch!r}",
        ),
        "snapshot_clean_match": (
            c.get("working_tree") == ("clean" if snapshot.is_clean else "dirty"),
            f"working_tree: candidate={c.get('working_tree')!r} expected={'clean' if snapshot.is_clean else 'dirty'}",
        ),
        "snapshot_file_count_match": (
            c.get("tracked_file_count") == snapshot.tracked_count
            and c.get("untracked_file_count") == snapshot.untracked_count,
            f"file_count: candidate tracked={c.get('tracked_file_count')} untracked={c.get('untracked_file_count')} "
            f"snapshot tracked={snapshot.tracked_count} untracked={snapshot.untracked_count}",
        ),
        "snapshot_python_requires_match": (
            c.get("python_requires") == snapshot.requires_python,
            f"python_requires: candidate={c.get('python_requires')!r} snapshot={snapshot.requires_python!r}",
        ),
        "snapshot_runtime_deps_match": (
            tuple(c.get("runtime_dependencies", [])) == snapshot.runtime_deps,
            f"runtime_deps mismatch",
        ),
        "snapshot_dev_deps_match": (
            tuple(c.get("dev_dependencies", [])) == snapshot.dev_deps,
            f"dev_deps mismatch",
        ),
        "snapshot_pytest_testpaths_match": (
            tuple(c.get("pytest_testpaths", [])) == snapshot.pytest_testpaths,
            f"pytest_testpaths mismatch",
        ),
        "snapshot_ci_config_match": (
            c.get("ci_config", {}).get("present") == snapshot.ci_config_exists
            and c.get("ci_config", {}).get("sha256") == snapshot.ci_config_sha256,
            f"ci_config mismatch",
        ),
        "snapshot_blind_spots_match": (
            tuple(c.get("blind_spots", [])) == snapshot.blind_spots,
            f"blind_spots mismatch",
        ),
    }

    if step not in checks:
        raise ContractInvalid(f"Unknown verification step: {step}", {"step": step})

    return checks[step]


def collect_evidence(
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    evidence_type: str,
    source_ref: str,
    claim: str,
    supporting_refs: tuple[str, ...] = (),
    integrity_status: str = "verified",
    envelope_id: str | None = None,
) -> EvidenceEnvelope:
    """Create an EvidenceEnvelope."""
    return EvidenceEnvelope.create(
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref=project_ref,
        correlation_id=correlation_id,
        evidence_type=evidence_type,
        source_ref=source_ref,
        claim=claim,
        supporting_refs=supporting_refs,
        integrity_status=integrity_status,
        envelope_id=envelope_id,
    )


def execute_verification(
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    plan: VerificationPlan,
    candidate_content: dict[str, Any],
    snapshot: ProjectSnapshot,
) -> tuple[list[EvidenceEnvelope], list[VerificationVerdict]]:
    """Run all steps in the plan, collect evidence, produce verdicts."""
    evidences: list[EvidenceEnvelope] = []
    verdicts: list[VerificationVerdict] = []

    for i, step in enumerate(plan.steps):
        passed, message = verify_candidate_against_snapshot(candidate_content, snapshot, step)

        ev = collect_evidence(
            run_binding_id=run_binding_id,
            task_id=task_id,
            task_run_id=task_run_id,
            project_ref=project_ref,
            correlation_id=correlation_id,
            evidence_type="existence_check",
            source_ref=f"verification:{step}",
            claim=message,
            supporting_refs=(snapshot.meta.integrity_ref,),
            integrity_status="verified" if passed else "failed",
            envelope_id=f"{task_id}:evidence:{step}",
        )
        evidences.append(ev)

        vv = VerificationVerdict.create(
            run_binding_id=run_binding_id,
            task_id=task_id,
            task_run_id=task_run_id,
            project_ref=project_ref,
            correlation_id=correlation_id,
            plan_ref=plan.meta.integrity_ref,
            outcome="pass" if passed else "fail",
            checked_conditions=(step,),
            supporting_refs=(ev.meta.integrity_ref,),
            failed_conditions=() if passed else (step,),
            envelope_id=f"{task_id}:vverdict:{step}",
        )
        verdicts.append(vv)

    return evidences, verdicts
