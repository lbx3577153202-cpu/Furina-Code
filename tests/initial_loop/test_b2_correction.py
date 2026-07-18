"""B2: User mid-task correction must invalidate old plan/ticket."""

import subprocess
from pathlib import Path

import pytest

from furina_code.contracts import (
    ContractInvalid,
    Disposition,
    Phase,
    TaskDossier,
    TaskRun,
)
from furina_code.initial_loop.correction import apply_user_correction
from furina_code.ledger import Ledger
from furina_code.world import create_project_snapshot
from furina_code.world.controlled_write import (
    bind_single_file_create,
    evaluate_single_file_authorization,
    execute_single_file_create,
    issue_single_file_ticket,
    write_e5_object,
)


def _repo(root: Path, name: str) -> Path:
    repo = root / name
    repo.mkdir()
    for args in (("init",), ("config", "user.email", "corr@test"),
                 ("config", "user.name", "Corr")):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "README.md").write_bytes(b"fixture\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True, text=True)
    return repo


def _setup_with_dossier(tmp_path, target="welcome.txt"):
    """Set up repo, ledger, dossier, run, plan, ticket for correction tests."""
    repo = _repo(tmp_path, "repo")
    ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
    ledger.open()

    # Create TaskDossier via ledger directly (not through write_e5_object)
    dossier = TaskDossier.create(
        run_binding_id="rb-corr", task_id="task-corr", task_run_id="run-corr",
        project_ref="project-corr", correlation_id="corr-corr",
        source_intent_ref="intent:original", structured_goal="Create file",
        success_criteria=("file created",), scope=("notes/",), exclusions=(),
        unknowns=(), risk_class="low", user_constraints=(),
    )
    ledger.write_object(dossier.meta, {
        "source_intent_ref": dossier.source_intent_ref,
        "structured_goal": dossier.structured_goal,
        "success_criteria": list(dossier.success_criteria),
        "scope": list(dossier.scope),
        "exclusions": list(dossier.exclusions),
        "unknowns": list(dossier.unknowns),
        "risk_class": dossier.risk_class,
        "user_constraints": list(dossier.user_constraints),
        "status": dossier.status.value,
    }, dossier.meta.owner_organ, 0)

    # Create TaskRun
    run = TaskRun.create("rb-corr", "task-corr", "run-corr", "project-corr", "corr-corr", 1)
    write_e5_object(ledger, run, 0)
    run = run.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
    write_e5_object(ledger, run, run.meta.revision - 1)

    # Observe
    before = create_project_snapshot(
        "rb-corr", "task-corr", "run-corr", "project-corr", "corr-corr", str(repo),
        snapshot_id="task-corr:snapshot:before",
    )
    write_e5_object(ledger, before, 0)

    # Plan
    run = run.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE,
                         current_refs=(before.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)
    plan = bind_single_file_create(before, "candidate:corr", "original content\n",
                                    target_path=f"notes/{target}")
    write_e5_object(ledger, plan, 0)

    # Authorize
    run = run.transition("I2-D", Phase.AUTHORIZE, Disposition.ACTIVE,
                         current_refs=(plan.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)
    decision = evaluate_single_file_authorization(plan, "user", ("user:corr",))
    write_e5_object(ledger, decision, 0)
    ticket = issue_single_file_ticket(decision, plan)
    write_e5_object(ledger, ticket, 0)

    return repo, ledger, run, plan, ticket


class TestB2Correction:

    def test_correction_revokes_old_ticket(self, tmp_path):
        repo, ledger, run, plan, ticket = _setup_with_dossier(tmp_path)

        # Correct to different target
        result = apply_user_correction(
            ledger, run, plan, ticket,
            new_structured_goal="Create greeting",
            new_success_criteria=("greeting.txt created",),
            new_scope=("notes/",), new_exclusions=(), new_unknowns=(),
            new_risk_class="low", new_user_constraints=(),
            correction_source_ref="user:correction:1",
        )

        # Ticket revoked
        assert result.revoked_ticket.status == "consumed"

        # Act phase - try to execute with old ticket
        # First transition back to active, then to act
        run = result.updated_run
        if run.disposition == Disposition.WAITING_USER:
            old_rev = run.meta.revision
            run = run.transition("I2-D", run.phase, Disposition.ACTIVE,
                                 current_refs=(ticket.meta.integrity_ref,))
            write_e5_object(ledger, run, old_rev)
        old_rev = run.meta.revision
        run = run.transition("I2-D", Phase.ACT, Disposition.ACTIVE,
                             current_refs=(ticket.meta.integrity_ref,))
        write_e5_object(ledger, run, old_rev)

        act_time = create_project_snapshot(
            "rb-corr", "task-corr", "run-corr", "project-corr", "corr-corr", str(repo),
            snapshot_id="task-corr:snapshot:act",
        )
        write_e5_object(ledger, act_time, 0)

        exec_result = execute_single_file_create(
            ledger, str(repo), plan, ticket, act_time, "key-corr", run,
        )
        assert exec_result.enforcement.decision == "deny"
        assert "not active" in exec_result.enforcement.reason
        assert not (repo / "notes" / "welcome.txt").exists()
        ledger.close()

    def test_old_ticket_cannot_create_after_correction(self, tmp_path):
        repo, ledger, run, plan, ticket = _setup_with_dossier(tmp_path)

        corr_result = apply_user_correction(
            ledger, run, plan, ticket,
            new_structured_goal="changed", new_success_criteria=(), new_scope=("notes/",),
            new_exclusions=(), new_unknowns=(), new_risk_class="low",
            new_user_constraints=(), correction_source_ref="user:reg",
        )

        run = corr_result.updated_run
        if run.disposition == Disposition.WAITING_USER:
            old_rev = run.meta.revision
            run = run.transition("I2-D", run.phase, Disposition.ACTIVE,
                                 current_refs=(ticket.meta.integrity_ref,))
            write_e5_object(ledger, run, old_rev)
        old_rev = run.meta.revision
        run = run.transition("I2-D", Phase.ACT, Disposition.ACTIVE,
                             current_refs=(ticket.meta.integrity_ref,))
        write_e5_object(ledger, run, old_rev)

        act_time = create_project_snapshot(
            "rb-corr", "task-corr", "run-corr", "project-corr", "corr-corr", str(repo),
            snapshot_id="task-corr:snapshot:act",
        )
        write_e5_object(ledger, act_time, 0)

        result = execute_single_file_create(
            ledger, str(repo), plan, ticket, act_time, "key-reg", run,
        )
        assert result.enforcement.decision == "deny"
        ledger.close()

    def test_correction_requires_new_plan_for_new_target(self, tmp_path):
        """After correction, old plan cannot execute; new plan needed."""
        repo, ledger, run, plan, ticket = _setup_with_dossier(tmp_path, "welcome.txt")

        corr_result = apply_user_correction(
            ledger, run, plan, ticket,
            new_structured_goal="Create greeting", new_success_criteria=("done",),
            new_scope=("notes/",), new_exclusions=(), new_unknowns=(),
            new_risk_class="low", new_user_constraints=(),
            correction_source_ref="user:corr:new",
        )

        # Old plan for welcome.txt should fail (ticket revoked)
        run = corr_result.updated_run
        if run.disposition == Disposition.WAITING_USER:
            old_rev = run.meta.revision
            run = run.transition("I2-D", run.phase, Disposition.ACTIVE,
                                 current_refs=(ticket.meta.integrity_ref,))
            write_e5_object(ledger, run, old_rev)
        old_rev = run.meta.revision
        run = run.transition("I2-D", Phase.ACT, Disposition.ACTIVE,
                             current_refs=(ticket.meta.integrity_ref,))
        write_e5_object(ledger, run, old_rev)
        act_time = create_project_snapshot(
            "rb-corr", "task-corr", "run-corr", "project-corr", "corr-corr", str(repo),
            snapshot_id="task-corr:snapshot:act2",
        )
        write_e5_object(ledger, act_time, 0)
        result = execute_single_file_create(
            ledger, str(repo), plan, ticket, act_time, "key-new", run,
        )
        assert result.enforcement.decision == "deny"

        # New plan requires fresh observation and new ticket
        # (just verify old plan is denied - full cycle test is separate)
        assert not (repo / "notes" / "welcome.txt").exists()
        ledger.close()
