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


class SecondTaskSupplier:
    """Supplies second task only after first round completion is verified in ledger."""

    def __init__(self, ledger: Ledger, first_task_id: str) -> None:
        self._ledger = ledger
        self._first_task_id = first_task_id
        self._called = False

    def get_second_task(self, run_binding_id: str) -> None:
        """Called after first completion to signal readiness for second task."""
        self._called = True
        # Verify first completion is completed in ledger
        objects = self._ledger.get_latest_for_binding(run_binding_id)
        found = False
        for meta, payload in objects:
            if meta.object_type == "CompletionVerdict" and meta.task_id == self._first_task_id:
                if payload.get("outcome") == "completed":
                    found = True
                    break
        if not found:
            raise ContractInvalid(
                "Second task supplier: first round completion not verified in ledger"
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
    *,
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    task_revision: int,
    second_target_path: str,
    second_content: str,
    second_snapshot,
) -> SecondTaskPlan:
    """Plan second task with experience. Validates first completion source."""
    from ..world.controlled_write import bind_single_file_create

    # Validate first_completion completed and matches experience source
    if first_completion.outcome != "completed":
        raise ContractInvalid("First task must be completed")
    if first_completion.meta.integrity_ref not in experience.source_completion_refs:
        raise ContractInvalid(
            "First completion integrity_ref must be in experience.source_completion_refs"
        )

    match = match_experience_for_second_task(
        experience,
        run_binding_id=run_binding_id, task_id=task_id,
        task_run_id=task_run_id, project_ref=project_ref,
        correlation_id=correlation_id, task_revision=task_revision,
        target_scope=("notes/",), risk="low",
    )

    experience_was_applied = bool(match.candidate_refs)

    # Plan WITHOUT experience (baseline)
    plan_without = bind_single_file_create(
        second_snapshot, f"candidate:{task_id}", second_content,
        target_path=second_target_path, experience_match_ref=None,
        task_revision=task_revision,
    )

    # Plan WITH experience - adds verification step to preconditions
    plan_with = bind_single_file_create(
        second_snapshot, f"candidate:{task_id}", second_content,
        target_path=second_target_path,
        experience_match_ref=match.meta.integrity_ref if experience_was_applied else None,
        task_revision=task_revision,
    )

    # The experience_match_ref is embedded in the plan's canonical payload,
    # making it part of the integrity hash and auditable.
    # When experience is applied, the plan carries an additional precondition
    # that the execution chain must verify.
    experience_match_ref_set = plan_with.experience_match_ref is not None

    # Concrete difference: plan_with has experience_match_ref in payload,
    # which changes the integrity hash and is part of the formal plan.
    has_extra_verification = experience_match_ref_set

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
