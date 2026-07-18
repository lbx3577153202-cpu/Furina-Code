"""B2: User mid-task correction with atomic guarantees and full cycle."""

import subprocess
from datetime import timedelta
from pathlib import Path

import pytest

from furina_code.contracts import (
    AuthorizationTicket,
    ContractInvalid,
    Disposition,
    Phase,
    TaskDossier,
    TaskRun,
)
from furina_code.contracts.errors import LedgerWriteFailed
from furina_code.contracts.meta import now_utc
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
    repo = _repo(tmp_path, "repo")
    ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
    ledger.open()

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
        "scope": list(dossier.scope), "exclusions": list(dossier.exclusions),
        "unknowns": list(dossier.unknowns), "risk_class": dossier.risk_class,
        "user_constraints": list(dossier.user_constraints),
        "status": dossier.status.value,
    }, dossier.meta.owner_organ, 0)

    before = create_project_snapshot(
        "rb-corr", "task-corr", "run-corr", "project-corr", "corr-corr", str(repo),
        snapshot_id="task-corr:snapshot:before",
    )

    plan = bind_single_file_create(before, "candidate:corr", "original content\n",
                                    target_path=f"notes/{target}")
    decision = evaluate_single_file_authorization(plan, "user", ("user:corr",))
    ticket = issue_single_file_ticket(decision, plan)

    run = TaskRun.create("rb-corr", "task-corr", "run-corr", "project-corr", "corr-corr", 1)
    write_e5_object(ledger, run, 0)
    run = run.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
    write_e5_object(ledger, run, run.meta.revision - 1)
    before_written = create_project_snapshot(
        "rb-corr", "task-corr", "run-corr", "project-corr", "corr-corr", str(repo),
        snapshot_id="task-corr:snapshot:observe",
    )
    write_e5_object(ledger, before_written, 0)
    run = run.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE,
                         current_refs=(before_written.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)
    write_e5_object(ledger, plan, 0)
    run = run.transition("I2-D", Phase.AUTHORIZE, Disposition.ACTIVE,
                         current_refs=(plan.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)
    write_e5_object(ledger, decision, 0)
    write_e5_object(ledger, ticket, 0)
    run = run.transition("I2-D", Phase.ACT, Disposition.ACTIVE,
                         current_refs=(ticket.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)

    return repo, ledger, run, plan, ticket


class TestB2Correction:

    def test_binding_validation_rejects_mismatch(self, tmp_path):
        """Correction rejects run/plan/ticket with different bindings."""
        repo, ledger, run, plan, ticket = _setup_with_dossier(tmp_path)

        # Different project_ref
        from furina_code.contracts import BoundActionPlan
        foreign_plan = BoundActionPlan.create(
            "rb-corr", "task-corr", "run-corr", "WRONG-project", "corr-corr",
            "candidate:x", 1, "sha256:" + "a" * 64, "sha256:" + "b" * 64,
            ("notes/",), ({"kind": "create_file", "path": "notes/x.txt", "content": "x\n"},),
            {"created_path": "notes/x.txt"}, "low", "remove", ("baseline_clean",),
        )

        with pytest.raises(ContractInvalid):
            apply_user_correction(
                ledger, run, foreign_plan, ticket,
                new_structured_goal="x", new_success_criteria=(), new_scope=("notes/",),
                new_exclusions=(), new_unknowns=(), new_risk_class="low",
                new_user_constraints=(), correction_source_ref="user:x",
            )
        ledger.close()

    def test_atomic_failure_leaves_no_side_effects(self, tmp_path):
        """If write_objects_atomic fails mid-batch, all heads and revisions unchanged."""
        repo, ledger, run, plan, ticket = _setup_with_dossier(tmp_path)
        dossier_head_before = ledger.get_head_revision("TaskDossier", "task-corr")
        ticket_head_before = ledger.get_head_revision("AuthorizationTicket", ticket.meta.object_id)
        run_head_before = ledger.get_head_revision("TaskRun", "run-corr")

        # Inject failure after 1st object written (dossier succeeds, ticket fails)
        ledger._atomic_fail_after = 1

        from furina_code.contracts.errors import LedgerWriteFailed
        with pytest.raises((LedgerWriteFailed, ContractInvalid)):
            apply_user_correction(
                ledger, run, plan, ticket,
                new_structured_goal="x", new_success_criteria=(), new_scope=("notes/",),
                new_exclusions=(), new_unknowns=(), new_risk_class="low",
                new_user_constraints=(), correction_source_ref="user:atomic",
            )

        # All heads must be unchanged (transaction rolled back)
        assert ledger.get_head_revision("TaskDossier", "task-corr") == dossier_head_before
        assert ledger.get_head_revision("AuthorizationTicket", ticket.meta.object_id) == ticket_head_before
        assert ledger.get_head_revision("TaskRun", "run-corr") == run_head_before
        ledger._atomic_fail_after = -1
        ledger.close()

    def test_old_ticket_rejected_after_correction(self, tmp_path):
        """After correction, old ticket is consumed and cannot execute."""
        repo, ledger, run, plan, ticket = _setup_with_dossier(tmp_path)

        apply_user_correction(
            ledger, run, plan, ticket,
            new_structured_goal="Create greeting", new_success_criteria=("done",),
            new_scope=("notes/",), new_exclusions=(), new_unknowns=(),
            new_risk_class="low", new_user_constraints=(),
            correction_source_ref="user:corr:1",
        )

        # Verify old ticket is consumed via ledger
        _, ticket_payload = ledger.get_latest("AuthorizationTicket", ticket.meta.object_id)
        assert ticket_payload["status"] == "consumed"

        # Verify old ticket cannot execute
        fresh = create_project_snapshot(
            "rb-corr", "task-corr", "run-corr", "project-corr", "corr-corr", str(repo),
            snapshot_id="task-corr:snapshot:check",
        )
        result = execute_single_file_create(
            ledger, str(repo), plan, ticket, fresh, "key-old", run,
        )
        assert result.enforcement.decision == "deny"
        assert "not active" in result.enforcement.reason
        assert not (repo / "notes" / "welcome.txt").exists()
        ledger.close()

    def test_full_correction_cycle_creates_new_target(self, tmp_path):
        """Full cycle: correct -> old denied -> new observation -> new plan -> complete.

        All new objects share the same task_run_id ("run-corr-new").
        """
        repo, ledger, run, plan, ticket = _setup_with_dossier(tmp_path, "welcome.txt")

        corr_result = apply_user_correction(
            ledger, run, plan, ticket,
            new_structured_goal="Create greeting", new_success_criteria=("done",),
            new_scope=("notes/",), new_exclusions=(), new_unknowns=(),
            new_risk_class="low", new_user_constraints=(),
            correction_source_ref="user:corr:2",
        )

        # Step 1: Old ticket consumed
        _, revoked = ledger.get_latest("AuthorizationTicket", ticket.meta.object_id)
        assert revoked["status"] == "consumed"

        # Step 2: New observation (with new task_run_id)
        new_run_id = "run-corr-new"
        new_before = create_project_snapshot(
            "rb-corr", "task-corr", new_run_id, "project-corr", "corr-corr", str(repo),
            snapshot_id="task-corr:snapshot:new-observe",
        )
        write_e5_object(ledger, new_before, 0)

        # Step 3: New plan (inherits task_run_id from snapshot = new_run_id)
        new_plan = bind_single_file_create(
            new_before, "candidate:new", "New greeting content\n",
            target_path="notes/greeting.txt",
            plan_id="task-corr:action-plan:post-corr",
        )
        write_e5_object(ledger, new_plan, 0)

        # Step 4: New authorization decision
        new_decision = evaluate_single_file_authorization(
            new_plan, "user", ("user:corr",),
            decision_id="task-corr:authorization-decision:post-corr",
        )
        write_e5_object(ledger, new_decision, 0)

        # Step 5: New ticket (shares task_run_id via plan)
        new_ticket = AuthorizationTicket.create(
            "rb-corr", "task-corr", new_run_id, "project-corr", "corr-corr",
            new_decision.meta.integrity_ref, new_plan.meta.integrity_ref,
            new_plan.task_revision, new_before.meta.integrity_ref,
            new_plan.target_scope, now_utc(), now_utc() + timedelta(seconds=300),
            ticket_id="task-corr:authorization-ticket:post-corr",
        )
        write_e5_object(ledger, new_ticket, 0)

        # Step 6: New act/active run (same task_run_id as plan/ticket)
        new_run = TaskRun.create(
            "rb-corr", "task-corr", new_run_id, "project-corr", "corr-corr", 1,
        )
        write_e5_object(ledger, new_run, 0)
        new_run = new_run.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        write_e5_object(ledger, new_run, new_run.meta.revision - 1)
        new_run = new_run.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE,
                                     current_refs=(new_before.meta.integrity_ref,))
        write_e5_object(ledger, new_run, new_run.meta.revision - 1)
        new_run = new_run.transition("I2-D", Phase.AUTHORIZE, Disposition.ACTIVE,
                                     current_refs=(new_plan.meta.integrity_ref,))
        write_e5_object(ledger, new_run, new_run.meta.revision - 1)
        new_run = new_run.transition("I2-D", Phase.ACT, Disposition.ACTIVE,
                                     current_refs=(new_ticket.meta.integrity_ref,))
        write_e5_object(ledger, new_run, new_run.meta.revision - 1)

        # Step 7: Execute and complete
        act_time = create_project_snapshot(
            "rb-corr", "task-corr", new_run_id, "project-corr", "corr-corr", str(repo),
            snapshot_id="task-corr:snapshot:new-act",
        )
        write_e5_object(ledger, act_time, 0)

        result = execute_single_file_create(
            ledger, str(repo), new_plan, new_ticket, act_time, "key-new", new_run,
        )
        assert result.enforcement.decision == "allow"
        assert result.receipt is not None
        assert result.receipt.status == "applied"
        assert (repo / "notes" / "greeting.txt").read_bytes() == b"New greeting content\n"
        ledger.close()

    def test_atomic_failure_at_second_object(self, tmp_path):
        """If write_objects_atomic fails after 2nd object, all heads unchanged."""
        repo, ledger, run, plan, ticket = _setup_with_dossier(tmp_path)
        dossier_head = ledger.get_head_revision("TaskDossier", "task-corr")
        ticket_head = ledger.get_head_revision("AuthorizationTicket", ticket.meta.object_id)
        run_head = ledger.get_head_revision("TaskRun", "run-corr")

        # Fail after 2 objects (dossier + ticket written, run fails)
        ledger._atomic_fail_after = 2

        with pytest.raises((LedgerWriteFailed, ContractInvalid)):
            apply_user_correction(
                ledger, run, plan, ticket,
                new_structured_goal="x", new_success_criteria=(), new_scope=("notes/",),
                new_exclusions=(), new_unknowns=(), new_risk_class="low",
                new_user_constraints=(), correction_source_ref="user:atomic2",
            )

        # All heads unchanged (transaction rolled back)
        assert ledger.get_head_revision("TaskDossier", "task-corr") == dossier_head
        assert ledger.get_head_revision("AuthorizationTicket", ticket.meta.object_id) == ticket_head
        assert ledger.get_head_revision("TaskRun", "run-corr") == run_head
        ledger._atomic_fail_after = -1
        ledger.close()

    @pytest.mark.parametrize("field,bad_value", [
        ("run_binding_id", "rb-OTHER"),
        ("task_id", "task-OTHER"),
        ("task_run_id", "run-OTHER"),
        ("project_ref", "project-OTHER"),
        ("correlation_id", "corr-OTHER"),
    ])
    def test_executor_rejects_each_binding_field(self, tmp_path, field, bad_value):
        """Executor denies when any of the 5 binding fields mismatches."""
        repo, ledger, run, plan, ticket = _setup_with_dossier(tmp_path)

        # Create run with one bad field
        kwargs = {
            "run_binding_id": "rb-corr",
            "task_id": "task-corr",
            "task_run_id": "run-corr",
            "project_ref": "project-corr",
            "correlation_id": "corr-corr",
        }
        kwargs[field] = bad_value
        mismatched_run = TaskRun.create(**kwargs, task_revision=1)
        mismatched_run = mismatched_run.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        mismatched_run = mismatched_run.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE)
        mismatched_run = mismatched_run.transition("I2-D", Phase.AUTHORIZE, Disposition.ACTIVE)
        mismatched_run = mismatched_run.transition("I2-D", Phase.ACT, Disposition.ACTIVE)

        fresh = create_project_snapshot(
            "rb-corr", "task-corr", "run-corr", "project-corr", "corr-corr", str(repo),
            snapshot_id="task-corr:snapshot:mismatch",
        )
        result = execute_single_file_create(
            ledger, str(repo), plan, ticket, fresh, f"key-{field}", mismatched_run,
        )
        assert result.enforcement.decision == "deny"
        assert field in result.enforcement.reason
        assert not (repo / "notes" / "welcome.txt").exists()
        ledger.close()
