"""The initial-loop proof: two real controlled writes, recovery-safe contracts, E7 trial."""

from __future__ import annotations

import subprocess
from pathlib import Path

from furina_code.contracts import Disposition, Phase
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
        target_path="notes/greeting.txt",
    )
    assert second.completion.outcome == "completed"
    assert (second_repo / "notes" / "greeting.txt").read_bytes() == b"A distinct second task.\n"
    assert second.plan.expected_diff["created_path"] != first.plan.expected_diff["created_path"]

    trial = record_trial_use(experience, match, second.completion)
    write_experience_object(ledger, trial, 0)
    lifecycle = adjudicate_trial(experience, trial)
    write_experience_object(ledger, lifecycle, 0)
    assert lifecycle.new_status == "conditional"
    assert lifecycle.new_status != "reusable"
    ledger.close()
