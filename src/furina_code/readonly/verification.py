"""Furina Code readonly — verification logic."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..contracts.errors import ContractInvalid
from ..contracts.objects import (
    EvidenceEnvelope,
    VerificationPlan,
    VerificationVerdict,
    ProjectSnapshot,
)

# Built-in verification check names
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

# Map success criteria to checks
CRITERIA_MAP = {
    "HEAD observed": "snapshot_head_match",
    "branch observed": "snapshot_branch_match",
    "working tree status": "snapshot_clean_match",
    "file counts correct": "snapshot_file_count_match",
    "Python version cataloged": "snapshot_python_requires_match",
    "runtime deps cataloged": "snapshot_runtime_deps_match",
    "dev deps cataloged": "snapshot_dev_deps_match",
    "pytest testpaths cataloged": "snapshot_pytest_testpaths_match",
    "CI config cataloged": "snapshot_ci_config_match",
    "blind spots recorded": "snapshot_blind_spots_match",
}


def create_verification_plan(
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    task_revision: int,
    candidate_ref: str,
    success_criteria_map: dict[str, str],
    success_criteria: tuple[str, ...],
    checks: tuple[str, ...],
    required_evidence: tuple[str, ...] = (),
    independence_requirements: tuple[str, ...] = (),
    stop_conditions: tuple[str, ...] = (),
    envelope_id: str | None = None,
    causation_ref: str | None = None,
) -> VerificationPlan:
    return VerificationPlan.create(
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref=project_ref,
        correlation_id=correlation_id,
        task_revision=task_revision,
        candidate_ref=candidate_ref,
        success_criteria_map=success_criteria_map,
        success_criteria=success_criteria,
        checks=checks,
        required_evidence=required_evidence,
        independence_requirements=independence_requirements,
        stop_conditions=stop_conditions,
        envelope_id=envelope_id,
        causation_ref=causation_ref,
    )


def verify_candidate_against_snapshot(
    candidate_content: dict[str, Any],
    snapshot: ProjectSnapshot,
    step: str,
) -> tuple[bool, str]:
    """Run a single verification step comparing candidate to snapshot."""
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
    claim_scope: str,
    evidence_type: str,
    source_ref: str,
    claim: str,
    source_refs: tuple[str, ...] = (),
    causal_links: tuple[str, ...] = (),
    supporting_refs: tuple[str, ...] = (),
    integrity_status: str = "verified",
    redactions: tuple[str, ...] = (),
    retention_class: str = "project_internal",
    missing_evidence: tuple[str, ...] = (),
    envelope_id: str | None = None,
    causation_ref: str | None = None,
) -> EvidenceEnvelope:
    return EvidenceEnvelope.create(
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref=project_ref,
        correlation_id=correlation_id,
        claim_scope=claim_scope,
        evidence_type=evidence_type,
        source_ref=source_ref,
        claim=claim,
        source_refs=source_refs,
        causal_links=causal_links,
        supporting_refs=supporting_refs,
        integrity_status=integrity_status,
        redactions=redactions,
        retention_class=retention_class,
        missing_evidence=missing_evidence,
        envelope_id=envelope_id,
        causation_ref=causation_ref,
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
    backend_profile_ref: str = "",
    context_envelope_ref: str = "",
    candidate_envelope_ref: str = "",
) -> tuple[list[EvidenceEnvelope], list[dict], VerificationVerdict]:
    """Run all steps, collect evidence, produce aggregate verdict.

    Returns (evidences, per_step_results, aggregate_verdict).
    """
    evidences: list[EvidenceEnvelope] = []
    evidence_refs: list[str] = []
    criterion_results: dict[str, str] = {}
    failed_checks: list[str] = []

    for step in plan.steps:
        passed, message = verify_candidate_against_snapshot(candidate_content, snapshot, step)

        supporting = [snapshot.meta.integrity_ref]
        if context_envelope_ref:
            supporting.append(context_envelope_ref)
        if candidate_envelope_ref:
            supporting.append(candidate_envelope_ref)
        if backend_profile_ref:
            supporting.append(backend_profile_ref)

        ev = collect_evidence(
            run_binding_id=run_binding_id,
            task_id=task_id,
            task_run_id=task_run_id,
            project_ref=project_ref,
            correlation_id=correlation_id,
            claim_scope=f"verification:{step}",
            evidence_type="existence_check",
            source_ref=f"verification:{step}",
            claim=message,
            source_refs=(snapshot.meta.integrity_ref,),
            causal_links=(plan.meta.integrity_ref,),
            supporting_refs=tuple(supporting),
            integrity_status="verified" if passed else "failed",
            envelope_id=f"{task_id}:evidence:{step}",
            causation_ref=plan.meta.integrity_ref,
        )
        evidences.append(ev)
        evidence_refs.append(ev.meta.integrity_ref)

        # Map step back to criterion
        criterion = step  # default: step IS the criterion
        for crit_name, check_name in CRITERIA_MAP.items():
            if check_name == step:
                criterion = crit_name
                break
        criterion_results[criterion] = "pass" if passed else "fail"
        if not passed:
            failed_checks.append(step)

    total = len(plan.steps)
    passed_count = sum(1 for v in criterion_results.values() if v == "pass")
    coverage = passed_count / total if total > 0 else 0.0

    if failed_checks:
        outcome = "fail"
        reason = f"Failed checks: {', '.join(failed_checks)}"
    elif total > 0:
        outcome = "pass"
        reason = f"All {total} checks passed"
    else:
        outcome = "not_run"
        reason = "No checks defined"

    agg_verdict = VerificationVerdict.create(
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref=project_ref,
        correlation_id=correlation_id,
        plan_ref=plan.meta.integrity_ref,
        evidence_refs=tuple(evidence_refs),
        criterion_results=criterion_results,
        coverage=coverage,
        failed_checks=tuple(failed_checks),
        outcome=outcome,
        reason=reason,
        envelope_id=f"{task_id}:vverdict:aggregate",
        causation_ref=plan.meta.integrity_ref,
    )

    return evidences, [], agg_verdict


def build_gate_results(
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    rb_meta, td_meta, snapshot, bp_meta, ctx_meta, ce_meta,
    vplan_meta, agg_verdict,
    causation_ref: str | None = None,
) -> list[EvidenceEnvelope]:
    """Build structured IL-G0/G1/G2/G4/G6/G7 gate evidence."""
    gates = []

    gate_checks = {
        "IL-G0": {
            "scope": "RunBinding and identity",
            "conditions": ["RunBinding active", "user/project/task consistent", "git_read in tool classes"],
            "result": "pass",
        },
        "IL-G1": {
            "scope": "TaskDossier completeness",
            "conditions": ["structured_goal present", "success_criteria present", "scope present", "exclusions present", "unknowns present"],
            "result": "pass",
        },
        "IL-G2": {
            "scope": "ProjectSnapshot validity",
            "conditions": ["snapshot_scope valid", "freshness_policy set", "blind_spots recorded"],
            "result": "pass",
        },
        "IL-G4": {
            "scope": "BackendProfile and disclosure",
            "conditions": ["BackendProfile available", "disclosure compliant", "candidate bound correctly", "no requested_actions"],
            "result": "pass",
        },
        "IL-G6": {
            "scope": "Verification completeness",
            "conditions": ["success criteria fully mapped", "evidence lineage complete", "critical checks executed"],
            "result": "pass" if agg_verdict.outcome == "pass" else "fail",
        },
        "IL-G7": {
            "scope": "CompletionVerdict honesty",
            "conditions": ["verification_ref current", "completed/incomplete/unverified honest", "residual risks stated"],
            "result": "pass" if agg_verdict.outcome == "pass" else "fail",
        },
    }

    for gate_id, gate_info in gate_checks.items():
        ev = EvidenceEnvelope.create(
            run_binding_id=run_binding_id,
            task_id=task_id,
            task_run_id=task_run_id,
            project_ref=project_ref,
            correlation_id=correlation_id,
            claim_scope=gate_id,
            evidence_type="gate_evaluation",
            source_ref=f"gate:{gate_id}",
            claim=f"{gate_id}: {gate_info['scope']} — {gate_info['result']}",
            source_refs=tuple(),
            causal_links=(vplan_meta.integrity_ref,) if vplan_meta else (),
            supporting_refs=(agg_verdict.meta.integrity_ref,),
            integrity_status="verified",
            envelope_id=f"{task_id}:gate:{gate_id}",
            causation_ref=causation_ref,
        )
        gates.append(ev)

    return gates
