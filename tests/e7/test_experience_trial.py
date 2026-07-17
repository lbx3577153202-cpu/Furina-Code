"""E7 — experience becomes conditional only after an independent second task."""

import pytest

from furina_code.contracts import AuthorityViolation, CompletionVerdict
from furina_code.experience import (
    adjudicate_trial,
    extract_completed_write_experience,
    match_experience_for_second_task,
    record_trial_use,
    write_experience_object,
)
from furina_code.ledger import Ledger


def _completion(task_id: str, outcome: str = "completed", *,
                task_run_id: str | None = None, correlation_id: str | None = None,
                project: str = "project-1", task_revision: int = 1) -> CompletionVerdict:
    run_id = task_run_id or f"run-{task_id}"
    corr_id = correlation_id or f"corr-{task_id}"
    return CompletionVerdict.create(
        run_binding_id=f"rb-{task_id}", task_id=task_id, task_run_id=run_id,
        project_ref=project, correlation_id=corr_id, task_revision=task_revision,
        task_run_ref="sha256:task-run", verification_ref="sha256:verification",
        candidate_ref="candidate:controlled-write", outcome=outcome,
        completed_items=("controlled write",) if outcome == "completed" else (),
        incomplete_items=("controlled write",) if outcome != "completed" else (),
        no_project_side_effect=False,
    )


def test_independent_second_task_turns_candidate_into_conditional_experience(tmp_path):
    first = _completion("task-one")
    experience = extract_completed_write_experience(first)
    ledger = Ledger(str(tmp_path / "experience.sqlite3"))
    ledger.open()
    write_experience_object(ledger, experience, 0)

    match = match_experience_for_second_task(
        experience, run_binding_id="rb-two", task_id="task-two", task_run_id="run-two",
        project_ref="project-1", correlation_id="corr-two", task_revision=1,
        target_scope=("notes/",), risk="low",
    )
    write_experience_object(ledger, match, 0)
    second = _completion("task-two", task_run_id="run-two", correlation_id="corr-two")
    trial = record_trial_use(experience, match, second)
    write_experience_object(ledger, trial, 0)
    lifecycle = adjudicate_trial(experience, trial)
    write_experience_object(ledger, lifecycle, 0)

    assert match.recommendation.startswith("candidate_guidance_only")
    assert trial.usage_mode == "candidate_guidance_only"
    assert lifecycle.new_status == "conditional"
    assert lifecycle.new_status != "reusable"
    ledger.close()


def test_experience_cannot_validate_itself_on_its_source_task():
    experience = extract_completed_write_experience(_completion("task-one"))

    match = match_experience_for_second_task(
        experience, run_binding_id="rb-one", task_id="task-one", task_run_id="run-one-new",
        project_ref="project-1", correlation_id="corr-one-new", task_revision=2,
        target_scope=("notes/",), risk="low",
    )

    assert match.candidate_refs == ()
    assert match.recommendation == "do_not_apply_experience"


def test_failed_second_task_degrades_instead_of_promoting_experience():
    experience = extract_completed_write_experience(_completion("task-one"))
    match = match_experience_for_second_task(
        experience, run_binding_id="rb-two", task_id="task-two", task_run_id="run-two",
        project_ref="project-1", correlation_id="corr-two", task_revision=1,
        target_scope=("notes/",), risk="low",
    )
    trial = record_trial_use(experience, match, _completion("task-two", "not_completed",
                                                           task_run_id="run-two", correlation_id="corr-two"))

    assert adjudicate_trial(experience, trial).new_status == "degraded"


def test_experience_owner_is_enforced(tmp_path):
    experience = extract_completed_write_experience(_completion("task-one"))
    ledger = Ledger(str(tmp_path / "experience.sqlite3"))
    ledger.open()
    with pytest.raises(AuthorityViolation):
        ledger.write_object(experience.meta, {}, caller_organ="I9-X", expected_revision=0)
    ledger.close()
