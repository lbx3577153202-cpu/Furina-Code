"""B2: User mid-task correction must invalidate old plan/ticket.

Tests:
1. Correction validates binding consistency (same task/binding)
2. Old ticket is revoked and cannot execute
3. New plan/ticket for corrected target can complete
4. Full correction cycle proves end-to-end closure
"""

import subprocess
from pathlib import Path

import pytest

from datetime import timedelta

from furina_code.contracts import (
    AuthorizationTicket,
    ContractInvalid,
    Disposition,
    Phase,
    TaskDossier,
    TaskRun,
)
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
    """Set up repo, ledger, dossier, run, plan, ticket."""
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
        "scope": list(dossier.scope),
        "exclusions": list(dossier.exclusions),
        "unknowns": list(dossier.unknowns),
        "risk_class": dossier.risk_class,
        "user_constraints": list(dossier.user_constraints),
        "status": dossier.status.value,
    }, dossier.meta.owner_organ, 0)

    run = TaskRun.create("rb-corr", "task-corr", "run-corr", "project-corr", "corr-corr", 1)
    write_e5_object(ledger, run, 0)
    run = run.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
    write_e5_object(ledger, run, run.meta.revision - 1)

    before = create_project_snapshot(
        "rb-corr", "task-corr", "run-corr", "project-corr", "corr-corr", str(repo),
        snapshot_id="task-corr:snapshot:before",
    )
    write_e5_object(ledger, before, 0)

    run = run.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE,
                         current_refs=(before.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)
    plan = bind_single_file_create(before, "candidate:corr", "original content\n",
                                    target_path=f"notes/{target}")
    write_e5_object(ledger, plan, 0)

    run = run.transition("I2-D", Phase.AUTHORIZE, Disposition.ACTIVE,
                         current_refs=(plan.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)
    decision = evaluate_single_file_authorization(plan, "user", ("user:corr",))
    write_e5_object(ledger, decision, 0)
    ticket = issue_single_file_ticket(decision, plan)
    write_e5_object(ledger, ticket, 0)

    return repo, ledger, run, plan, ticket


def _transition_to_act(ledger, run, ticket_ref):
    """Transition run through waiting_user -> active -> act."""
    if run.disposition == Disposition.WAITING_USER:
        old_rev = run.meta.revision
        run = run.transition("I2-D", run.phase, Disposition.ACTIVE,
                             current_refs=(ticket_ref,))
        write_e5_object(ledger, run, old_rev)
    old_rev = run.meta.revision
    run = run.transition("I2-D", Phase.ACT, Disposition.ACTIVE,
                         current_refs=(ticket_ref,))
    write_e5_object(ledger, run, old_rev)
    return run


class TestB2Correction:

    def test_correction_revokes_old_ticket(self, tmp_path):
        """After correction, old ticket cannot execute."""
        repo, ledger, run, plan, ticket = _setup_with_dossier(tmp_path)

        result = apply_user_correction(
            ledger, run, plan, ticket,
            new_structured_goal="Create greeting",
            new_success_criteria=("greeting.txt created",),
            new_scope=("notes/",), new_exclusions=(), new_unknowns=(),
            new_risk_class="low", new_user_constraints=(),
            correction_source_ref="user:correction:1",
        )

        assert result.revoked_ticket.status == "consumed"

        run = _transition_to_act(ledger, result.updated_run, ticket.meta.integrity_ref)
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

    def test_correction_validates_binding_consistency(self, tmp_path):
        """Correction rejects mismatched run/plan/ticket bindings."""
        repo, ledger, run, plan, ticket = _setup_with_dossier(tmp_path)

        # Create a plan from a different binding
        from furina_code.contracts import BoundActionPlan
        foreign_plan = BoundActionPlan.create(
            "rb-foreign", "task-foreign", "run-foreign", "project-foreign", "corr-foreign",
            "candidate:foreign", 1, "sha256:snap", "sha256:abc", ("notes/",),
            ({"kind": "create_file", "path": "notes/x.txt", "content": "x\n"},),
            {"created_path": "notes/x.txt"}, "low", "remove", ("baseline_clean",),
        )

        with pytest.raises(ContractInvalid, match="same binding"):
            apply_user_correction(
                ledger, run, foreign_plan, ticket,
                new_structured_goal="x", new_success_criteria=(), new_scope=("notes/",),
                new_exclusions=(), new_unknowns=(), new_risk_class="low",
                new_user_constraints=(), correction_source_ref="user:bad",
            )
        ledger.close()

    def test_correction_rejects_ticket_not_bound_to_plan(self, tmp_path):
        """Correction rejects ticket that doesn't reference the plan."""
        repo, ledger, run, plan, ticket = _setup_with_dossier(tmp_path)

        from furina_code.contracts import AuthorizationTicket
        from furina_code.contracts.meta import now_utc
        from datetime import timedelta
        foreign_ticket = AuthorizationTicket.create(
            "rb-corr", "task-corr", "run-corr", "project-corr", "corr-corr",
            "decision:foreign", "sha256:foreign_plan", 1,
            "sha256:snap", ("notes/",), now_utc(), now_utc() + timedelta(seconds=300),
        )

        with pytest.raises(ContractInvalid, match="reference the plan"):
            apply_user_correction(
                ledger, run, plan, foreign_ticket,
                new_structured_goal="x", new_success_criteria=(), new_scope=("notes/",),
                new_exclusions=(), new_unknowns=(), new_risk_class="low",
                new_user_constraints=(), correction_source_ref="user:bad",
            )
        ledger.close()

    def test_full_correction_cycle_completes(self, tmp_path):
        """Full cycle: correct -> old denied -> new plan -> new ticket -> complete."""
        repo, ledger, run, plan, ticket = _setup_with_dossier(tmp_path, "welcome.txt")

        corr_result = apply_user_correction(
            ledger, run, plan, ticket,
            new_structured_goal="Create greeting", new_success_criteria=("done",),
            new_scope=("notes/",), new_exclusions=(), new_unknowns=(),
            new_risk_class="low", new_user_constraints=(),
            correction_source_ref="user:corr:new",
        )

        # Step 1: Old plan denied
        run = _transition_to_act(ledger, corr_result.updated_run, ticket.meta.integrity_ref)
        act_time = create_project_snapshot(
            "rb-corr", "task-corr", "run-corr", "project-corr", "corr-corr", str(repo),
            snapshot_id="task-corr:snapshot:act2",
        )
        write_e5_object(ledger, act_time, 0)
        result = execute_single_file_create(
            ledger, str(repo), plan, ticket, act_time, "key-old", run,
        )
        assert result.enforcement.decision == "deny"

        # Step 2: New plan for greeting.txt requires fresh observation
        # Use the act_time snapshot (which observed the workspace after correction)
        new_plan = bind_single_file_create(
            act_time, "candidate:new", "New greeting\n", target_path="notes/greeting.txt",
        )
        new_decision = evaluate_single_file_authorization(new_plan, "user", ("user:corr",))
        # Use unique ticket ID to avoid collision with old ticket
        new_ticket = AuthorizationTicket.create(
            "rb-corr", "task-corr", "run-corr", "project-corr", "corr-corr",
            new_decision.meta.integrity_ref, new_plan.meta.integrity_ref,
            new_plan.task_revision, act_time.meta.integrity_ref,
            new_plan.target_scope, now_utc(), now_utc() + timedelta(seconds=300),
            ticket_id="task-corr:authorization-ticket:new",
        )
        write_e5_object(ledger, new_ticket, 0)
        result2 = execute_single_file_create(
            ledger, str(repo), new_plan, new_ticket, act_time, "key-new", run,
        )
        assert result2.enforcement.decision == "allow"
        assert (repo / "notes" / "greeting.txt").read_bytes() == b"New greeting\n"
        ledger.close()
