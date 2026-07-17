"""E6 interruption review for the single controlled-write slice.

Recovery reviews observed facts and writes a verdict.  It never invokes the
project writer, so an uncertain side effect cannot be replayed by accident.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, TYPE_CHECKING

from ..contracts import (
    ActionReceipt,
    BoundActionPlan,
    Checkpoint,
    ContractInvalid,
    Phase,
    RecoveryVerdict,
)
from ..contracts.objects import ProjectSnapshot

if TYPE_CHECKING:
    from ..ledger import Ledger


def _payload(obj: Any) -> dict[str, Any]:
    if isinstance(obj, Checkpoint):
        return {
            "task_revision": obj.task_revision, "phase": obj.phase.value,
            "disposition": obj.disposition.value, "event_cursor": obj.event_cursor,
            "pending_requests": list(obj.pending_requests),
            "pending_actions": list(obj.pending_actions), "snapshot_ref": obj.snapshot_ref,
            "ticket_refs": list(obj.ticket_refs), "reason": obj.reason,
        }
    if isinstance(obj, RecoveryVerdict):
        return {
            "checkpoint_ref": obj.checkpoint_ref,
            "fresh_snapshot_refs": list(obj.fresh_snapshot_refs),
            "receipt_refs": list(obj.receipt_refs), "ticket_review": obj.ticket_review,
            "outcome": obj.outcome,
            "resume_phase": obj.resume_phase.value if obj.resume_phase else None,
            "required_steps": list(obj.required_steps), "reason": obj.reason,
        }
    raise ContractInvalid(f"Unsupported recovery object: {type(obj).__name__}")


def write_recovery_object(ledger: Ledger, obj: Any, expected_revision: int) -> None:
    ledger.write_object(obj.meta, _payload(obj), obj.meta.owner_organ, expected_revision)


def _expected_content_present(workspace: str, plan: BoundActionPlan) -> bool:
    if len(plan.operations) != 1:
        return False
    operation = plan.operations[0]
    relative = Path(str(operation.get("path", "")))
    if relative.is_absolute() or ".." in relative.parts:
        return False
    root = Path(workspace).resolve()
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return False
    if not target.is_file():
        return False
    digest = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
    return digest == plan.expected_diff.get("content_sha256")


def review_interrupted_write(
    ledger: Ledger,
    workspace: str,
    checkpoint: Checkpoint,
    plan: BoundActionPlan,
    fresh_snapshot: ProjectSnapshot,
    receipt: ActionReceipt | None,
    ticket_status: str,
) -> RecoveryVerdict:
    """Produce a recovery decision from fresh observation, without replaying."""
    if checkpoint.snapshot_ref != plan.baseline_snapshot_ref:
        raise ContractInvalid("Checkpoint is not bound to the action plan baseline")
    if fresh_snapshot.meta.run_binding_id != plan.meta.run_binding_id:
        raise ContractInvalid("Fresh snapshot binding differs from action plan")

    target_present = _expected_content_present(workspace, plan)
    receipt_refs = (receipt.meta.integrity_ref,) if receipt else ()
    if receipt is None:
        valid = (
            ticket_status == "active"
            and fresh_snapshot.snapshot_sha256 == plan.baseline_snapshot_sha256
            and fresh_snapshot.is_clean
        )
        outcome = "continue_no_replay" if valid else "pause"
        resume_phase = Phase.ACT if valid else Phase.RECONCILE
        required = ("re-run enforcement immediately before action",) if valid else (
            "obtain a new snapshot and authorization before any action",)
        reason = "No receipt exists; ticket and baseline remain valid" if valid else (
            "No receipt exists but ticket or project baseline is no longer valid")
        ticket_review = "active_and_fresh" if valid else "invalid_or_drifted"
    elif receipt.status == "applied" or target_present:
        outcome = "skip_confirmed_action"
        resume_phase = Phase.RECONCILE
        required = ("do not execute action again", "reconcile and verify observed project state")
        reason = "Observed target proves the action already occurred"
        ticket_review = "consumed_or_no_longer_actionable"
    elif receipt.status in {"executing", "outcome_unknown"}:
        outcome = "pause"
        resume_phase = Phase.RECONCILE
        required = (
            "do not retry automatically", "preserve receipt", "obtain explicit recovery review",
        )
        reason = "Action outcome remains unknown after fresh observation"
        ticket_review = "consumed; cannot be reused"
    else:
        outcome = "pause"
        resume_phase = Phase.RECONCILE
        required = ("obtain a new authorization before any new action",)
        reason = "No confirmed applied action is available to resume"
        ticket_review = "requires new authorization"

    verdict = RecoveryVerdict.create(
        run_binding_id=plan.meta.run_binding_id, task_id=plan.meta.task_id,
        task_run_id=plan.meta.task_run_id, project_ref=plan.meta.project_ref,
        correlation_id=plan.meta.correlation_id,
        checkpoint_ref=checkpoint.meta.integrity_ref,
        fresh_snapshot_refs=(fresh_snapshot.meta.integrity_ref,),
        receipt_refs=receipt_refs, ticket_review=ticket_review,
        outcome=outcome, resume_phase=resume_phase, required_steps=required,
        reason=reason, causation_ref=checkpoint.meta.integrity_ref,
    )
    write_recovery_object(ledger, verdict, 0)
    return verdict
