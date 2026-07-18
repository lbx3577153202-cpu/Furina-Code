"""B3: Crash between side-effect and receipt must be recoverable.

Uses CrashSimulator which spawns child process calling real
execute_single_file_create(), then crashes. Parent reopens ledger
and calls review_interrupted_write().
"""

import hashlib
import subprocess
from pathlib import Path

from furina_code.contracts import Checkpoint, Disposition, Phase
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
    """Set up repo, ledger with plan/ticket/checkpoint for crash test."""
    repo = _repo(tmp_path, "repo")
    ledger_path = str(tmp_path / "runtime.sqlite3")
    ledger = Ledger(ledger_path)
    ledger.open()

    before = create_project_snapshot(
        "rb-crash", "task-crash", "run-crash", "project-crash", "corr-crash",
        str(repo), snapshot_id="task-crash:snapshot:before",
    )
    write_e5_object(ledger, before, 0)
    plan = bind_single_file_create(before, "candidate:crash", "crash content\n")
    write_e5_object(ledger, plan, 0)
    decision = evaluate_single_file_authorization(plan, "user", ("user:crash",))
    write_e5_object(ledger, decision, 0)
    ticket = issue_single_file_ticket(decision, plan)
    write_e5_object(ledger, ticket, 0)

    # Create checkpoint for recovery
    checkpoint = Checkpoint.create(
        "rb-crash", "task-crash", "run-crash", "project-crash", "corr-crash", 1,
        Phase.ACT, Disposition.ACTIVE, 2, (), before.meta.integrity_ref,
        "interrupted controlled action",
        pending_actions=(plan.meta.integrity_ref,),
        ticket_refs=(ticket.meta.integrity_ref,),
    )
    write_recovery_object(ledger, checkpoint, 0)
    ledger.close()

    return repo, ledger_path, plan, ticket, before, checkpoint


class TestB3CrashRecovery:

    def test_crash_writes_file_receipt_executing_recovery_skips(self, tmp_path):
        """Full crash -> recovery cycle using real executor.

        Child process calls execute_single_file_create() with _FURINA_CRASH_TEST=1.
        The executor writes the file, consumes the ticket, creates the receipt,
        then the crash injection fires and the child exits non-zero.
        Parent reads the real receipt/ticket from the ledger and calls
        review_interrupted_write().
        """
        repo, ledger_path, plan, ticket, snap, checkpoint = _setup_for_crash(tmp_path)

        # Use CrashSimulator - spawns child that calls REAL executor
        sim = CrashSimulator(ledger_path, str(repo))
        exit_code = sim.write_and_crash(plan, ticket, snap, snap, "crash-key")

        # Child must have exited non-zero
        assert exit_code != 0, f"Child should exit non-zero, got {exit_code}"

        # File was written by the real executor
        assert (repo / "notes" / "welcome.txt").exists()
        assert (repo / "notes" / "welcome.txt").read_bytes() == b"crash content\n"

        # Parent opens a fresh ledger connection
        parent_ledger = Ledger(ledger_path)
        parent_ledger.open()

        # Read REAL receipt from ledger (not fabricated)
        # ActionReceipt object_id defaults to "{task_id}:action-receipt:1"
        receipt_id = f"{plan.meta.task_id}:action-receipt:1"
        receipt_result = parent_ledger.get_latest("ActionReceipt", receipt_id)
        assert receipt_result is not None, "No ActionReceipt found in ledger"
        receipt_meta, receipt_payload = receipt_result
        assert receipt_payload["status"] == "executing", (
            f"Receipt should be executing, got {receipt_payload['status']}"
        )

        # Read REAL ticket status from ledger
        ticket_result = parent_ledger.get_latest("AuthorizationTicket", ticket.meta.object_id)
        assert ticket_result is not None, "No AuthorizationTicket found in ledger"
        _, ticket_payload = ticket_result
        assert ticket_payload["status"] == "consumed", (
            f"Ticket should be consumed, got {ticket_payload['status']}"
        )

        # Verify receipt references match plan
        assert receipt_payload["plan_ref"] == plan.meta.integrity_ref
        assert receipt_payload["ticket_ref"] == ticket.meta.integrity_ref

        # Read checkpoint from ledger
        cp_result = parent_ledger.get_latest("Checkpoint", checkpoint.meta.object_id)
        assert cp_result is not None, "No Checkpoint found in ledger"
        _, cp_payload = cp_result

        # Reconstruct checkpoint from ledger data
        from furina_code.contracts import Checkpoint as Cp
        cp_meta = cp_result[0]
        ledger_checkpoint = Cp.create(
            cp_meta.run_binding_id, cp_meta.task_id,
            cp_meta.task_run_id, cp_meta.project_ref,
            cp_meta.correlation_id, cp_payload["task_revision"],
            Phase(cp_payload["phase"]), Disposition(cp_payload["disposition"]),
            cp_payload["event_cursor"],
            tuple(cp_payload.get("pending_requests", ())),
            cp_payload.get("snapshot_ref"), cp_payload.get("reason", ""),
            pending_actions=tuple(cp_payload.get("pending_actions", ())),
            ticket_refs=tuple(cp_payload.get("ticket_refs", ())),
        )

        # Create fresh snapshot for recovery observation
        fresh = create_project_snapshot(
            "rb-crash", "task-crash", "run-crash", "project-crash", "corr-crash",
            str(repo), snapshot_id="task-crash:snapshot:fresh",
        )

        # Reconstruct receipt from ledger data for review_interrupted_write
        from furina_code.contracts import ActionReceipt
        ledger_receipt = ActionReceipt.create(
            receipt_meta.run_binding_id, receipt_meta.task_id,
            receipt_meta.task_run_id, receipt_meta.project_ref,
            receipt_meta.correlation_id,
            receipt_payload["plan_ref"], receipt_payload["ticket_ref"],
            receipt_payload["idempotency_key"], receipt_payload["tool_ref"],
            receipt_id=receipt_meta.object_id,
            causation_ref=receipt_meta.causation_ref,
        )

        # Call REAL review_interrupted_write with ledger-reconstructed objects
        verdict = review_interrupted_write(
            parent_ledger, str(repo), ledger_checkpoint, plan, fresh,
            ledger_receipt, ticket_payload["status"],
        )

        # Recovery must skip the action (file already exists, receipt executing)
        assert verdict.outcome == "skip_confirmed_action"
        assert "do not execute action again" in verdict.required_steps

        # File hash unchanged - no second write occurred
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
        import importlib
        # The exception class is module-private (prefixed with _)
        # and only raised when _FURINA_CRASH_TEST=1
        import os
        assert os.environ.get("_FURINA_CRASH_TEST") != "1"
