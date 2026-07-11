"""Furina Code readonly — CompletionVerdict creation."""

from __future__ import annotations

from ..contracts.objects import CompletionVerdict, VerificationVerdict


def create_completion_verdict(
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    task_revision: int,
    task_run_ref: str,
    verification_ref: str,
    candidate_ref: str,
    outcome: str,
    completed_items: tuple[str, ...] = (),
    incomplete_items: tuple[str, ...] = (),
    unverified_items: tuple[str, ...] = (),
    residual_risks: tuple[str, ...] = (),
    no_project_side_effect: bool = True,
    user_effect: str = "",
    reconciliation_refs: tuple[str, ...] = (),
    envelope_id: str | None = None,
    causation_ref: str | None = None,
) -> CompletionVerdict:
    return CompletionVerdict.create(
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref=project_ref,
        correlation_id=correlation_id,
        task_revision=task_revision,
        task_run_ref=task_run_ref,
        verification_ref=verification_ref,
        candidate_ref=candidate_ref,
        outcome=outcome,
        completed_items=completed_items,
        incomplete_items=incomplete_items,
        unverified_items=unverified_items,
        residual_risks=residual_risks,
        no_project_side_effect=no_project_side_effect,
        user_effect=user_effect,
        reconciliation_refs=reconciliation_refs,
        envelope_id=envelope_id,
        causation_ref=causation_ref,
    )
