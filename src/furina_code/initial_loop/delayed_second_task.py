"""B6: Second task determined only after first completion.

The second task's path/content must not be created before the first task
starts. Experience from the first task must change the second plan without
becoming an authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..contracts import BoundActionPlan, CompletionVerdict, ExperienceMatch
from ..experience.trial import match_experience_for_second_task

if TYPE_CHECKING:
    from ..contracts import ExperienceCandidate


@dataclass(frozen=True)
class SecondTaskPlan:
    """A second task plan that was influenced by first-round experience."""
    plan: BoundActionPlan
    match: ExperienceMatch
    experience_was_applied: bool
    match_changed_plan: bool
    authorization_independent: bool


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
    """Plan the second task using experience from the first completion.

    This function:
    1. Takes the first completion's experience
    2. Matches it against the second task's parameters
    3. Creates a plan that may be influenced by the match
    4. Ensures the match is guidance only, not authorization
    """
    from ..world.controlled_write import bind_single_file_create

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

    # The match influences the plan but doesn't replace authorization
    experience_was_applied = bool(match.candidate_refs)
    match_changed_plan = match.recommendation.startswith("candidate_guidance_only")

    # Create the plan with experience match ref
    plan = bind_single_file_create(
        second_snapshot,
        f"candidate:{task_id}",
        second_content,
        target_path=second_target_path,
        experience_match_ref=match.meta.integrity_ref if experience_was_applied else None,
        task_revision=task_revision,
    )

    return SecondTaskPlan(
        plan=plan,
        match=match,
        experience_was_applied=experience_was_applied,
        match_changed_plan=match_changed_plan,
        authorization_independent=True,  # Experience never replaces authorization
    )


def verify_causal_chain(
    experience_ref: str,
    match: ExperienceMatch,
    plan: BoundActionPlan,
    completion: CompletionVerdict,
) -> bool:
    """Verify the experience → match → plan → completion causal chain."""
    # Experience must be in match candidates
    if experience_ref not in match.candidate_refs:
        return False

    # Plan must reference the match
    if plan.experience_match_ref != match.meta.integrity_ref:
        return False

    # Completion must reference the plan
    if completion.action_plan_ref != plan.meta.integrity_ref:
        return False

    # All must share the same task identity
    if not all([
        match.meta.task_id == completion.meta.task_id,
        match.meta.task_run_id == completion.meta.task_run_id,
        match.meta.project_ref == completion.meta.project_ref,
        match.meta.correlation_id == completion.meta.correlation_id,
    ]):
        return False

    return True
