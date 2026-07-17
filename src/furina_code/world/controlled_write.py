"""E5's deliberately narrow, ticket-gated project write.

This module is not a shell runner and does not call a backend.  It is the
local enforcement boundary for one real, low-risk operation in an isolated
Git workspace: creating ``notes/welcome.txt`` exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, TYPE_CHECKING

from ..contracts import (
    ActionReceipt,
    AuthorizationDecision,
    AuthorizationTicket,
    BoundActionPlan,
    CompletionVerdict,
    ContractInvalid,
    EvidenceEnvelope,
    EnforcementVerdict,
    RealityReconciliation,
    TaskRun,
    VerificationPlan,
    VerificationVerdict,
)
from ..contracts.meta import now_utc
from ..contracts.objects import ProjectSnapshot

if TYPE_CHECKING:
    from ..ledger import Ledger


E5_POLICY_VERSION = "e5-single-file-create-v1"
E5_TARGET_PATH = "notes/welcome.txt"
E5_TARGET_SCOPE = "notes/"


@dataclass(frozen=True)
class ExecutionResult:
    enforcement: EnforcementVerdict
    receipt: ActionReceipt | None


@dataclass(frozen=True)
class VerificationResult:
    plan: VerificationPlan
    evidence: tuple[EvidenceEnvelope, ...]
    verdict: VerificationVerdict


@dataclass(frozen=True)
class CompletionResult:
    completion: CompletionVerdict


def _content_sha256(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _payload(obj: Any) -> dict[str, Any]:
    """Canonical payloads for the E5 formal objects written to the ledger."""
    if isinstance(obj, TaskRun):
        return {
            "task_revision": obj.task_revision, "phase": obj.phase.value,
            "disposition": obj.disposition.value,
            "current_refs": list(obj.current_refs),
            "open_requests": list(obj.open_requests),
            "started_at": obj.started_at.isoformat(), "terminal_reason": obj.terminal_reason,
        }
    if isinstance(obj, ProjectSnapshot):
        return {
            "observation_scope": obj.observation_scope, "git_ref": obj.git_ref,
            "file_facts": obj.file_facts, "environment_facts": obj.environment_facts,
            "blind_spots": list(obj.blind_spots), "observed_at": obj.observed_at.isoformat(),
            "freshness_policy": obj.freshness_policy, "head_sha": obj.head_sha,
            "branch": obj.branch, "status_lines": list(obj.status_lines),
            "tracked_count": obj.tracked_count, "untracked_count": obj.untracked_count,
            "is_clean": obj.is_clean, "pyproject_exists": obj.pyproject_exists,
            "pyproject_sha256": obj.pyproject_sha256,
            "requires_python": obj.requires_python,
            "runtime_deps": list(obj.runtime_deps), "dev_deps": list(obj.dev_deps),
            "pytest_testpaths": list(obj.pytest_testpaths),
            "ci_config_exists": obj.ci_config_exists,
            "ci_config_sha256": obj.ci_config_sha256,
            "snapshot_sha256": obj.snapshot_sha256,
        }
    if isinstance(obj, BoundActionPlan):
        return {
            "candidate_ref": obj.candidate_ref, "task_revision": obj.task_revision,
            "baseline_snapshot_ref": obj.baseline_snapshot_ref,
            "baseline_snapshot_sha256": obj.baseline_snapshot_sha256,
            "target_scope": list(obj.target_scope), "operations": list(obj.operations),
            "expected_diff": obj.expected_diff, "risk": obj.risk,
            "rollback_or_compensation": obj.rollback_or_compensation,
            "preconditions": list(obj.preconditions),
            "experience_match_ref": obj.experience_match_ref,
        }
    if isinstance(obj, AuthorizationDecision):
        return {
            "subject_ref": obj.subject_ref, "task_revision": obj.task_revision,
            "plan_ref": obj.plan_ref, "snapshot_ref": obj.snapshot_ref,
            "policy_version": obj.policy_version, "decision": obj.decision,
            "conditions": list(obj.conditions), "reason": obj.reason,
            "user_authority_refs": list(obj.user_authority_refs),
        }
    if isinstance(obj, AuthorizationTicket):
        return {
            "decision_ref": obj.decision_ref, "plan_ref": obj.plan_ref,
            "task_revision": obj.task_revision, "snapshot_ref": obj.snapshot_ref,
            "scope": list(obj.scope), "valid_from": obj.valid_from.isoformat(),
            "expires_at": obj.expires_at.isoformat(), "single_use": obj.single_use,
            "status": obj.status, "revocation_ref": obj.revocation_ref,
        }
    if isinstance(obj, EnforcementVerdict):
        return {
            "ticket_ref": obj.ticket_ref, "plan_ref": obj.plan_ref,
            "current_snapshot_ref": obj.current_snapshot_ref,
            "decision": obj.decision, "checked_at": obj.checked_at.isoformat(),
            "reason": obj.reason,
        }
    if isinstance(obj, ActionReceipt):
        return {
            "plan_ref": obj.plan_ref, "ticket_ref": obj.ticket_ref,
            "idempotency_key": obj.idempotency_key, "status": obj.status,
            "started_at": obj.started_at.isoformat(),
            "ended_at": obj.ended_at.isoformat() if obj.ended_at else None,
            "tool_ref": obj.tool_ref, "raw_result_ref": obj.raw_result_ref,
            "exit_info": obj.exit_info,
            "side_effect_assessment": obj.side_effect_assessment,
        }
    if isinstance(obj, RealityReconciliation):
        return {
            "plan_ref": obj.plan_ref, "receipt_ref": obj.receipt_ref,
            "before_snapshot_ref": obj.before_snapshot_ref,
            "after_snapshot_ref": obj.after_snapshot_ref,
            "expected_diff": obj.expected_diff, "actual_diff": obj.actual_diff,
            "unexpected_changes": list(obj.unexpected_changes), "verdict": obj.verdict,
        }
    if isinstance(obj, EvidenceEnvelope):
        return {
            "claim_scope": obj.claim_scope, "evidence_type": obj.evidence_type,
            "source_ref": obj.source_ref, "claim": obj.claim,
            "source_refs": list(obj.source_refs), "causal_links": list(obj.causal_links),
            "supporting_refs": list(obj.supporting_refs),
            "integrity_status": obj.integrity_status, "redactions": list(obj.redactions),
            "retention_class": obj.retention_class,
            "missing_evidence": list(obj.missing_evidence),
        }
    if isinstance(obj, VerificationPlan):
        return {
            "task_revision": obj.task_revision, "candidate_ref": obj.candidate_ref,
            "success_criteria_map": obj.success_criteria_map,
            "success_criteria": list(obj.success_criteria), "checks": list(obj.checks),
            "required_evidence": list(obj.required_evidence),
            "independence_requirements": list(obj.independence_requirements),
            "stop_conditions": list(obj.stop_conditions), "steps": list(obj.steps),
        }
    if isinstance(obj, VerificationVerdict):
        return {
            "plan_ref": obj.plan_ref, "evidence_refs": list(obj.evidence_refs),
            "criterion_results": obj.criterion_results, "coverage": obj.coverage,
            "failed_checks": list(obj.failed_checks), "unknowns": list(obj.unknowns),
            "outcome": obj.outcome, "reason": obj.reason,
            "checked_at": obj.checked_at.isoformat(),
        }
    if isinstance(obj, CompletionVerdict):
        return {
            "task_revision": obj.task_revision, "task_run_ref": obj.task_run_ref,
            "verification_ref": obj.verification_ref,
            "reconciliation_refs": list(obj.reconciliation_refs),
            "candidate_ref": obj.candidate_ref, "outcome": obj.outcome,
            "completed_items": list(obj.completed_items),
            "incomplete_items": list(obj.incomplete_items),
            "unverified_items": list(obj.unverified_items),
            "residual_risks": list(obj.residual_risks),
            "no_project_side_effect": obj.no_project_side_effect,
            "user_effect": obj.user_effect,
            "action_plan_ref": obj.action_plan_ref,
        }
    raise ContractInvalid(f"Unsupported E5 object: {type(obj).__name__}")


def write_e5_object(ledger: Ledger, obj: Any, expected_revision: int) -> None:
    """Use each object's owner as the only write entry for this E5 slice."""
    ledger.write_object(obj.meta, _payload(obj), obj.meta.owner_organ, expected_revision)


