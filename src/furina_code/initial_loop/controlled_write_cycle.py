"""One auditable G3–G7 controlled-write cycle.

This is orchestration, not a backend adapter: it coordinates existing Furina
Code contracts and local world boundaries.  It deliberately has no model,
network or MiMo invocation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..contracts import (
    AuthorizationDecision, AuthorizationTicket, BoundActionPlan, CompletionVerdict,
    Disposition, Phase, ProjectSnapshot, RealityReconciliation, TaskRun,
    VerificationVerdict,
)
from ..world import create_project_snapshot
from ..world.controlled_write import (
    adjudicate_single_file_completion,
    bind_single_file_create,
    evaluate_single_file_authorization,
    execute_single_file_create,
    issue_single_file_ticket,
    reconcile_single_file_create,
    verify_single_file_create,
    write_e5_object,
)

if TYPE_CHECKING:
    from ..ledger import Ledger


@dataclass(frozen=True)
class ControlledWriteCycle:
    task_run: TaskRun
    before_snapshot: ProjectSnapshot
    plan: BoundActionPlan
    decision: AuthorizationDecision
    ticket: AuthorizationTicket
    reconciliation: RealityReconciliation
    verification: VerificationVerdict
    completion: CompletionVerdict


def _advance(ledger: Ledger, run: TaskRun, phase: Phase, refs: tuple[str, ...]) -> TaskRun:
    next_run = run.transition("I2-D", phase, Disposition.ACTIVE, current_refs=refs)
    write_e5_object(ledger, next_run, run.meta.revision)
    return next_run


def run_controlled_write_cycle(
    ledger: Ledger,
    workspace: str,
    *,
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    candidate_ref: str,
    user_authority_refs: tuple[str, ...],
    content: str,
    target_path: str,
    experience_match_ref: str | None = None,
    task_revision: int = 1,
    task_dossier_ref: str | None = None,
) -> ControlledWriteCycle:
    """Execute one low-risk file creation through observe→terminal.

    Callers must provide explicit user authority.  Every formal object and each
    TaskRun transition is persisted before moving to the next stage.
    """
    run = TaskRun.create(
        run_binding_id, task_id, task_run_id, project_ref, correlation_id,
        task_revision, causation_ref=task_dossier_ref,
    )
    write_e5_object(ledger, run, 0)
    run = _advance(ledger, run, Phase.OBSERVE, ())
    before = create_project_snapshot(
        run_binding_id, task_id, task_run_id, project_ref, correlation_id, workspace,
        snapshot_id=f"{task_id}:snapshot:before", causation_ref=run.meta.integrity_ref,
    )
    write_e5_object(ledger, before, 0)
    run = _advance(ledger, run, Phase.DELIBERATE, (before.meta.integrity_ref,))
    plan = bind_single_file_create(
        before, candidate_ref, content, target_path=target_path,
        experience_match_ref=experience_match_ref, task_revision=task_revision,
    )
    write_e5_object(ledger, plan, 0)
    run = _advance(ledger, run, Phase.AUTHORIZE, (plan.meta.integrity_ref,))
    decision = evaluate_single_file_authorization(plan, "user", user_authority_refs)
    write_e5_object(ledger, decision, 0)
    ticket = issue_single_file_ticket(decision, plan)
    write_e5_object(ledger, ticket, 0)
    run = _advance(ledger, run, Phase.ACT, (ticket.meta.integrity_ref,))
    # Fresh reality snapshot immediately before execution: the executor must
    # enforce against the *current* project state, not the observe-time baseline.
    act_time = create_project_snapshot(
        run_binding_id, task_id, task_run_id, project_ref, correlation_id, workspace,
        snapshot_id=f"{task_id}:snapshot:act-time",
        causation_ref=ticket.meta.integrity_ref,
    )
    write_e5_object(ledger, act_time, 0)
    execution = execute_single_file_create(
        ledger, workspace, plan, ticket, act_time, f"{task_id}:create:{target_path}", run,
    )
    if execution.receipt is None:
        raise RuntimeError(f"Controlled write was denied: {execution.enforcement.reason}")
    after = create_project_snapshot(
        run_binding_id, task_id, task_run_id, project_ref, correlation_id, workspace,
        snapshot_id=f"{task_id}:snapshot:after", causation_ref=execution.receipt.meta.integrity_ref,
    )
    write_e5_object(ledger, after, 0)
    run = _advance(ledger, run, Phase.RECONCILE, (execution.receipt.meta.integrity_ref, after.meta.integrity_ref))
    reconciliation = reconcile_single_file_create(ledger, workspace, plan, execution.receipt, before, after)
    run = _advance(ledger, run, Phase.VERIFY, (reconciliation.meta.integrity_ref,))
    verification_result = verify_single_file_create(ledger, plan, reconciliation, run)
    run = _advance(ledger, run, Phase.ADJUDICATE, (verification_result.verdict.meta.integrity_ref,))
    completion_result = adjudicate_single_file_completion(
        ledger, plan, reconciliation, verification_result.verdict, run,
    )
    run = run.transition(
        "I2-D", Phase.TERMINAL, Disposition.TERMINAL,
        current_refs=(completion_result.completion.meta.integrity_ref,),
        terminal_reason=completion_result.completion.outcome,
    )
    write_e5_object(ledger, run, run.meta.revision - 1)
    return ControlledWriteCycle(
        task_run=run, before_snapshot=before, plan=plan, decision=decision, ticket=ticket,
        reconciliation=reconciliation, verification=verification_result.verdict,
        completion=completion_result.completion,
    )
