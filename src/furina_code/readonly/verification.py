"""Furina Code readonly — verification logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..contracts.errors import ContractInvalid
from ..contracts.objects import (
    EvidenceEnvelope,
    VerificationPlan,
    VerificationVerdict,
    ProjectSnapshot,
    RunBinding,
    TaskDossier,
    BackendProfile,
    ContextEnvelope,
    CandidateEnvelope,
    CompletionVerdict,
    RunBindingStatus,
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


@dataclass
class GateResult:
    """Non-informal value object for gate evaluation."""
    gate_id: str
    outcome: str  # "pass" | "fail" | "inconclusive"
    checked_conditions: tuple[str, ...]
    supporting_refs: tuple[str, ...]
    failed_conditions: tuple[str, ...]
    checked_at: str
    evidence_ref: str | None = None


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
    """Run all steps, collect evidence, produce aggregate verdict."""
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
        criterion = step
        for crit_name, check_name in plan.success_criteria_map.items():
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


def evaluate_gate(
    gate_id: str,
    rb: RunBinding | None,
    td: TaskDossier | None,
    snapshot: ProjectSnapshot | None,
    bp: BackendProfile | None,
    ctx: ContextEnvelope | None,
    ce: CandidateEnvelope | None,
    vplan: VerificationPlan | None,
    agg_verdict: VerificationVerdict | None,
    cv: CompletionVerdict | None,
) -> GateResult:
    """Evaluate a single gate against actual formal objects."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conditions: list[str] = []
    failed: list[str] = []

    if gate_id == "IL-G0":
        # RunBinding active; user/project/task consistent; git_read in tools
        if rb is None:
            return GateResult(gate_id, "fail", ("RunBinding exists",), (), ("RunBinding missing",), now)
        conditions.append("RunBinding active")
        if rb.status != RunBindingStatus.ACTIVE:
            failed.append("RunBinding not active")
        conditions.append("user/project/task consistent")
        if rb.project_ref != (td.meta.project_ref if td else ""):
            failed.append("project_ref mismatch")
        conditions.append("git_read in tool classes")
        if "git_read" not in rb.allowed_tool_classes:
            failed.append("git_read not in allowed_tool_classes")
        conditions.append("binding integrity valid")
        if not rb.meta.integrity_ref.startswith("sha256:"):
            failed.append("RunBinding integrity invalid")

    elif gate_id == "IL-G1":
        # TaskDossier completeness
        if td is None:
            return GateResult(gate_id, "fail", ("TaskDossier exists",), (), ("TaskDossier missing",), now)
        for field in ("source_intent_ref", "structured_goal", "success_criteria", "scope", "exclusions", "unknowns", "user_constraints"):
            conditions.append(f"{field} present")
            val = getattr(td, field, None)
            if val is None:
                failed.append(f"{field} missing")
        conditions.append("task revision present")
        if td.meta.revision < 1:
            failed.append("task revision invalid")

    elif gate_id == "IL-G2":
        # ProjectSnapshot validity
        if snapshot is None:
            return GateResult(gate_id, "fail", ("ProjectSnapshot exists",), (), ("ProjectSnapshot missing",), now)
        conditions.append("observation_scope set")
        if not snapshot.observation_scope:
            failed.append("observation_scope empty")
        conditions.append("freshness_policy set")
        if not snapshot.freshness_policy:
            failed.append("freshness_policy empty")
        conditions.append("git_ref present")
        if not snapshot.git_ref:
            failed.append("git_ref empty")
        conditions.append("file_facts present")
        if not snapshot.file_facts:
            failed.append("file_facts empty")
        conditions.append("environment_facts present")
        if not snapshot.environment_facts:
            failed.append("environment_facts empty")
        conditions.append("blind_spots recorded")
        # blind_spots can be empty (that's valid — no blind spots)
        if snapshot.blind_spots is None:
            failed.append("blind_spots is None")

    elif gate_id == "IL-G4":
        # BackendProfile and disclosure
        if bp is None:
            return GateResult(gate_id, "fail", ("BackendProfile exists",), (), ("BackendProfile missing",), now)
        conditions.append("BackendProfile health available")
        if bp.health != "available":
            failed.append(f"BackendProfile health={bp.health}")
        if ctx is not None:
            conditions.append("ContextEnvelope.backend_ref matches")
            if ctx.backend_ref != bp.meta.integrity_ref:
                failed.append("backend_ref mismatch")
            conditions.append("context_digest present")
            if not ctx.context_digest:
                failed.append("context_digest empty")
            conditions.append("disclosure rules present")
            if not ctx.redactions:
                failed.append("redactions empty")
        if ce is not None:
            conditions.append("CandidateEnvelope bound to context")
            if ce.context_ref != (ctx.meta.integrity_ref if ctx else ""):
                failed.append("candidate context_ref mismatch")
            conditions.append("requested_actions empty")
            if ce.requested_actions:
                failed.append("requested_actions not empty")

    elif gate_id == "IL-G6":
        # Verification completeness
        if vplan is None:
            return GateResult(gate_id, "fail", ("VerificationPlan exists",), (), ("VerificationPlan missing",), now)
        conditions.append("success criteria fully mapped")
        if td is not None:
            td_criteria = set(td.success_criteria)
            plan_criteria = set(vplan.success_criteria_map.keys())
            if td_criteria != plan_criteria:
                failed.append(f"criteria mismatch: dossier={td_criteria} plan={plan_criteria}")
        conditions.append("all checks have evidence")
        if agg_verdict is not None:
            if len(agg_verdict.evidence_refs) < len(vplan.checks):
                failed.append("fewer evidence refs than checks")
            conditions.append("coverage == 1.0")
            if agg_verdict.coverage < 1.0:
                failed.append(f"coverage={agg_verdict.coverage}")
            conditions.append("no critical unknowns")
            if agg_verdict.unknowns:
                failed.append(f"unknowns: {agg_verdict.unknowns}")

    elif gate_id == "IL-G7":
        # CompletionVerdict honesty
        if cv is None:
            return GateResult(gate_id, "fail", ("CompletionVerdict exists",), (), ("CompletionVerdict missing",), now)
        if agg_verdict is not None:
            conditions.append("verification_ref current")
            if cv.verification_ref != agg_verdict.meta.integrity_ref:
                failed.append("verification_ref mismatch")
        conditions.append("no_project_side_effect true")
        if not cv.no_project_side_effect:
            failed.append("no_project_side_effect is false")
        conditions.append("user_effect describes limitations")
        if "not modified" not in cv.user_effect.lower() and "not implemented" not in cv.user_effect.lower():
            failed.append("user_effect does not describe limitations")
        conditions.append("completed/incomplete semantically consistent")
        if cv.outcome == "completed" and cv.incomplete_items:
            failed.append("completed but has incomplete_items")
        conditions.append("residual_risks stated if incomplete")
        if cv.outcome != "completed" and not cv.residual_risks:
            failed.append("not completed but no residual_risks")

    else:
        return GateResult(gate_id, "inconclusive", (), (), (f"Unknown gate: {gate_id}",), now)

    outcome = "fail" if failed else "pass"
    return GateResult(gate_id, outcome, tuple(conditions), (), tuple(failed), now)


