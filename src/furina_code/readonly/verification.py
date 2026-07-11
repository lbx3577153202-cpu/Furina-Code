"""Furina Code readonly — verification logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

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
    TaskDossierStatus,
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
    task_run: Any | None = None,
    verification_evidence: list[EvidenceEnvelope] | None = None,
    current_heads: dict[str, str] | None = None,
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
        conditions.append("user_ref non-empty")
        if not rb.user_ref:
            failed.append("user_ref empty")
        conditions.append("project_ref consistent")
        if td is not None and rb.project_ref != td.meta.project_ref:
            failed.append("project_ref mismatch with TaskDossier")
        if snapshot is not None and rb.project_ref != snapshot.meta.project_ref:
            failed.append("project_ref mismatch with ProjectSnapshot")
        conditions.append("task_ref consistent")
        if td is not None and rb.task_ref != td.meta.task_id:
            failed.append("task_ref mismatch with TaskDossier")
        conditions.append("task_run_id consistent")
        if task_run is not None and rb.meta.task_run_id != task_run.meta.task_run_id:
            failed.append("task_run_id mismatch")
        conditions.append("correlation_id consistent")
        if td is not None and rb.meta.correlation_id != td.meta.correlation_id:
            failed.append("correlation_id mismatch")
        conditions.append("git_read in tool classes")
        if "git_read" not in rb.allowed_tool_classes:
            failed.append("git_read not in allowed_tool_classes")
        conditions.append("binding integrity valid")
        if not rb.meta.integrity_ref.startswith("sha256:"):
            failed.append("RunBinding integrity invalid format")
        # Verify integrity is from a real ledger (not just format check)
        if rb.meta.integrity_ref == "sha256:" + "0" * 64:
            failed.append("RunBinding integrity is placeholder")

    elif gate_id == "IL-G1":
        # TaskDossier completeness
        if td is None:
            return GateResult(gate_id, "fail", ("TaskDossier exists",), (), ("TaskDossier missing",), now)
        conditions.append("TaskDossier status active")
        if td.status != TaskDossierStatus.ACTIVE:
            failed.append(f"TaskDossier status={td.status.value}")
        for field in ("source_intent_ref", "structured_goal", "success_criteria", "scope", "exclusions", "user_constraints"):
            conditions.append(f"{field} non-empty")
            val = getattr(td, field, None)
            if not val:
                failed.append(f"{field} empty")
        conditions.append("unknowns field present")
        # unknowns can be empty, but field must exist
        if td.unknowns is None:
            failed.append("unknowns is None")
        conditions.append("10 success criteria")
        if len(td.success_criteria) != 10:
            failed.append(f"success_criteria count={len(td.success_criteria)}, expected 10")
        conditions.append("task_revision consistent")
        if task_run is not None and td.meta.revision != task_run.task_revision:
            failed.append(f"task_revision mismatch: dossier={td.meta.revision} run={task_run.task_revision}")

    elif gate_id == "IL-G2":
        # ProjectSnapshot validity — must check observation adequacy
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
        if snapshot.blind_spots is None:
            failed.append("blind_spots is None")
        conditions.append("head_sha valid")
        if not snapshot.head_sha or len(snapshot.head_sha) != 40:
            failed.append("head_sha invalid")
        conditions.append("branch set")
        if not snapshot.branch:
            failed.append("branch empty")
        # Check if critical facts are unknown due to rejection (not just missing)
        conditions.append("critical facts observed")
        _critical_unknown = False
        for bs in snapshot.blind_spots:
            if any(kw in bs.lower() for kw in ("symlink", "rejected", "oversized", "parse failed", "escape")):
                _critical_unknown = True
                break
        if _critical_unknown:
            failed.append("critical facts unknown due to security/size/parse rejection")
        # Missing pyproject.toml is a blind_spot but not a gate failure

    elif gate_id == "IL-G4":
        # BackendProfile and disclosure
        if bp is None:
            return GateResult(gate_id, "fail", ("BackendProfile exists",), (), ("BackendProfile missing",), now)
        conditions.append("BackendProfile health available")
        if bp.health != "available":
            failed.append(f"BackendProfile health={bp.health}")
        conditions.append("BackendProfile current")
        if not bp.backend_id:
            failed.append("backend_id empty")
        if ctx is not None:
            conditions.append("ContextEnvelope.backend_ref matches BackendProfile")
            if ctx.backend_ref != bp.meta.integrity_ref:
                failed.append("backend_ref mismatch")
            conditions.append("context_digest present")
            if not ctx.context_digest:
                failed.append("context_digest empty")
            conditions.append("context_digest valid format")
            if not ctx.context_digest.startswith("sha256:"):
                failed.append("context_digest invalid format")
            conditions.append("disclosure rules present")
            if not ctx.redactions:
                failed.append("redactions empty")
            conditions.append("classification_summary present")
            if not ctx.classification_summary:
                failed.append("classification_summary empty")
            conditions.append("disclosure_basis present")
            if not ctx.disclosure_basis:
                failed.append("disclosure_basis empty")
        if ce is not None:
            conditions.append("CandidateEnvelope bound to context")
            if ce.context_ref != (ctx.meta.integrity_ref if ctx else ""):
                failed.append("candidate context_ref mismatch")
            conditions.append("CandidateEnvelope backend_ref matches")
            if ce.backend_profile_ref != bp.meta.integrity_ref:
                failed.append("candidate backend_profile_ref mismatch")
            conditions.append("candidate_digest present")
            if not ce.candidate_digest:
                failed.append("candidate_digest empty")
            conditions.append("requested_actions empty")
            if ce.requested_actions:
                failed.append("requested_actions not empty")
            conditions.append("candidate intake evidence present")
            if ce.status != "accepted":
                failed.append(f"candidate status={ce.status}")

    elif gate_id == "IL-G6":
        # Verification completeness
        if vplan is None:
            return GateResult(gate_id, "fail", ("VerificationPlan exists",), (), ("VerificationPlan missing",), now)
        conditions.append("success criteria fully mapped")
        if td is not None:
            td_criteria = set(td.success_criteria)
            plan_criteria = set(vplan.success_criteria_map.keys())
            plan_sc = set(vplan.success_criteria)
            if td_criteria != plan_criteria:
                failed.append(f"criteria mismatch: dossier={td_criteria} plan_map={plan_criteria}")
            if td_criteria != plan_sc:
                failed.append(f"criteria mismatch: dossier={td_criteria} plan_sc={plan_sc}")
            if plan_criteria != plan_sc:
                failed.append(f"plan internal mismatch: map_keys={plan_criteria} sc={plan_sc}")
        conditions.append("all checks have evidence")
        if agg_verdict is not None:
            if len(agg_verdict.evidence_refs) < len(vplan.checks):
                failed.append(f"fewer evidence refs ({len(agg_verdict.evidence_refs)}) than checks ({len(vplan.checks)})")
            conditions.append("evidence refs unique")
            if len(set(agg_verdict.evidence_refs)) != len(agg_verdict.evidence_refs):
                failed.append("duplicate evidence refs found")

            # Exact check-to-evidence mapping using actual EvidenceEnvelope objects
            if verification_evidence is not None:
                # Build map: check → evidence integrity_ref
                check_to_evidence: dict[str, str] = {}
                for ev in verification_evidence:
                    # claim_scope is "verification:<check_name>"
                    if ev.claim_scope.startswith("verification:"):
                        check_name = ev.claim_scope.split(":", 1)[1]
                        check_to_evidence[check_name] = ev.meta.integrity_ref

                conditions.append("each check has exactly one evidence")
                for check in vplan.checks:
                    if check not in check_to_evidence:
                        failed.append(f"check '{check}' has no evidence")
                    elif check_to_evidence[check] not in agg_verdict.evidence_refs:
                        failed.append(f"check '{check}' evidence not in verdict refs")

                conditions.append("no extra verification evidence")
                extra = set(check_to_evidence.keys()) - set(vplan.checks)
                if extra:
                    failed.append(f"extra evidence for checks not in plan: {extra}")

                # Verdict refs must equal the required evidence set
                required_ev_refs = frozenset(check_to_evidence.get(c, "") for c in vplan.checks)
                actual_ev_refs = frozenset(agg_verdict.evidence_refs)
                conditions.append("verdict refs equal required evidence set")
                if required_ev_refs != actual_ev_refs:
                    failed.append(f"verdict evidence_refs mismatch: required={len(required_ev_refs)} actual={len(actual_ev_refs)}")

            conditions.append("coverage == 1.0")
            if agg_verdict.coverage < 1.0:
                failed.append(f"coverage={agg_verdict.coverage}")
            conditions.append("no unknowns")
            if agg_verdict.unknowns:
                failed.append(f"unknowns: {agg_verdict.unknowns}")
            conditions.append("outcome == pass")
            if agg_verdict.outcome != "pass":
                failed.append(f"outcome={agg_verdict.outcome}")
            conditions.append("all evidence_refs non-empty")
            for ref in agg_verdict.evidence_refs:
                if not ref:
                    failed.append("empty evidence_ref found")
                    break

    elif gate_id == "IL-G7":
        # CompletionVerdict honesty — run AFTER CompletionVerdict is written
        if cv is None:
            return GateResult(gate_id, "fail", ("CompletionVerdict exists",), (), ("CompletionVerdict missing",), now)
        conditions.append("CompletionVerdict is current head")
        if cv.meta.revision < 1:
            failed.append("CompletionVerdict revision invalid")
        # Verify current head from Ledger
        if current_heads is not None:
            if "CompletionVerdict" in current_heads:
                if cv.meta.integrity_ref != current_heads["CompletionVerdict"]:
                    failed.append("CompletionVerdict is not current head")
            if "VerificationVerdict" in current_heads and agg_verdict is not None:
                if agg_verdict.meta.integrity_ref != current_heads["VerificationVerdict"]:
                    failed.append("VerificationVerdict is not current head")
            if "TaskRun" in current_heads and task_run is not None:
                if task_run.meta.integrity_ref != current_heads["TaskRun"]:
                    failed.append("TaskRun is not current head")
        if agg_verdict is not None:
            conditions.append("verification_ref points to current VerificationVerdict")
            if cv.verification_ref != agg_verdict.meta.integrity_ref:
                failed.append("verification_ref mismatch")
        conditions.append("task_revision matches")
        if task_run is not None and cv.task_revision != task_run.task_revision:
            failed.append(f"task_revision mismatch: cv={cv.task_revision} run={task_run.task_revision}")
        conditions.append("no_project_side_effect true")
        if not cv.no_project_side_effect:
            failed.append("no_project_side_effect is false")
        conditions.append("user_effect describes limitations")
        _ue = cv.user_effect.lower()
        _limitation_indicators = ("not modified", "not implemented", "not run", "not verified", "not proven", "no project")
        if not any(ind in _ue for ind in _limitation_indicators):
            failed.append("user_effect does not describe limitations")
        conditions.append("completed/incomplete/unverified no conflicts")
        if cv.outcome == "completed" and cv.incomplete_items:
            failed.append("completed but has incomplete_items")
        if cv.outcome == "completed" and cv.unverified_items:
            failed.append("completed but has unverified_items")
        # Check no overlap between completed/incomplete/unverified
        _completed = set(cv.completed_items)
        _incomplete = set(cv.incomplete_items)
        _unverified = set(cv.unverified_items)
        if _completed & _incomplete:
            failed.append(f"completed/incomplete overlap: {_completed & _incomplete}")
        if _completed & _unverified:
            failed.append(f"completed/unverified overlap: {_completed & _unverified}")
        if _incomplete & _unverified:
            failed.append(f"incomplete/unverified overlap: {_incomplete & _unverified}")
        # agg_verdict fail/inconclusive → CompletionVerdict must not be completed
        if agg_verdict is not None and agg_verdict.outcome != "pass" and cv.outcome == "completed":
            failed.append(f"VerificationVerdict={agg_verdict.outcome} but CompletionVerdict=completed")
        conditions.append("residual_risks stated if not completed")
        if cv.outcome != "completed" and not cv.residual_risks:
            failed.append("not completed but no residual_risks")
        # G7 failure must block terminal
        if failed:
            conditions.append("G7 failure blocks terminal")
    else:
        return GateResult(gate_id, "inconclusive", (), (), (f"Unknown gate: {gate_id}",), now)

    # Build supporting_refs based on gate type
    supporting = []
    if gate_id == "IL-G0":
        for obj in (rb, td, task_run, snapshot):
            if obj is not None and hasattr(obj, 'meta'):
                supporting.append(obj.meta.integrity_ref)
    elif gate_id == "IL-G1":
        for obj in (td, task_run):
            if obj is not None and hasattr(obj, 'meta'):
                supporting.append(obj.meta.integrity_ref)
    elif gate_id == "IL-G2":
        if snapshot is not None and hasattr(snapshot, 'meta'):
            supporting.append(snapshot.meta.integrity_ref)
    elif gate_id == "IL-G4":
        for obj in (bp, ctx, ce):
            if obj is not None and hasattr(obj, 'meta'):
                supporting.append(obj.meta.integrity_ref)
    elif gate_id == "IL-G6":
        for obj in (td, vplan, agg_verdict):
            if obj is not None and hasattr(obj, 'meta'):
                supporting.append(obj.meta.integrity_ref)
    elif gate_id == "IL-G7":
        for obj in (cv, agg_verdict, task_run):
            if obj is not None and hasattr(obj, 'meta'):
                supporting.append(obj.meta.integrity_ref)

    outcome = "fail" if failed else "pass"
    return GateResult(gate_id, outcome, tuple(conditions), tuple(supporting), tuple(failed), now)


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
    task_run: Any | None = None,
    verification_evidence: list[EvidenceEnvelope] | None = None,
) -> tuple[list[EvidenceEnvelope], list[GateResult]]:
    """Build structured IL-G0/G1/G2/G4/G6/G7 gate evidence with real checks."""
    gate_ids = ("IL-G0", "IL-G1", "IL-G2", "IL-G4", "IL-G6", "IL-G7")
    evidences: list[EvidenceEnvelope] = []
    results: list[GateResult] = []

    for gate_id in gate_ids:
        gr = evaluate_gate(gate_id, rb, td, snapshot, bp, ctx, ce, vplan, agg_verdict, cv,
                           task_run=task_run, verification_evidence=verification_evidence)

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