def _allowed_target_path(target_path: str) -> bool:
    path = Path(target_path)
    return (
        not path.is_absolute()
        and path.parent == Path("notes")
        and path.suffix == ".txt"
        and len(path.parts) == 2
    )


def bind_single_file_create(
    snapshot: ProjectSnapshot,
    candidate_ref: str,
    content: str,
    *,
    target_path: str = E5_TARGET_PATH,
    experience_match_ref: str | None = None,
) -> BoundActionPlan:
    """Bind the sole E5 operation to one observed project state."""
    if not snapshot.is_clean:
        raise ContractInvalid("E5 baseline must be clean")
    if not content:
        raise ContractInvalid("E5 content must not be empty")
    if not _allowed_target_path(target_path):
        raise ContractInvalid("E5 target must be one .txt file directly within notes/")
    return BoundActionPlan.create(
        run_binding_id=snapshot.meta.run_binding_id,
        task_id=snapshot.meta.task_id,
        task_run_id=snapshot.meta.task_run_id,
        project_ref=snapshot.meta.project_ref,
        correlation_id=snapshot.meta.correlation_id,
        candidate_ref=candidate_ref,
        task_revision=1,
        baseline_snapshot_ref=snapshot.meta.integrity_ref,
        baseline_snapshot_sha256=snapshot.snapshot_sha256,
        target_scope=(E5_TARGET_SCOPE,),
        operations=({"kind": "create_file", "path": target_path, "content": content},),
        expected_diff={"created_path": target_path, "content_sha256": _content_sha256(content)},
        risk="low",
        rollback_or_compensation="remove only the created target after a new authorization",
        preconditions=("baseline_clean", "target_absent"),
        experience_match_ref=experience_match_ref,
        causation_ref=snapshot.meta.integrity_ref,
    )


