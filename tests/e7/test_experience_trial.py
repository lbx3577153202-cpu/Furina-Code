"""E7 — experience becomes conditional only after an independent second task."""

import pytest

from furina_code.contracts import AuthorityViolation, BoundActionPlan, CompletionVerdict
from furina_code.experience import (
    adjudicate_trial,
    extract_completed_write_experience,
    match_experience_for_second_task,
    record_trial_use,
    write_experience_object,
)
from furina_code.ledger import Ledger
from furina_code.world.controlled_write import write_e5_object


def _plan(task_id: str, match_ref: str | None = None) -> BoundActionPlan:
    return BoundActionPlan.create(
        run_binding_id=f"rb-{task_id}", task_id=task_id, task_run_id=f"run-{task_id}",
        project_ref="project-1", correlation_id=f"corr-{task_id}",
        candidate_ref="candidate:test", task_revision=1,
        baseline_snapshot_ref="sha256:snapshot", baseline_snapshot_sha256="sha256:abc",
        target_scope=("notes/",),
        operations=({"kind": "create_file", "path": "notes/test.txt", "content": "test\n"},),
        expected_diff={"created_path": "notes/test.txt", "content_sha256": "sha256:test"},
        risk="low", rollback_or_compensation="remove file",
        preconditions=("baseline_clean", "target_absent"),
        experience_match_ref=match_ref,
    )


def _completion(task_id: str, outcome: str = "completed", *,
                task_run_id: str | None = None, correlation_id: str | None = None,
                project: str = "project-1", task_revision: int = 1,
                plan_ref: str | None = None) -> CompletionVerdict:
    run_id = task_run_id or f"run-{task_id}"
    corr_id = correlation_id or f"corr-{task_id}"
    return CompletionVerdict.create(
        run_binding_id=f"rb-{task_id}", task_id=task_id, task_run_id=run_id,
        project_ref=project, correlation_id=corr_id, task_revision=task_revision,
        task_run_ref="sha256:task-run", verification_ref="sha256:verification",
        candidate_ref="candidate:controlled-write", outcome=outcome,
        completed_items=("controlled write",) if outcome == "completed" else (),
        incomplete_items=("controlled write",) if outcome != "completed" else (),
        no_project_side_effect=False, action_plan_ref=plan_ref,
    )


def test_independent_second_task_turns_candidate_into_conditional_experience(tmp_path):
    ledger = Ledger(str(tmp_path / "experience.sqlite3"))
    ledger.open()
    first = _completion("task-one")
    write_e5_object(ledger, first, 0)
    experience = extract_completed_write_experience(first, ledger)
    write_experience_object(ledger, experience, 0)

    match = match_experience_for_second_task(
        experience, run_binding_id="rb-two", task_id="task-two", task_run_id="run-two",
        project_ref="project-1", correlation_id="corr-two", task_revision=1,
        target_scope=("notes/",), risk="low",
    )
    write_experience_object(ledger, match, 0)
    plan = _plan("task-two", match_ref=match.meta.integrity_ref)
    second = _completion("task-two", task_run_id="run-two", correlation_id="corr-two",
                         plan_ref=plan.meta.integrity_ref)
    trial = record_trial_use(experience, match, plan, second)
    write_experience_object(ledger, trial, 0)
    lifecycle = adjudicate_trial(experience, trial)
    write_experience_object(ledger, lifecycle, 0)

    assert match.recommendation.startswith("candidate_guidance_only")
    assert trial.usage_mode == "candidate_guidance_only"
    assert lifecycle.new_status == "conditional"
    assert lifecycle.new_status != "reusable"
    ledger.close()


def test_experience_cannot_validate_itself_on_its_source_task():
    ledger = Ledger(":memory:")
    ledger.open()
    comp = _completion("task-one")
    write_e5_object(ledger, comp, 0)
    experience = extract_completed_write_experience(comp, ledger)

    match = match_experience_for_second_task(
        experience, run_binding_id="rb-one", task_id="task-one", task_run_id="run-one-new",
        project_ref="project-1", correlation_id="corr-one-new", task_revision=2,
        target_scope=("notes/",), risk="low",
    )

    assert match.candidate_refs == ()
    assert match.recommendation == "do_not_apply_experience"


def test_failed_second_task_degrades_instead_of_promoting_experience():
    ledger = Ledger(":memory:")
    ledger.open()
    comp = _completion("task-one")
    write_e5_object(ledger, comp, 0)
    experience = extract_completed_write_experience(comp, ledger)
    match = match_experience_for_second_task(
        experience, run_binding_id="rb-two", task_id="task-two", task_run_id="run-two",
        project_ref="project-1", correlation_id="corr-two", task_revision=1,
        target_scope=("notes/",), risk="low",
    )
    plan = _plan("task-two", match_ref=match.meta.integrity_ref)
    trial = record_trial_use(experience, match, plan,
                             _completion("task-two", "not_completed",
                                         task_run_id="run-two", correlation_id="corr-two",
                                         plan_ref=plan.meta.integrity_ref))

    assert adjudicate_trial(experience, trial).new_status == "degraded"


def test_experience_owner_is_enforced(tmp_path):
    ledger = Ledger(str(tmp_path / "experience.sqlite3"))
    ledger.open()
    comp = _completion("task-one")
    write_e5_object(ledger, comp, 0)
    experience = extract_completed_write_experience(comp, ledger)
    with pytest.raises(AuthorityViolation):
        ledger.write_object(experience.meta, {}, caller_organ="I9-X", expected_revision=0)
    ledger.close()
