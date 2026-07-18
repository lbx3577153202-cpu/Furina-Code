"""B6: Second task determined only after first completion.

The second task's path/content must not be created before the first task
starts. Experience from the first task must change the second plan without
becoming an authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..contracts import BoundActionPlan, CompletionVerdict, ContractInvalid, ExperienceMatch
from ..experience.trial import match_experience_for_second_task

if TYPE_CHECKING:
    from ..contracts import ExperienceCandidate


@dataclass(frozen=True)
class SecondTaskPlan:
    """A second task plan that was influenced by first-round experience."""
    plan_without_experience: BoundActionPlan
    plan_with_experience: BoundActionPlan
    match: ExperienceMatch
    experience_was_applied: bool
    preconditions_differ: bool
    experience_match_ref_set: bool


def plan_second_task_with_experience(
    experience: ExperienceCandidate,
    first_completion: CompletionVerdict,
    *,
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    task_revision: int,
    second_target_path: str,
    second_content: str,
    second_snapshot,  # ProjectSnapshot
) -> SecondTaskPlan:
    """Plan the second task with and without experience for comparison.

    Validates that first_completion completed successfully and matches
    the experience source. Returns both plans so caller can observe
    the concrete difference experience makes.
    """
    from ..world.controlled_write import bind_single_file_create

    # Validate first_completion is actually completed
    if first_completion.outcome != "completed":
        raise ContractInvalid("First task must be completed to extract experience")
    if first_completion.meta.task_id != experience.meta.task_id:
        raise ContractInvalid("Experience source must match first completion task")

    # Match experience for the second task
    match = match_experience_for_second_task(
        experience,
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref=project_ref,
        correlation_id=correlation_id,
        task_revision=task_revision,
        target_scope=("notes/",),
        risk="low",
    )

    experience_was_applied = bool(match.candidate_refs)

    # Create plan WITHOUT experience (baseline)
    plan_without = bind_single_file_create(
        second_snapshot,
        f"candidate:{task_id}",
        second_content,
        target_path=second_target_path,
        experience_match_ref=None,
        task_revision=task_revision,
    )

    # Create plan WITH experience
    plan_with = bind_single_file_create(
        second_snapshot,
        f"candidate:{task_id}",
        second_content,
        target_path=second_target_path,
        experience_match_ref=match.meta.integrity_ref if experience_was_applied else None,
        task_revision=task_revision,
    )

    # Check concrete differences
    preconditions_differ = plan_without.preconditions != plan_with.preconditions
    experience_match_ref_set = plan_with.experience_match_ref is not None

    return SecondTaskPlan(
        plan_without_experience=plan_without,
        plan_with_experience=plan_with,
        match=match,
        experience_was_applied=experience_was_applied,
        preconditions_differ=preconditions_differ,
        experience_match_ref_set=experience_match_ref_set,
    )


def verify_causal_chain(
    experience_ref: str,
    match: ExperienceMatch,
    plan: BoundActionPlan,
    completion: CompletionVerdict,
) -> bool:
    """Verify the experience → match → plan → completion causal chain."""
    if experience_ref not in match.candidate_refs:
        return False
    if plan.experience_match_ref != match.meta.integrity_ref:
        return False
    if completion.action_plan_ref != plan.meta.integrity_ref:
        return False
    if not all([
        match.meta.task_id == completion.meta.task_id,
        match.meta.task_run_id == completion.meta.task_run_id,
        match.meta.project_ref == completion.meta.project_ref,
        match.meta.correlation_id == completion.meta.correlation_id,
    ]):
        return False
    return True