def evaluate_single_file_authorization(
    plan: BoundActionPlan,
    subject_ref: str,
    user_authority_refs: tuple[str, ...],
) -> AuthorizationDecision:
    """Apply the frozen E5 static policy; policy decision is not execution."""
    expected_operation = len(plan.operations) == 1 and plan.operations[0].get("kind") == "create_file"
    path_matches = expected_operation and _allowed_target_path(str(plan.operations[0].get("path", "")))
    scope_matches = plan.target_scope == (E5_TARGET_SCOPE,)
    content_matches = (expected_operation and
                       plan.expected_diff.get("content_sha256") == _content_sha256(plan.operations[0].get("content", "")))
    allowed = all((plan.risk == "low", expected_operation, path_matches, scope_matches,
                   content_matches, "target_absent" in plan.preconditions,
                   "baseline_clean" in plan.preconditions, bool(user_authority_refs)))
    reason = "E5 static policy permits one new notes file" if allowed else "E5 static policy denied the proposed action"
    return AuthorizationDecision.create(
        run_binding_id=plan.meta.run_binding_id, task_id=plan.meta.task_id,
        task_run_id=plan.meta.task_run_id, project_ref=plan.meta.project_ref,
        correlation_id=plan.meta.correlation_id, subject_ref=subject_ref,
        task_revision=plan.task_revision, plan_ref=plan.meta.integrity_ref,
        snapshot_ref=plan.baseline_snapshot_ref, policy_version=E5_POLICY_VERSION,
        decision="allow" if allowed else "deny",
        conditions=("single new file", "exact path", "fresh clean snapshot", "single-use ticket"),
        reason=reason, user_authority_refs=user_authority_refs,
        causation_ref=plan.meta.integrity_ref,
    )


def issue_single_file_ticket(
    decision: AuthorizationDecision,
    plan: BoundActionPlan,
    lifetime_seconds: int = 300,
) -> AuthorizationTicket:
    if decision.decision != "allow" or decision.plan_ref != plan.meta.integrity_ref:
        raise ContractInvalid("Only an allow decision bound to this plan may issue a ticket")
    if lifetime_seconds <= 0:
        raise ContractInvalid("Ticket lifetime must be positive")
    valid_from = now_utc()
    return AuthorizationTicket.create(
        run_binding_id=plan.meta.run_binding_id, task_id=plan.meta.task_id,
        task_run_id=plan.meta.task_run_id, project_ref=plan.meta.project_ref,
        correlation_id=plan.meta.correlation_id, decision_ref=decision.meta.integrity_ref,
        plan_ref=plan.meta.integrity_ref, task_revision=plan.task_revision,
        snapshot_ref=plan.baseline_snapshot_ref, scope=plan.target_scope,
        valid_from=valid_from, expires_at=valid_from + timedelta(seconds=lifetime_seconds),
        causation_ref=decision.meta.integrity_ref,
    )


