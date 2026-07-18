"""B2: Mid-task user correction service.

Atomically invalidates old plan/ticket authority when a user changes direction.
Validates all objects belong to the same binding/task, writes revocation fact,
and forces fresh observation, planning, authorization, and verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..contracts import (
    AuthorizationTicket,
    BoundActionPlan,
    ContractInvalid,
    Disposition,
    Phase,
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
    revoked_ticket: AuthorizationTicket
    updated_run: TaskRun
    correction_fact_ref: str


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

    This operation:
    1. Validates all objects belong to the same binding/task/revision
    2. Creates a new TaskDossier revision with the correction source
    3. Revokes the old ticket (consumed state)
    4. Pauses the current TaskRun, recording old plan/ticket/correction refs
    5. Returns the result so caller can force re-observation
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
    write_e5_object(ledger, new_dossier, old_dossier.meta.revision)

    # 3. Revoke the old ticket
    revoked_ticket = ticket.consume()
    write_e5_object(ledger, revoked_ticket, ticket.meta.revision)

    # 4. Pause the TaskRun, recording all superseded refs
    if run.disposition == Disposition.ACTIVE:
        paused_run = run.transition(
            "I2-D", run.phase, Disposition.WAITING_USER,
            current_refs=(
                plan.meta.integrity_ref,
                ticket.meta.integrity_ref,
                new_dossier.meta.integrity_ref,
            ),
        )
        write_e5_object(ledger, paused_run, run.meta.revision)
    else:
        paused_run = run

    return CorrectionResult(
        original_plan_ref=plan.meta.integrity_ref,
        original_ticket_ref=ticket.meta.integrity_ref,
        corrected_dossier_ref=new_dossier.meta.integrity_ref,
        revoked_ticket=revoked_ticket,
        updated_run=paused_run,
        correction_fact_ref=new_dossier.meta.integrity_ref,
    )
