"""B6: Second task determined only after first completion.

Second task supplier can only be called after first round ledger
completion is verified completed. Experience must change actual
plan content, not just set experience_match_ref.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..contracts import BoundActionPlan, CompletionVerdict, ContractInvalid, ExperienceMatch
from ..experience.trial import match_experience_for_second_task

if TYPE_CHECKING:
    from ..contracts import ExperienceCandidate
    from ..ledger import Ledger


@dataclass(frozen=True)
class SecondTaskRequest:
    """Auditable description of the second task, produced by supplier."""
    target_path: str
    content: str
    source_completion_ref: str
    experience_ref: str


class SecondTaskSupplier:
    """Supplies second task only after first round completion is verified in ledger."""

    def __init__(
        self,
        ledger: Ledger,
        first_task_id: str,
        second_target_path: str,
        second_content: str,
    ) -> None:
        self._ledger = ledger
        self._first_task_id = first_task_id
        self._second_target_path = second_target_path
        self._second_content = second_content
        self._called = False

    def get_second_task(self, run_binding_id: str) -> SecondTaskRequest:
        """Return second task description only if first round completed in ledger.

        Raises ContractInvalid if first round not completed.
        was_called is only set to True on success.
        """
        objects = self._ledger.get_latest_for_binding(run_binding_id)
        found_completion_ref = None
        for meta, payload in objects:
            if meta.object_type == "CompletionVerdict" and meta.task_id == self._first_task_id:
                if payload.get("outcome") == "completed":
                    found_completion_ref = meta.integrity_ref
                    break
        if found_completion_ref is None:
            raise ContractInvalid(
                "Second task supplier: first round completion not verified in ledger"
            )
        self._called = True
        return SecondTaskRequest(
            target_path=self._second_target_path,
            content=self._second_content,
            source_completion_ref=found_completion_ref,
            experience_ref="",  # filled by caller after experience extraction
        )

    @property
    def was_called(self) -> bool:
        return self._called


@dataclass(frozen=True)
class SecondTaskPlan:
    plan_without_experience: BoundActionPlan
    plan_with_experience: BoundActionPlan
    match: ExperienceMatch
    experience_was_applied: bool
    experience_match_ref_set: bool
    has_extra_verification: bool


def plan_second_task_with_experience(
    experience: ExperienceCandidate,
    first_completion: CompletionVerdict,
    request: SecondTaskRequest,
    *,
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    task_revision: int,
    second_snapshot,
) -> SecondTaskPlan:
    """Plan second task with experience. Validates first completion source.

    Accepts SecondTaskRequest from supplier instead of separate path/content.
    Validates request's source_completion_ref matches first_completion.
    """
    from ..world.controlled_write import bind_single_file_create

    # Validate first_completion completed and matches experience source
    if first_completion.outcome != "completed":
        raise ContractInvalid("First task must be completed")
    if first_completion.meta.integrity_ref not in experience.source_completion_refs:
        raise ContractInvalid(
            "First completion integrity_ref must be in experience.source_completion_refs"
        )
    # Validate request's source completion matches first completion
    if request.source_completion_ref != first_completion.meta.integrity_ref:
        raise ContractInvalid(
            "Request source_completion_ref does not match first completion"
        )

    second_target_path = request.target_path
    second_content = request.content

    match = match_experience_for_second_task(
        experience,
        run_binding_id=run_binding_id, task_id=task_id,
        task_run_id=task_run_id, project_ref=project_ref,
        correlation_id=correlation_id, task_revision=task_revision,
        target_scope=("notes/",), risk="low",
    )

    experience_was_applied = bool(match.candidate_refs)

    # Plan WITHOUT experience (baseline) - standard preconditions
    plan_without = bind_single_file_create(
        second_snapshot, f"candidate:{task_id}", second_content,
        target_path=second_target_path, experience_match_ref=None,
        task_revision=task_revision,
    )

    # Plan WITH experience - adds "experience_verified" precondition
    # This changes what the verification chain must check
    extra_preconditions = ("experience_verified",) if experience_was_applied else ()
    plan_with = bind_single_file_create(
        second_snapshot, f"candidate:{task_id}", second_content,
        target_path=second_target_path,
        experience_match_ref=match.meta.integrity_ref if experience_was_applied else None,
        task_revision=task_revision,
        extra_preconditions=extra_preconditions,
    )

    experience_match_ref_set = plan_with.experience_match_ref is not None
    has_extra_verification = bool(extra_preconditions)

    return SecondTaskPlan(
        plan_without_experience=plan_without,
        plan_with_experience=plan_with,
        match=match,
        experience_was_applied=experience_was_applied,
        experience_match_ref_set=experience_match_ref_set,
        has_extra_verification=has_extra_verification,
    )


def verify_causal_chain(
    experience_ref: str,
    match: ExperienceMatch,
    plan: BoundActionPlan,
    completion: CompletionVerdict,
) -> bool:
    """Verify experience -> match -> plan -> completion chain."""
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
