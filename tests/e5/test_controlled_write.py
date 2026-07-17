"""E5 — one actual, ticket-gated project write in an isolated Git project."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from furina_code.contracts import ContractInvalid, Disposition, Phase, TaskRun
from furina_code.ledger import Ledger
from furina_code.world import create_project_snapshot
from furina_code.world.controlled_write import (
    bind_single_file_create,
    evaluate_single_file_authorization,
    execute_single_file_create,
    issue_single_file_ticket,
    reconcile_single_file_create,
    verify_single_file_create,
    adjudicate_single_file_completion,
    write_e5_object,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _new_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "project"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "e5@example.test")
    _git(repo, "config", "user.name", "E5 test")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial fixture")
    return repo


def _act_run() -> TaskRun:
    task_run = TaskRun.create("rb-1", "task-1", "run-1", "project-1", "corr-1", 1)
    for phase in (Phase.OBSERVE, Phase.DELIBERATE, Phase.AUTHORIZE, Phase.ACT):
        task_run = task_run.transition("I2-D", phase, Disposition.ACTIVE)
    return task_run


def _prepared(tmp_path: Path):
    repo = _new_repo(tmp_path)
    ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
    ledger.open()
    before = create_project_snapshot(
        "rb-1", "task-1", "run-1", "project-1", "corr-1", str(repo),
        snapshot_id="task-1:snapshot:before",
    )
    write_e5_object(ledger, before, 0)
    plan = bind_single_file_create(before, "candidate:e5:welcome", "Hello from Furina Code.\n")
    decision = evaluate_single_file_authorization(plan, "user-1", ("user:explicit-e5",))
    ticket = issue_single_file_ticket(decision, plan)
    write_e5_object(ledger, plan, 0)
    write_e5_object(ledger, decision, 0)
    write_e5_object(ledger, ticket, 0)
    return repo, ledger, before, plan, ticket, _act_run()


def test_single_controlled_write_has_receipt_and_reconciliation(tmp_path):
    repo, ledger, before, plan, ticket, task_run = _prepared(tmp_path)

    result = execute_single_file_create(
        ledger, str(repo), plan, ticket, before, "e5-write-1", task_run,
    )
    assert result.enforcement.decision == "allow"
    assert result.receipt is not None
    assert result.receipt.status == "applied"
    assert (repo / "notes" / "welcome.txt").read_text(encoding="utf-8") == "Hello from Furina Code.\n"

    after = create_project_snapshot(
        "rb-1", "task-1", "run-1", "project-1", "corr-1", str(repo),
        snapshot_id="task-1:snapshot:after",
    )
    write_e5_object(ledger, after, 0)
    reconciliation = reconcile_single_file_create(
        ledger, str(repo), plan, result.receipt, before, after,
    )
    verify_run = task_run.transition("I2-D", Phase.RECONCILE, Disposition.ACTIVE)
    verify_run = verify_run.transition("I2-D", Phase.VERIFY, Disposition.ACTIVE)
    verification = verify_single_file_create(
        ledger, plan, reconciliation, verify_run,
    )
    adjudicate_run = verify_run.transition("I2-D", Phase.ADJUDICATE, Disposition.ACTIVE)
    completion = adjudicate_single_file_completion(
        ledger, plan, reconciliation, verification.verdict, adjudicate_run,
    )
    assert reconciliation.verdict == "expected"
    assert reconciliation.unexpected_changes == ()
    assert verification.verdict.outcome == "pass"
    assert completion.completion.outcome == "completed"
    assert completion.completion.no_project_side_effect is False
    assert ledger.get_head_revision("AuthorizationTicket", ticket.meta.object_id) == 2
    assert ledger.get_head_revision("ActionReceipt", result.receipt.meta.object_id) == 2
    ledger.close()


def test_no_ticket_means_no_write(tmp_path):
    repo, ledger, before, plan, _, task_run = _prepared(tmp_path)

    with pytest.raises(ContractInvalid, match="AuthorizationTicket is required"):
        execute_single_file_create(ledger, str(repo), plan, None, before, "e5-no-ticket", task_run)

    assert not (repo / "notes" / "welcome.txt").exists()
    ledger.close()


def test_snapshot_drift_rejects_old_plan_without_writing_target(tmp_path):
    repo, ledger, before, plan, ticket, task_run = _prepared(tmp_path)
    (repo / "unrelated.txt").write_text("drift\n", encoding="utf-8")
    drifted = create_project_snapshot(
        "rb-1", "task-1", "run-1", "project-1", "corr-1", str(repo),
        snapshot_id="task-1:snapshot:drifted",
    )

    result = execute_single_file_create(
        ledger, str(repo), plan, ticket, drifted, "e5-drift", task_run,
    )
    assert result.enforcement.decision == "deny"
    assert result.receipt is None
    assert not (repo / "notes" / "welcome.txt").exists()
    ledger.close()


def test_same_idempotency_key_does_not_repeat_write(tmp_path):
    repo, ledger, before, plan, ticket, task_run = _prepared(tmp_path)
    first = execute_single_file_create(ledger, str(repo), plan, ticket, before, "e5-repeat", task_run)
    assert first.receipt is not None and first.receipt.status == "applied"

    second = execute_single_file_create(ledger, str(repo), plan, ticket, before, "e5-repeat", task_run)
    assert second.enforcement.decision == "deny"
    assert second.receipt is None
    assert (repo / "notes" / "welcome.txt").read_text(encoding="utf-8") == "Hello from Furina Code.\n"
    ledger.close()


def test_completion_cannot_be_created_before_adjudication(tmp_path):
    repo, ledger, before, plan, ticket, task_run = _prepared(tmp_path)
    result = execute_single_file_create(ledger, str(repo), plan, ticket, before, "e5-adjudicate", task_run)
    assert result.receipt is not None
    after = create_project_snapshot("rb-1", "task-1", "run-1", "project-1", "corr-1", str(repo), snapshot_id="after")
    reconciliation = reconcile_single_file_create(ledger, str(repo), plan, result.receipt, before, after)
    verify_run = task_run.transition("I2-D", Phase.RECONCILE, Disposition.ACTIVE)
    verify_run = verify_run.transition("I2-D", Phase.VERIFY, Disposition.ACTIVE)
    verification = verify_single_file_create(ledger, plan, reconciliation, verify_run)

    with pytest.raises(ContractInvalid, match="adjudicate/active"):
        adjudicate_single_file_completion(ledger, plan, reconciliation, verification.verdict, verify_run)
    ledger.close()
