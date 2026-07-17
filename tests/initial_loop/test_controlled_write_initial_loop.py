"""The initial-loop proof: two real controlled writes, recovery-safe contracts, E7 trial."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from furina_code.contracts import ContractInvalid, Disposition, Phase
from furina_code.experience import (
    adjudicate_trial,
    extract_completed_write_experience,
    match_experience_for_second_task,
    record_trial_use,
    write_experience_object,
)
from furina_code.initial_loop import run_controlled_write_cycle
from furina_code.ledger import Ledger


def _repo(root: Path, name: str) -> Path:
    repo = root / name
    repo.mkdir()
    for args in (("init",), ("config", "user.email", "loop@example.test"), ("config", "user.name", "Initial loop")):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "README.md").write_bytes(b"fixture\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True, text=True)
    return repo


def test_initial_loop_completes_two_independent_controlled_tasks_and_conditional_trial(tmp_path):
    first_repo = _repo(tmp_path, "first")
    second_repo = _repo(tmp_path, "second")
    ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
    ledger.open()

    first = run_controlled_write_cycle(
        ledger, str(first_repo), run_binding_id="rb-one", task_id="task-one", task_run_id="run-one",
        project_ref="project-one", correlation_id="corr-one", candidate_ref="candidate:first",
        user_authority_refs=("user:explicit-initial-loop",), content="Hello from Furina Code.\n",
        target_path="notes/welcome.txt",
    )
    assert first.completion.outcome == "completed"
    assert first.task_run.phase is Phase.TERMINAL
    assert first.task_run.disposition is Disposition.TERMINAL
    assert (first_repo / "notes" / "welcome.txt").read_bytes() == b"Hello from Furina Code.\n"

    experience = extract_completed_write_experience(first.completion)
    write_experience_object(ledger, experience, 0)
    match = match_experience_for_second_task(
        experience, run_binding_id="rb-two", task_id="task-two", task_run_id="run-two",
        project_ref="project-two", correlation_id="corr-two", task_revision=1,
        target_scope=("notes/",), risk="low",
    )
    write_experience_object(ledger, match, 0)
    assert match.recommendation.startswith("candidate_guidance_only")

    second = run_controlled_write_cycle(
        ledger, str(second_repo), run_binding_id="rb-two", task_id="task-two", task_run_id="run-two",
        project_ref="project-two", correlation_id="corr-two", candidate_ref="candidate:second",
        user_authority_refs=("user:explicit-initial-loop",), content="A distinct second task.\n",
        target_path="notes/greeting.txt", experience_match_ref=match.meta.integrity_ref,
    )
    assert second.completion.outcome == "completed"
    assert (second_repo / "notes" / "greeting.txt").read_bytes() == b"A distinct second task.\n"
    assert second.plan.expected_diff["created_path"] != first.plan.expected_diff["created_path"]

    # Verify the experience match ref is embedded in the second plan
    assert any("experience_match:" in p for p in second.plan.preconditions)

    trial = record_trial_use(experience, match, second.completion)
    write_experience_object(ledger, trial, 0)
    lifecycle = adjudicate_trial(experience, trial)
    write_experience_object(ledger, lifecycle, 0)
    assert lifecycle.new_status == "conditional"
    assert lifecycle.new_status != "reusable"
    ledger.close()


def test_e5_act_time_snapshot_denies_write_on_external_change(tmp_path):
    """Regression: if workspace changes between observe and act, execution must deny."""
    repo = _repo(tmp_path, "repo")
    ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
    ledger.open()

    # Start a cycle but don't finish it — we need to inject an external change
    # between observe and act.  We do this by running observe+authorize, then
    # modifying the repo, then attempting execution.
    from furina_code.contracts import TaskRun, AuthorizationDecision, AuthorizationTicket
    from furina_code.world import create_project_snapshot
    from furina_code.world.controlled_write import (
        bind_single_file_create, evaluate_single_file_authorization,
        issue_single_file_ticket, execute_single_file_create, write_e5_object,
    )

    run = TaskRun.create("rb-act", "task-act", "run-act", "project-act", "corr-act", 1)
    write_e5_object(ledger, run, 0)
    run = run.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
    write_e5_object(ledger, run, run.meta.revision - 1)

    before = create_project_snapshot(
        "rb-act", "task-act", "run-act", "project-act", "corr-act", str(repo),
        snapshot_id="task-act:snapshot:before",
    )
    write_e5_object(ledger, before, 0)

    plan = bind_single_file_create(before, "candidate:act-test", "should be denied\n")
    write_e5_object(ledger, plan, 0)
    run = run.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE,
                         current_refs=(plan.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)

    decision = evaluate_single_file_authorization(plan, "user", ("user:act-test",))
    write_e5_object(ledger, decision, 0)
    ticket = issue_single_file_ticket(decision, plan)
    write_e5_object(ledger, ticket, 0)
    run = run.transition("I2-D", Phase.AUTHORIZE, Disposition.ACTIVE,
                         current_refs=(ticket.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)
    run = run.transition("I2-D", Phase.ACT, Disposition.ACTIVE,
                         current_refs=(ticket.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)

    # EXTERNAL CHANGE: create a new untracked file between observe and act
    (repo / "notes").mkdir(exist_ok=True)
    (repo / "notes" / "external.txt").write_bytes(b"external change\n")

    # Now attempt execution with a FRESH act-time snapshot
    act_time = create_project_snapshot(
        "rb-act", "task-act", "run-act", "project-act", "corr-act", str(repo),
        snapshot_id="task-act:snapshot:act-time",
    )
    write_e5_object(ledger, act_time, 0)

    result = execute_single_file_create(
        ledger, str(repo), plan, ticket, act_time, "task-act:create:notes/welcome.txt", run,
    )

    # The enforcement MUST deny because act-time snapshot differs from baseline
    assert result.enforcement.decision == "deny"
    assert result.receipt is None
    assert "project snapshot drifted" in result.enforcement.reason
    # The target file must NOT exist
    assert not (repo / "notes" / "welcome.txt").exists()
    ledger.close()


def test_e7_trial_rejects_cross_task_match(tmp_path):
    """Regression: a match from a different task cannot bind to a completion."""
    experience = extract_completed_write_experience(
        _make_completion("task-src", "completed")
    )
    match = match_experience_for_second_task(
        experience, run_binding_id="rb-other", task_id="task-other", task_run_id="run-other",
        project_ref="project-other", correlation_id="corr-other", task_revision=1,
        target_scope=("notes/",), risk="low",
    )
    # Completion from a THIRD task — different project, but same task_id, run, and correlation
    completion = _make_completion("task-other", "completed",
                                 project="project-diff", task_run_id="run-other",
                                 correlation_id="corr-other")

    with pytest.raises(ContractInvalid, match="same project"):
        record_trial_use(experience, match, completion)


def test_e7_trial_rejects_mismatched_revision(tmp_path):
    """Regression: match and completion must reference the same task revision."""
    experience = extract_completed_write_experience(
        _make_completion("task-x", "completed")
    )
    match = match_experience_for_second_task(
        experience, run_binding_id="rb-x", task_id="task-x2", task_run_id="run-x2",
        project_ref="project-x", correlation_id="corr-x", task_revision=1,
        target_scope=("notes/",), risk="low",
    )
    completion = _make_completion("task-x2", "completed", task_run_id="run-x2",
                                 correlation_id="corr-x", project="project-x", task_revision=2)

    with pytest.raises(ContractInvalid, match="task revision"):
        record_trial_use(experience, match, completion)


def test_e7_second_round_never_reusable(tmp_path):
    """Regression: successful second round must be conditional, never reusable."""
    experience = extract_completed_write_experience(
        _make_completion("task-y", "completed")
    )
    match = match_experience_for_second_task(
        experience, run_binding_id="rb-y", task_id="task-y2", task_run_id="run-y2",
        project_ref="project-y", correlation_id="corr-y", task_revision=1,
        target_scope=("notes/",), risk="low",
    )
    completion = _make_completion("task-y2", "completed", task_run_id="run-y2",
                                 correlation_id="corr-y", project="project-y")
    trial = record_trial_use(experience, match, completion)
    lifecycle = adjudicate_trial(experience, trial)
    assert lifecycle.new_status == "conditional"
    assert lifecycle.new_status != "reusable"


def test_e7_failed_second_round_degrades(tmp_path):
    """Regression: failed second round must degrade the experience."""
    experience = extract_completed_write_experience(
        _make_completion("task-z", "completed")
    )
    match = match_experience_for_second_task(
        experience, run_binding_id="rb-z", task_id="task-z2", task_run_id="run-z2",
        project_ref="project-z", correlation_id="corr-z", task_revision=1,
        target_scope=("notes/",), risk="low",
    )
    completion = _make_completion("task-z2", "not_completed", task_run_id="run-z2",
                                 correlation_id="corr-z", project="project-z")
    trial = record_trial_use(experience, match, completion)
    lifecycle = adjudicate_trial(experience, trial)
    assert lifecycle.new_status == "degraded"


def _make_completion(task_id: str, outcome: str = "completed", *,
                     project: str = "project-1", task_revision: int = 1,
                     task_run_id: str | None = None, correlation_id: str | None = None):
    from furina_code.contracts import CompletionVerdict
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
