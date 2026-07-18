"""B2: Mid-task user correction service.

Atomically invalidates old plan/ticket authority when a user changes direction.
Uses ledger.write_objects_atomic() for all-or-nothing correction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from ..contracts import (
    AuthorizationTicket,
    BoundActionPlan,
    ContractInvalid,
    Disposition,
    TaskDossier,
    TaskRun,
)

if TYPE_CHECKING:
    from ..ledger import Ledger


@dataclass(frozen=True)
class CorrectionResult:
    """Result of a user correction that invalidates old authority."""
    original_plan_ref: str
    original_ticket_ref: str
    corrected_dossier_ref: str
    revoked_ticket_ref: str
    paused_run_ref: str
    correction_fact_ref: str


def _payload(obj: Any) -> dict[str, Any]:
    """Extract payload from formal object."""
    if isinstance(obj, TaskDossier):
        return {
            "source_intent_ref": obj.source_intent_ref,
            "structured_goal": obj.structured_goal,
            "success_criteria": list(obj.success_criteria),
            "scope": list(obj.scope), "exclusions": list(obj.exclusions),
            "unknowns": list(obj.unknowns), "risk_class": obj.risk_class,
            "user_constraints": list(obj.user_constraints),
            "status": obj.status.value,
        }
    if isinstance(obj, TaskRun):
        return {
            "task_revision": obj.task_revision, "phase": obj.phase.value,
            "disposition": obj.disposition.value,
            "current_refs": list(obj.current_refs),
            "open_requests": list(obj.open_requests),
            "started_at": obj.started_at.isoformat(), "terminal_reason": obj.terminal_reason,
        }
    if isinstance(obj, AuthorizationTicket):
        return {
            "decision_ref": obj.decision_ref, "plan_ref": obj.plan_ref,
            "task_revision": obj.task_revision, "snapshot_ref": obj.snapshot_ref,
            "scope": list(obj.scope), "valid_from": obj.valid_from.isoformat(),
            "expires_at": obj.expires_at.isoformat(), "single_use": obj.single_use,
            "status": obj.status, "revocation_ref": obj.revocation_ref,
        }
    raise ContractInvalid(f"Unsupported correction object: {type(obj).__name__}")


def apply_user_correction(
    ledger: Ledger,
    run: TaskRun,
    plan: BoundActionPlan,
    ticket: AuthorizationTicket,
    *,
    new_structured_goal: str,
    new_success_criteria: tuple[str, ...],
    new_scope: tuple[str, ...],
    new_exclusions: tuple[str, ...],
    new_unknowns: tuple[str, ...],
    new_risk_class: str,
    new_user_constraints: tuple[str, ...],
    correction_source_ref: str,
) -> CorrectionResult:
    """Atomically apply user correction with full binding validation.

    All objects are written in a single ledger transaction. If any
    write fails, none are persisted.
    """
    from ..world.controlled_write import write_e5_object

    # 1. Validate binding consistency
    if run.meta.run_binding_id != plan.meta.run_binding_id:
        raise ContractInvalid("Run and plan must belong to the same binding")
    if run.meta.run_binding_id != ticket.meta.run_binding_id:
        raise ContractInvalid("Run and ticket must belong to the same binding")
    if run.meta.task_id != plan.meta.task_id:
        raise ContractInvalid("Run and plan must belong to the same task")
    if run.meta.task_id != ticket.meta.task_id:
        raise ContractInvalid("Run and ticket must belong to the same task")
    if plan.meta.integrity_ref != ticket.plan_ref:
        raise ContractInvalid("Ticket must reference the plan being corrected")

    # 2. Find and revise the TaskDossier
    dossier_result = ledger.get_latest("TaskDossier", run.meta.task_id)
    if dossier_result is None:
        raise ContractInvalid("No TaskDossier found for this task")
    dossier_meta, dossier_payload = dossier_result

    old_dossier = TaskDossier.create(
        run_binding_id=dossier_meta.run_binding_id,
        task_id=dossier_meta.task_id,
        task_run_id=dossier_meta.task_run_id,
        project_ref=dossier_meta.project_ref,
        correlation_id=dossier_meta.correlation_id,
        source_intent_ref=dossier_payload.get("source_intent_ref", ""),
        structured_goal=dossier_payload.get("structured_goal", ""),
        success_criteria=tuple(dossier_payload.get("success_criteria", [])),
        scope=tuple(dossier_payload.get("scope", [])),
        exclusions=tuple(dossier_payload.get("exclusions", [])),
        unknowns=tuple(dossier_payload.get("unknowns", [])),
        risk_class=dossier_payload.get("risk_class", "low"),
        user_constraints=tuple(dossier_payload.get("user_constraints", [])),
    )

    new_dossier = old_dossier.revise(
        structured_goal=new_structured_goal,
        success_criteria=new_success_criteria,
        scope=new_scope,
        exclusions=new_exclusions,
        unknowns=new_unknowns,
        risk_class=new_risk_class,
        user_constraints=new_user_constraints,
        source_intent_ref=correction_source_ref,
    )

    # 3. Create revoked ticket (new revision with consumed status)
    revoked_ticket = ticket.consume()

    # 4. Create paused TaskRun
    if run.disposition == Disposition.ACTIVE:
        paused_run = run.transition(
            "I2-D", run.phase, Disposition.WAITING_USER,
            current_refs=(
                plan.meta.integrity_ref,
                ticket.meta.integrity_ref,
                new_dossier.meta.integrity_ref,
            ),
        )
    else:
        paused_run = run

    # 5. Write ALL objects atomically in one transaction
    objects_to_write = [
        (new_dossier.meta, _payload(new_dossier), new_dossier.meta.owner_organ, old_dossier.meta.revision),
        (revoked_ticket.meta, _payload(revoked_ticket), revoked_ticket.meta.owner_organ, ticket.meta.revision),
    ]
    if run.disposition == Disposition.ACTIVE:
        objects_to_write.append(
            (paused_run.meta, _payload(paused_run), paused_run.meta.owner_organ, run.meta.revision),
        )

    ledger.write_objects_atomic(objects_to_write)

    return CorrectionResult(
        original_plan_ref=plan.meta.integrity_ref,
        original_ticket_ref=ticket.meta.integrity_ref,
        corrected_dossier_ref=new_dossier.meta.integrity_ref,
        revoked_ticket_ref=revoked_ticket.meta.integrity_ref,
        paused_run_ref=paused_run.meta.integrity_ref,
        correction_fact_ref=new_dossier.meta.integrity_ref,
    )
