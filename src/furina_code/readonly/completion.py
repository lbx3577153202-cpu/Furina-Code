"""Furina Code readonly — CompletionVerdict creation."""

from __future__ import annotations

from ..contracts.objects import CompletionVerdict, VerificationVerdict


def create_completion_verdict(
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    task_run_ref: str,
    candidate_ref: str,
    verdicts: list[VerificationVerdict],
    envelope_id: str | None = None,
) -> CompletionVerdict:
    """Aggregate VerificationVerdicts into a CompletionVerdict."""
    completed: list[str] = []
    failed: list[str] = []

    for v in verdicts:
        for cond in v.checked_conditions:
            if cond in v.failed_conditions:
                failed.append(cond)
            else:
                completed.append(cond)

    if failed:
        outcome = "failed"
    elif completed:
        outcome = "completed"
    else:
        outcome = "partial"

    unverified: list[str] = []
    residual: list[str] = []
    if failed:
        residual.append(f"Failed conditions: {', '.join(failed)}")

    return CompletionVerdict.create(
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref=project_ref,
        correlation_id=correlation_id,
        task_run_ref=task_run_ref,
        candidate_ref=candidate_ref,
        outcome=outcome,
        completed_items=tuple(completed),
        incomplete_items=tuple(failed),
        unverified_items=tuple(unverified),
        residual_risks=tuple(residual),
        user_effect=(
            "No project files modified. No project tests run. "
            "Project code correctness not verified. "
            "Authorization Gate not implemented. "
            "Controlled write not implemented. "
            "RecoveryVerdict not implemented. "
            "No experience formed."
        ),
        envelope_id=envelope_id,
    )
