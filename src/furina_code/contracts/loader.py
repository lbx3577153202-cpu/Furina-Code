"""Deserialize formal objects from ledger data, preserving original CanonicalMeta.

Unlike .create() which computes new integrity_refs with fresh timestamps,
these loaders reconstruct objects from stored meta_json + payload_json,
preserving the original integrity_ref, created_at, and all identity fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING

from ..contracts import (
    ActionReceipt,
    AuthorizationTicket,
    BoundActionPlan,
    Checkpoint,
    CompletionVerdict,
    Disposition,
    EnforcementVerdict,
    Phase,
    TaskRun,
    VerificationVerdict,
)
from ..contracts.meta import CanonicalMeta
from ..contracts.objects import ProjectSnapshot

if TYPE_CHECKING:
    from ..ledger import Ledger


def _load_meta(meta_json: str) -> CanonicalMeta:
    """Reconstruct CanonicalMeta from stored JSON, preserving integrity_ref."""
    d = __import__("json").loads(meta_json)
    return CanonicalMeta(
        schema_version=d["schema_version"],
        object_type=d["object_type"],
        object_id=d["object_id"],
        revision=d["revision"],
        owner_organ=d["owner_organ"],
        run_binding_id=d["run_binding_id"],
        task_id=d["task_id"],
        task_run_id=d["task_run_id"],
        project_ref=d["project_ref"],
        correlation_id=d["correlation_id"],
        causation_ref=d.get("causation_ref"),
        created_at=datetime.fromisoformat(d["created_at"]),
        recorded_at=datetime.fromisoformat(d["recorded_at"]),
        classification=d["classification"],
        integrity_ref=d["integrity_ref"],
        supersedes_ref=d.get("supersedes_ref"),
    )


def load_bound_action_plan(ledger: Ledger, object_id: str) -> BoundActionPlan:
    """Load a BoundActionPlan from ledger, preserving original integrity_ref."""
    meta, payload = ledger.get_latest("BoundActionPlan", object_id)
    return BoundActionPlan(
        meta=meta,
        candidate_ref=payload["candidate_ref"],
        task_revision=payload["task_revision"],
        baseline_snapshot_ref=payload["baseline_snapshot_ref"],
        baseline_snapshot_sha256=payload["baseline_snapshot_sha256"],
        target_scope=tuple(payload["target_scope"]),
        operations=tuple(payload["operations"]),
        expected_diff=payload["expected_diff"],
        risk=payload["risk"],
        rollback_or_compensation=payload["rollback_or_compensation"],
        preconditions=tuple(payload["preconditions"]),
        experience_match_ref=payload.get("experience_match_ref"),
    )


def load_authorization_ticket(ledger: Ledger, object_id: str) -> AuthorizationTicket:
    """Load an AuthorizationTicket from ledger, preserving original integrity_ref."""
    meta, payload = ledger.get_latest("AuthorizationTicket", object_id)
    return AuthorizationTicket(
        meta=meta,
        decision_ref=payload["decision_ref"],
        plan_ref=payload["plan_ref"],
        task_revision=payload["task_revision"],
        snapshot_ref=payload["snapshot_ref"],
        scope=tuple(payload["scope"]),
        valid_from=datetime.fromisoformat(payload["valid_from"]),
        expires_at=datetime.fromisoformat(payload["expires_at"]),
        single_use=payload.get("single_use", True),
        status=payload["status"],
        revocation_ref=payload.get("revocation_ref"),
    )


def load_action_receipt(ledger: Ledger, object_id: str) -> ActionReceipt:
    """Load an ActionReceipt from ledger, preserving original integrity_ref."""
    meta, payload = ledger.get_latest("ActionReceipt", object_id)
    return ActionReceipt(
        meta=meta,
        plan_ref=payload["plan_ref"],
        ticket_ref=payload["ticket_ref"],
        idempotency_key=payload["idempotency_key"],
        status=payload["status"],
        started_at=datetime.fromisoformat(payload["started_at"]),
        ended_at=datetime.fromisoformat(payload["ended_at"]) if payload.get("ended_at") else None,
        tool_ref=payload["tool_ref"],
        raw_result_ref=payload.get("raw_result_ref"),
        exit_info=payload.get("exit_info", {}),
        side_effect_assessment=payload.get("side_effect_assessment", ""),
    )


def load_enforcement_verdict(ledger: Ledger, object_id: str) -> EnforcementVerdict:
    """Load an EnforcementVerdict from ledger, preserving original integrity_ref."""
    meta, payload = ledger.get_latest("EnforcementVerdict", object_id)
    return EnforcementVerdict(
        meta=meta,
        ticket_ref=payload["ticket_ref"],
        plan_ref=payload["plan_ref"],
        current_snapshot_ref=payload["current_snapshot_ref"],
        decision=payload["decision"],
        checked_at=datetime.fromisoformat(payload["checked_at"]),
        reason=payload["reason"],
    )


def load_verification_verdict(ledger: Ledger, object_id: str) -> VerificationVerdict:
    """Load a VerificationVerdict from ledger, preserving original integrity_ref."""
    meta, payload = ledger.get_latest("VerificationVerdict", object_id)
    return VerificationVerdict(
        meta=meta,
        plan_ref=payload.get("plan_ref", ""),
        evidence_refs=tuple(payload.get("evidence_refs", [])),
        criterion_results=payload.get("criterion_results", {}),
        coverage=payload.get("coverage", 0.0),
        failed_checks=tuple(payload.get("failed_checks", [])),
        unknowns=tuple(payload.get("unknowns", [])),
        outcome=payload.get("outcome", ""),
        reason=payload.get("reason", ""),
        checked_at=datetime.fromisoformat(payload["checked_at"]) if payload.get("checked_at") else meta.created_at,
    )


def load_completion_verdict(ledger: Ledger, object_id: str) -> CompletionVerdict:
    """Load a CompletionVerdict from ledger, preserving original integrity_ref."""
    meta, payload = ledger.get_latest("CompletionVerdict", object_id)
    return CompletionVerdict(
        meta=meta,
        task_revision=payload.get("task_revision", 1),
        task_run_ref=payload.get("task_run_ref", ""),
        verification_ref=payload.get("verification_ref", ""),
        reconciliation_refs=tuple(payload.get("reconciliation_refs", [])),
        candidate_ref=payload.get("candidate_ref", ""),
        outcome=payload.get("outcome", ""),
        completed_items=tuple(payload.get("completed_items", [])),
        incomplete_items=tuple(payload.get("incomplete_items", [])),
        unverified_items=tuple(payload.get("unverified_items", [])),
        residual_risks=tuple(payload.get("residual_risks", [])),
        no_project_side_effect=payload.get("no_project_side_effect", True),
        user_effect=payload.get("user_effect", ""),
        action_plan_ref=payload.get("action_plan_ref"),
    )


def load_checkpoint(ledger: Ledger, object_id: str) -> Checkpoint:
    """Load a Checkpoint from ledger, preserving original integrity_ref."""
    meta, payload = ledger.get_latest("Checkpoint", object_id)
    return Checkpoint(
        meta=meta,
        task_revision=payload["task_revision"],
        phase=Phase(payload["phase"]),
        disposition=Disposition(payload["disposition"]),
        event_cursor=payload["event_cursor"],
        pending_requests=tuple(payload.get("pending_requests", [])),
        pending_actions=tuple(payload.get("pending_actions", [])),
        snapshot_ref=payload.get("snapshot_ref"),
        ticket_refs=tuple(payload.get("ticket_refs", [])),
        reason=payload.get("reason", ""),
    )


def load_task_run(ledger: Ledger, object_id: str) -> TaskRun:
    """Load a TaskRun from ledger, preserving original phase/disposition/integrity_ref."""
    meta, payload = ledger.get_latest("TaskRun", object_id)
    return TaskRun(
        meta=meta,
        task_revision=payload["task_revision"],
        phase=Phase(payload["phase"]),
        disposition=Disposition(payload["disposition"]),
        current_refs=tuple(payload.get("current_refs", [])),
        open_requests=tuple(payload.get("open_requests", [])),
        started_at=datetime.fromisoformat(payload["started_at"]),
        terminal_reason=payload.get("terminal_reason"),
    )


def load_project_snapshot(ledger: Ledger, object_id: str) -> ProjectSnapshot:
    """Load a ProjectSnapshot from ledger, preserving original integrity_ref."""
    meta, payload = ledger.get_latest("ProjectSnapshot", object_id)
    return ProjectSnapshot(
        meta=meta,
        observation_scope=payload.get("observation_scope", ""),
        git_ref=payload.get("git_ref", {}),
        file_facts=payload.get("file_facts", {}),
        environment_facts=payload.get("environment_facts", {}),
        blind_spots=tuple(payload.get("blind_spots", [])),
        observed_at=datetime.fromisoformat(payload["observed_at"]) if payload.get("observed_at") else meta.created_at,
        freshness_policy=payload.get("freshness_policy", ""),
        head_sha=payload.get("head_sha", ""),
        branch=payload.get("branch", ""),
        status_lines=tuple(payload.get("status_lines", [])),
        tracked_count=payload.get("tracked_count", 0),
        untracked_count=payload.get("untracked_count", 0),
        is_clean=payload.get("is_clean", True),
        pyproject_exists=payload.get("pyproject_exists", False),
        pyproject_sha256=payload.get("pyproject_sha256"),
        requires_python=payload.get("requires_python"),
        runtime_deps=tuple(payload.get("runtime_deps", [])),
        dev_deps=tuple(payload.get("dev_deps", [])),
        pytest_testpaths=tuple(payload.get("pytest_testpaths", [])),
        ci_config_exists=payload.get("ci_config_exists", False),
        ci_config_sha256=payload.get("ci_config_sha256"),
        snapshot_sha256=payload.get("snapshot_sha256", ""),
    )