def _ticket_is_current(ledger: Ledger, ticket: AuthorizationTicket) -> bool:
    return ledger.get_head_revision("AuthorizationTicket", ticket.meta.object_id) == ticket.meta.revision


def _idempotency_used(ledger: Ledger, key: str) -> bool:
    rows = ledger.conn.execute(
        "SELECT payload_json FROM object_revisions WHERE object_type='ActionReceipt'"
    ).fetchall()
    return any(json.loads(row[0]).get("idempotency_key") == key for row in rows)


def _inside_workspace(workspace: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ContractInvalid("E5 target path traversal rejected")
    target = (workspace / relative).resolve()
    try:
        target.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ContractInvalid("E5 target is outside workspace") from exc
    return target


def execute_single_file_create(
    ledger: Ledger,
    workspace: str,
    plan: BoundActionPlan,
    ticket: AuthorizationTicket | None,
    current_snapshot: ProjectSnapshot,
    idempotency_key: str,
    task_run: TaskRun,
) -> ExecutionResult:
    """Enforce, persist consumption/receipt, then perform the one safe write."""
    if ticket is None:
        raise ContractInvalid("AuthorizationTicket is required before any project write")
    now = now_utc()
    reasons: list[str] = []
    if ticket.status != "active" or not _ticket_is_current(ledger, ticket):
        reasons.append("ticket is not active at its current ledger revision")
    if not (ticket.plan_ref == plan.meta.integrity_ref and ticket.snapshot_ref == plan.baseline_snapshot_ref):
        reasons.append("ticket is not bound to this plan and baseline")
    if ticket.task_revision != plan.task_revision or ticket.scope != plan.target_scope:
        reasons.append("ticket task revision or scope differs from plan")
    if (task_run.phase.value, task_run.disposition.value) != ("act", "active"):
        reasons.append("TaskRun is not act/active")
    if task_run.task_revision != plan.task_revision:
        reasons.append("TaskRun task revision differs from plan")
    if not (ticket.valid_from <= now < ticket.expires_at):
        reasons.append("ticket is outside its validity interval")
    if current_snapshot.snapshot_sha256 != plan.baseline_snapshot_sha256 or not current_snapshot.is_clean:
        reasons.append("project snapshot drifted from the plan baseline")
    if _idempotency_used(ledger, idempotency_key):
        reasons.append("idempotency key was already used")

    allow = not reasons
    enforcement = EnforcementVerdict.create(
        run_binding_id=plan.meta.run_binding_id, task_id=plan.meta.task_id,
        task_run_id=plan.meta.task_run_id, project_ref=plan.meta.project_ref,
        correlation_id=plan.meta.correlation_id, ticket_ref=ticket.meta.integrity_ref,
        plan_ref=plan.meta.integrity_ref, current_snapshot_ref=current_snapshot.meta.integrity_ref,
        decision="allow" if allow else "deny",
        reason="all E5 enforcement checks passed" if allow else "; ".join(reasons),
        verdict_id=f"{plan.meta.task_id}:enforcement:{idempotency_key}:{now.timestamp()}",
        causation_ref=ticket.meta.integrity_ref,
    )
    write_e5_object(ledger, enforcement, 0)
    if not allow:
        return ExecutionResult(enforcement, None)

    consumed_ticket = ticket.consume()
    write_e5_object(ledger, consumed_ticket, ticket.meta.revision)
    receipt = ActionReceipt.create(
        run_binding_id=plan.meta.run_binding_id, task_id=plan.meta.task_id,
        task_run_id=plan.meta.task_run_id, project_ref=plan.meta.project_ref,
        correlation_id=plan.meta.correlation_id, plan_ref=plan.meta.integrity_ref,
        ticket_ref=consumed_ticket.meta.integrity_ref, idempotency_key=idempotency_key,
        tool_ref="e5-safe-file-create-v1", causation_ref=enforcement.meta.integrity_ref,
    )
    write_e5_object(ledger, receipt, 0)

    operation = plan.operations[0]
    target = _inside_workspace(Path(workspace), operation["path"])
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(operation["content"])
        completed = receipt.finish(
            "applied", _content_sha256(operation["content"]),
            {"operation": "create_file", "path": operation["path"]},
            "target created exactly once",
        )
    except Exception as exc:
        # The executor cannot prove that a failing file call had no side effect.
        # E6 will decide recovery; E5 never retries it automatically.
        completed = receipt.finish(
            "outcome_unknown", None,
            {"operation": "create_file", "error": type(exc).__name__},
            "write outcome unknown; automatic retry prohibited",
        )
    write_e5_object(ledger, completed, receipt.meta.revision)
    return ExecutionResult(enforcement, completed)


def reconcile_single_file_create(
    ledger: Ledger,
    workspace: str,
    plan: BoundActionPlan,
    receipt: ActionReceipt,
    before_snapshot: ProjectSnapshot,
    after_snapshot: ProjectSnapshot,
) -> RealityReconciliation:
    """Observe the actual filesystem/Git difference before any completion claim."""
    target_path = str(plan.operations[0].get("path", ""))
    target = _inside_workspace(Path(workspace), target_path)
    actual_hash = None
    if target.is_file():
        actual_hash = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
    try:
        listed = subprocess.run(
            ["git", "-C", str(workspace), "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, check=True, shell=False, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ContractInvalid("E5 could not inspect untracked files for reconciliation") from exc
    untracked_paths = tuple(line for line in listed.stdout.splitlines() if line)
    tracked_changes = tuple(line for line in after_snapshot.status_lines if not line.startswith("? "))
    unexpected = tuple((*tracked_changes, *(path for path in untracked_paths if path != target_path)))
    target_ok = actual_hash == plan.expected_diff.get("content_sha256")
    status_ok = untracked_paths == (target_path,) and not tracked_changes
    expected = receipt.status == "applied" and target_ok and status_ok and not unexpected
    actual_diff = {
        "target_exists": target.is_file(), "created_path": target_path if target.is_file() else None,
        "content_sha256": actual_hash, "git_status": list(after_snapshot.status_lines),
        "untracked_paths": list(untracked_paths),
    }
    reconciliation = RealityReconciliation.create(
        run_binding_id=plan.meta.run_binding_id, task_id=plan.meta.task_id,
        task_run_id=plan.meta.task_run_id, project_ref=plan.meta.project_ref,
        correlation_id=plan.meta.correlation_id, plan_ref=plan.meta.integrity_ref,
        receipt_ref=receipt.meta.integrity_ref,
        before_snapshot_ref=before_snapshot.meta.integrity_ref,
        after_snapshot_ref=after_snapshot.meta.integrity_ref,
        expected_diff=plan.expected_diff, actual_diff=actual_diff,
        unexpected_changes=unexpected,
        verdict="expected" if expected else ("unknown" if receipt.status == "outcome_unknown" else "divergent"),
        causation_ref=receipt.meta.integrity_ref,
    )
    write_e5_object(ledger, reconciliation, 0)
    return reconciliation


def verify_single_file_create(
    ledger: Ledger,
    plan: BoundActionPlan,
    reconciliation: RealityReconciliation,
    task_run: TaskRun,
) -> VerificationResult:
    """Turn reconciled project fact into evidence and an independent verdict.

    The caller must have advanced the task run to ``verify/active`` before this
    function.  This prevents the world/action owner from silently owning the
    task-run state machine as well.
    """
    if (task_run.phase.value, task_run.disposition.value) != ("verify", "active"):
        raise ContractInvalid("TaskRun must be verify/active before E5 verification")
    checks = (
        "target_content_exact",
        "scope_exact",
        "reconciliation_expected",
    )
    verification_plan = VerificationPlan.create(
        run_binding_id=plan.meta.run_binding_id, task_id=plan.meta.task_id,
        task_run_id=plan.meta.task_run_id, project_ref=plan.meta.project_ref,
        correlation_id=plan.meta.correlation_id, task_revision=plan.task_revision,
        candidate_ref=plan.candidate_ref,
        success_criteria_map={
            "target content exact": "target_content_exact",
            "only target path changed": "scope_exact",
            "reality reconciliation expected": "reconciliation_expected",
        },
        success_criteria=(
            "target content exact", "only target path changed",
            "reality reconciliation expected",
        ),
        checks=checks,
        required_evidence=(reconciliation.meta.integrity_ref,),
        stop_conditions=("outcome_unknown", "unexpected_changes"),
        causation_ref=reconciliation.meta.integrity_ref,
    )
    write_e5_object(ledger, verification_plan, 0)

    actual = reconciliation.actual_diff
    results = {
        "target_content_exact": actual.get("content_sha256") == plan.expected_diff.get("content_sha256"),
        "scope_exact": (
            not reconciliation.unexpected_changes
            and actual.get("untracked_paths") == [plan.expected_diff["created_path"]]
        ),
        "reconciliation_expected": reconciliation.verdict == "expected",
    }
    evidence: list[EvidenceEnvelope] = []
    for check in checks:
        passed = results[check]
        item = EvidenceEnvelope.create(
            run_binding_id=plan.meta.run_binding_id, task_id=plan.meta.task_id,
            task_run_id=plan.meta.task_run_id, project_ref=plan.meta.project_ref,
            correlation_id=plan.meta.correlation_id,
            claim_scope=f"e5-verification:{check}", evidence_type="reconciliation_check",
            source_ref=reconciliation.meta.integrity_ref,
            claim=f"{check}={'pass' if passed else 'fail'}",
            source_refs=(reconciliation.meta.integrity_ref,),
            causal_links=(verification_plan.meta.integrity_ref,),
            supporting_refs=(plan.meta.integrity_ref,),
            integrity_status="verified" if passed else "failed",
            envelope_id=f"{plan.meta.task_id}:e5-evidence:{check}",
            causation_ref=verification_plan.meta.integrity_ref,
        )
        write_e5_object(ledger, item, 0)
        evidence.append(item)

    failed = tuple(check for check in checks if not results[check])
    verification = VerificationVerdict.create(
        run_binding_id=plan.meta.run_binding_id, task_id=plan.meta.task_id,
        task_run_id=plan.meta.task_run_id, project_ref=plan.meta.project_ref,
        correlation_id=plan.meta.correlation_id,
        plan_ref=verification_plan.meta.integrity_ref,
        evidence_refs=tuple(item.meta.integrity_ref for item in evidence),
        criterion_results={check: "pass" if results[check] else "fail" for check in checks},
        coverage=sum(results.values()) / len(checks), failed_checks=failed,
        outcome="pass" if not failed else "fail",
        reason="all E5 declared checks passed" if not failed else "E5 verification checks failed",
        causation_ref=verification_plan.meta.integrity_ref,
    )
    write_e5_object(ledger, verification, 0)

    return VerificationResult(verification_plan, tuple(evidence), verification)


def adjudicate_single_file_completion(
    ledger: Ledger,
    plan: BoundActionPlan,
    reconciliation: RealityReconciliation,
    verification: VerificationVerdict,
    task_run: TaskRun,
) -> CompletionResult:
    """Make the completion claim only from adjudicate/active, never verify/active."""
    if (task_run.phase.value, task_run.disposition.value) != ("adjudicate", "active"):
        raise ContractInvalid("TaskRun must be adjudicate/active before E5 completion")
    if verification.plan_ref == "" or verification.meta.task_id != plan.meta.task_id:
        raise ContractInvalid("VerificationVerdict is not bound to this controlled-write task")
    completion = CompletionVerdict.create(
        run_binding_id=plan.meta.run_binding_id, task_id=plan.meta.task_id,
        task_run_id=plan.meta.task_run_id, project_ref=plan.meta.project_ref,
        correlation_id=plan.meta.correlation_id, task_revision=plan.task_revision,
        task_run_ref=task_run.meta.integrity_ref,
        verification_ref=verification.meta.integrity_ref,
        reconciliation_refs=(reconciliation.meta.integrity_ref,),
        candidate_ref=plan.candidate_ref,
        outcome="completed" if verification.outcome == "pass" else "not_completed",
        completed_items=(f"created {plan.expected_diff['created_path']}", "verified exact content", "verified scope")
        if verification.outcome == "pass" else (),
        incomplete_items=verification.failed_checks,
        residual_risks=("recovery and experience are outside E5",),
        no_project_side_effect=False,
        user_effect=f"created {plan.expected_diff['created_path']}" if verification.outcome == "pass" else "no completion claim",
        action_plan_ref=plan.meta.integrity_ref,
        causation_ref=verification.meta.integrity_ref,
    )
    write_e5_object(ledger, completion, 0)
    return CompletionResult(completion)