def build_gate_results(
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    rb: RunBinding | None,
    td: TaskDossier | None,
    snapshot: ProjectSnapshot | None,
    bp: BackendProfile | None,
    ctx: ContextEnvelope | None,
    ce: CandidateEnvelope | None,
    vplan: VerificationPlan | None,
    agg_verdict: VerificationVerdict | None,
    cv: CompletionVerdict | None = None,
    causation_ref: str | None = None,
) -> tuple[list[EvidenceEnvelope], list[GateResult]]:
    """Build structured IL-G0/G1/G2/G4/G6/G7 gate evidence with real checks."""
    gate_ids = ("IL-G0", "IL-G1", "IL-G2", "IL-G4", "IL-G6", "IL-G7")
    evidences: list[EvidenceEnvelope] = []
    results: list[GateResult] = []

    for gate_id in gate_ids:
        gr = evaluate_gate(gate_id, rb, td, snapshot, bp, ctx, ce, vplan, agg_verdict, cv)

        ev = EvidenceEnvelope.create(
            run_binding_id=run_binding_id,
            task_id=task_id,
            task_run_id=task_run_id,
            project_ref=project_ref,
            correlation_id=correlation_id,
            claim_scope=gate_id,
            evidence_type="gate_evaluation",
            source_ref=f"gate:{gate_id}",
            claim=f"{gate_id}: {gr.outcome} — checked {len(gr.checked_conditions)} conditions, {len(gr.failed_conditions)} failed",
            source_refs=gr.supporting_refs,
            causal_links=(vplan.meta.integrity_ref,) if vplan else (),
            supporting_refs=(agg_verdict.meta.integrity_ref,) if agg_verdict else (),
            integrity_status="verified" if gr.outcome == "pass" else "failed",
            envelope_id=f"{task_id}:gate:{gate_id}",
            causation_ref=causation_ref,
        )
        gr.evidence_ref = ev.meta.integrity_ref
        evidences.append(ev)
        results.append(gr)

    return evidences, results
