"""E6 — interrupted writes are recovered by verdict, never blind replay."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from furina_code.continuity import review_interrupted_write, write_recovery_object
from furina_code.contracts import ActionReceipt, Checkpoint, Disposition, Phase, StateTransitionInvalid, TaskRun
from furina_code.ledger import Ledger
from furina_code.world import create_project_snapshot
from furina_code.world.controlled_write import bind_single_file_create, write_e5_object


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _setup(tmp_path: Path):
    repo = tmp_path / "project"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "e6@example.test")
    _git(repo, "config", "user.name", "E6 test")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial fixture")
    ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
    ledger.open()
    before = create_project_snapshot("rb-1", "task-1", "run-1", "project-1", "corr-1", str(repo), snapshot_id="before")
    write_e5_object(ledger, before, 0)
    plan = bind_single_file_create(before, "candidate:e6", "Hello from Furina Code.\n")
    write_e5_object(ledger, plan, 0)
    checkpoint = Checkpoint.create(
        "rb-1", "task-1", "run-1", "project-1", "corr-1", 1,
        Phase.ACT, Disposition.ACTIVE, 2, (), before.meta.integrity_ref,
        "interrupted controlled action", pending_actions=(plan.meta.integrity_ref,),
        ticket_refs=("ticket:one",), causation_ref=plan.meta.integrity_ref,
    )
    write_recovery_object(ledger, checkpoint, 0)
    return repo, ledger, before, plan, checkpoint


def _unknown_receipt(plan):
    started = ActionReceipt.create(
        plan.meta.run_binding_id, plan.meta.task_id, plan.meta.task_run_id,
        plan.meta.project_ref, plan.meta.correlation_id, plan.meta.integrity_ref,
        "ticket:one", "e6-unknown", "e5-safe-file-create-v1",
    )
    return started.finish("outcome_unknown", None, {"error": "timeout"}, "outcome unknown")


def test_before_action_valid_ticket_can_only_continue_to_enforcement(tmp_path):
    repo, ledger, before, plan, checkpoint = _setup(tmp_path)

    verdict = review_interrupted_write(ledger, str(repo), checkpoint, plan, before, None, "active")

    assert verdict.outcome == "continue_no_replay"
    assert verdict.resume_phase == Phase.ACT
    assert "re-run enforcement" in verdict.required_steps[0]
    assert not (repo / "notes" / "welcome.txt").exists()
    ledger.close()


def test_unknown_outcome_with_observed_target_skips_duplicate_action(tmp_path):
    repo, ledger, before, plan, checkpoint = _setup(tmp_path)
    (repo / "notes").mkdir()
    (repo / "notes" / "welcome.txt").write_bytes(b"Hello from Furina Code.\n")
    fresh = create_project_snapshot("rb-1", "task-1", "run-1", "project-1", "corr-1", str(repo), snapshot_id="fresh")

    verdict = review_interrupted_write(ledger, str(repo), checkpoint, plan, fresh, _unknown_receipt(plan), "consumed")

    assert verdict.outcome == "skip_confirmed_action"
    assert verdict.resume_phase == Phase.RECONCILE
    assert "do not execute action again" in verdict.required_steps
    assert (repo / "notes" / "welcome.txt").read_text(encoding="utf-8") == "Hello from Furina Code.\n"
    ledger.close()


def test_unknown_outcome_without_proof_pauses_and_never_retries(tmp_path):
    repo, ledger, before, plan, checkpoint = _setup(tmp_path)

    verdict = review_interrupted_write(ledger, str(repo), checkpoint, plan, before, _unknown_receipt(plan), "consumed")

    assert verdict.outcome == "pause"
    assert "do not retry automatically" in verdict.required_steps
    assert not (repo / "notes" / "welcome.txt").exists()
    ledger.close()


def test_recovery_review_cannot_resume_without_verdict_reference(tmp_path):
    repo, ledger, before, plan, checkpoint = _setup(tmp_path)
    verdict = review_interrupted_write(ledger, str(repo), checkpoint, plan, before, _unknown_receipt(plan), "consumed")
    run = TaskRun.create("rb-1", "task-1", "run-1", "project-1", "corr-1", 1)
    for phase in (Phase.OBSERVE, Phase.DELIBERATE, Phase.AUTHORIZE, Phase.ACT):
        run = run.transition("I2-D", phase, Disposition.ACTIVE)
    run = run.transition("I2-D", Phase.RECONCILE, Disposition.RECOVERY_REVIEW)

    with pytest.raises(StateTransitionInvalid, match="RecoveryVerdict"):
        run.transition("I2-D", Phase.RECONCILE, Disposition.ACTIVE)

    resumed = run.transition(
        "I2-D", Phase.RECONCILE, Disposition.ACTIVE,
        recovery_verdict_ref=verdict.meta.integrity_ref,
    )
    assert resumed.phase == Phase.RECONCILE
    assert resumed.disposition == Disposition.ACTIVE
    assert verdict.meta.integrity_ref in resumed.current_refs
    assert resumed.meta.causation_ref == verdict.meta.integrity_ref
    ledger.close()
