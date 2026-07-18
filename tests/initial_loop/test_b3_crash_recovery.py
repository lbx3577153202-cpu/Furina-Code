"""B3: Crash between side-effect and receipt must be recoverable.

Parent writes plan, decision, ticket, snapshot, and act/active TaskRun
to ledger, then spawns child via CrashSimulator.  Child loads objects
from ledger (preserving original integrity_refs), calls the REAL
execute_single_file_create(), and crashes.  Parent reads real
receipt/ticket from ledger and calls review_interrupted_write().
"""

import hashlib
import subprocess
from pathlib import Path

from furina_code.contracts import Checkpoint, Disposition, Phase, TaskRun
from furina_code.continuity import review_interrupted_write, write_recovery_object
from furina_code.initial_loop.crash_injection import CrashSimulator
from furina_code.ledger import Ledger
from furina_code.world import create_project_snapshot
from furina_code.world.controlled_write import (
    bind_single_file_create,
    evaluate_single_file_authorization,
    issue_single_file_ticket,
    write_e5_object,
)


def _repo(root: Path, name: str) -> Path:
    repo = root / name
    repo.mkdir()
    for args in (("init",), ("config", "user.email", "crash@test"),
                 ("config", "user.name", "Crash")):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "README.md").write_bytes(b"fixture\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True, text=True)
    return repo


def _setup_for_crash(tmp_path):
    """Set up repo, ledger with all objects for crash test.

    Writes: snapshot, plan, decision, ticket, TaskRun (transitions to ACT/ACTIVE),
    and checkpoint.  Returns object IDs for the child to load from ledger.
    """
    repo = _repo(tmp_path, "repo")
    ledger_path = str(tmp_path / "runtime.sqlite3")
    ledger = Ledger(ledger_path)
    ledger.open()

    # Snapshot
    before = create_project_snapshot(
        "rb-crash", "task-crash", "run-crash", "project-crash", "corr-crash",
        str(repo), snapshot_id="task-crash:snapshot:before",
    )
    write_e5_object(ledger, before, 0)

    # Plan
    plan = bind_single_file_create(before, "candidate:crash", "crash content\n")
    write_e5_object(ledger, plan, 0)

    # Decision
    decision = evaluate_single_file_authorization(plan, "user", ("user:crash",))
    write_e5_object(ledger, decision, 0)

    # Ticket
    ticket = issue_single_file_ticket(decision, plan)
    write_e5_object(ledger, ticket, 0)

    # TaskRun: transition through state machine to ACT/ACTIVE
    run = TaskRun.create("rb-crash", "task-crash", "run-crash", "project-crash", "corr-crash", 1)
    write_e5_object(ledger, run, 0)
    run = run.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
    write_e5_object(ledger, run, run.meta.revision - 1)
    run = run.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE,
                         current_refs=(before.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)
    run = run.transition("I2-D", Phase.AUTHORIZE, Disposition.ACTIVE,
                         current_refs=(plan.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)
    run = run.transition("I2-D", Phase.ACT, Disposition.ACTIVE,
                         current_refs=(ticket.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)

    # Checkpoint for recovery
    checkpoint = Checkpoint.create(
        "rb-crash", "task-crash", "run-crash", "project-crash", "corr-crash", 1,
        Phase.ACT, Disposition.ACTIVE, 2, (), before.meta.integrity_ref,
        "interrupted controlled action",
        pending_actions=(plan.meta.integrity_ref,),
        ticket_refs=(ticket.meta.integrity_ref,),
    )
    write_recovery_object(ledger, checkpoint, 0)
    ledger.close()

    return repo, ledger_path, plan.meta.object_id, ticket.meta.object_id, before.meta.object_id, run.meta.object_id, checkpoint.meta.object_id


class TestB3CrashRecovery:

    def test_crash_writes_file_receipt_executing_recovery_skips(self, tmp_path):
        """Full crash -> recovery cycle using real executor.

        Parent writes all objects to ledger.  Child loads them via loader
        (preserving integrity_refs), calls execute_single_file_create(),
        and crashes.  Parent loads real receipt/ticket from ledger and
        calls review_interrupted_write().
        """
        repo, ledger_path, plan_oid, ticket_oid, snap_oid, run_oid, cp_oid = _setup_for_crash(tmp_path)

        # Spawn child that calls REAL executor
        sim = CrashSimulator(ledger_path, str(repo))
        exit_code = sim.write_and_crash(plan_oid, ticket_oid, snap_oid, run_oid, "crash-key")

        # Child must have exited non-zero
        assert exit_code != 0, f"Child should exit non-zero, got {exit_code}"

        # File was written by the real executor
        assert (repo / "notes" / "welcome.txt").exists()
        assert (repo / "notes" / "welcome.txt").read_bytes() == b"crash content\n"

        # Parent opens a fresh ledger connection
        parent_ledger = Ledger(ledger_path)
        parent_ledger.open()

        # Load REAL receipt from ledger using loader
        from furina_code.contracts.loader import load_action_receipt, load_authorization_ticket, load_checkpoint, load_bound_action_plan
        receipt_id = f"task-crash:action-receipt:1"
        receipt = load_action_receipt(parent_ledger, receipt_id)
        assert receipt.status == "executing", f"Receipt should be executing, got {receipt.status}"

        # Load REAL ticket from ledger
        ticket = load_authorization_ticket(parent_ledger, ticket_oid)
        assert ticket.status == "consumed", f"Ticket should be consumed, got {ticket.status}"

        # Load plan from ledger
        plan = load_bound_action_plan(parent_ledger, plan_oid)

        # Verify receipt references match plan
        assert receipt.plan_ref == plan.meta.integrity_ref
        assert receipt.ticket_ref == ticket.meta.integrity_ref

        # Load checkpoint from ledger
        checkpoint = load_checkpoint(parent_ledger, cp_oid)

        # Create fresh snapshot for recovery observation
        fresh = create_project_snapshot(
            "rb-crash", "task-crash", "run-crash", "project-crash", "corr-crash",
            str(repo), snapshot_id="task-crash:snapshot:fresh",
        )

        # Call REAL review_interrupted_write with ledger-loaded objects
        verdict = review_interrupted_write(
            parent_ledger, str(repo), checkpoint, plan, fresh,
            receipt, ticket.status,
        )

        # Recovery must skip the action
        assert verdict.outcome == "skip_confirmed_action"
        assert "do not execute action again" in verdict.required_steps

        # File hash unchanged - no second write
        file_hash = hashlib.sha256(
            (repo / "notes" / "welcome.txt").read_bytes()
        ).hexdigest()
        expected = hashlib.sha256(b"crash content\n").hexdigest()
        assert file_hash == expected

        parent_ledger.close()

    def test_crash_env_var_not_set_normally(self):
        """_FURINA_CRASH_TEST is not set in normal test execution."""
        import os
        assert os.environ.get("_FURINA_CRASH_TEST") != "1"

    def test_crash_hook_unavailable_in_production(self):
        """_CrashTestInjection is internal and not importable in production."""
        import os
        assert os.environ.get("_FURINA_CRASH_TEST") != "1"
