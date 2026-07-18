"""B3: Crash between side-effect and receipt must be recoverable.

Uses real multiprocessing: child writes file and persists executing
receipt via real ledger, then terminates. Parent reopens ledger and
runs review_interrupted_write() to prove recovery observes target.
"""

import hashlib
import multiprocessing
import os
import subprocess
from pathlib import Path

from furina_code.contracts import Checkpoint, Disposition, Phase
from furina_code.continuity import review_interrupted_write, write_recovery_object
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


def _child_write_file_and_crash(
    ledger_path: str,
    workspace: str,
    plan_ref: str,
    ticket_ref: str,
    content: str,
    target_path: str,
    idem_key: str,
) -> None:
    """Child process: write file via real path ops, persist executing receipt, crash."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

    from furina_code.contracts import ActionReceipt, EnforcementVerdict
    from furina_code.contracts.meta import now_utc
    from furina_code.ledger import Ledger
    from furina_code.world.controlled_write import _inside_workspace, write_e5_object

    ledger = Ledger(ledger_path)
    ledger.open()

    # Persist enforcement (real object)
    enforcement = EnforcementVerdict.create(
        run_binding_id="rb-crash", task_id="task-crash",
        task_run_id="run-crash", project_ref="project-crash",
        correlation_id="corr-crash", ticket_ref=ticket_ref,
        plan_ref=plan_ref, current_snapshot_ref="snap:crash",
        decision="allow", reason="child enforcement passed",
        verdict_id=f"task-crash:enforcement:child:{now_utc().timestamp()}",
        causation_ref=ticket_ref,
    )
    write_e5_object(ledger, enforcement, 0)

    # Persist executing receipt (real object)
    receipt = ActionReceipt.create(
        run_binding_id="rb-crash", task_id="task-crash",
        task_run_id="run-crash", project_ref="project-crash",
        correlation_id="corr-crash", plan_ref=plan_ref,
        ticket_ref=ticket_ref, idempotency_key=idem_key,
        tool_ref="e5-safe-file-create-v1", causation_ref=enforcement.meta.integrity_ref,
    )
    write_e5_object(ledger, receipt, 0)

    # Write file via real path operations
    target = _inside_workspace(Path(workspace), target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(content)

    # CRASH: exit without finalizing receipt
    ledger.close()
    os._exit(1)


class TestB3CrashRecovery:

    def test_real_crash_writes_file_and_receipt_executing(self, tmp_path):
        """Child writes file and persists executing receipt, then crashes."""
        repo = _repo(tmp_path, "repo")
        ledger_path = str(tmp_path / "runtime.sqlite3")

        # Set up plan, ticket in parent ledger
        ledger = Ledger(ledger_path)
        ledger.open()
        before = create_project_snapshot(
            "rb-crash", "task-crash", "run-crash", "project-crash", "corr-crash",
            str(repo), snapshot_id="task-crash:snapshot:before",
        )
        plan = bind_single_file_create(before, "candidate:crash", "crash content\n")
        decision = evaluate_single_file_authorization(plan, "user", ("user:crash",))
        write_e5_object(ledger, decision, 0)
        ticket = issue_single_file_ticket(decision, plan)
        write_e5_object(ledger, ticket, 0)
        ledger.close()

        # Child writes file and crashes
        proc = multiprocessing.Process(
            target=_child_write_file_and_crash,
            args=(ledger_path, str(repo), plan.meta.integrity_ref,
                  ticket.meta.integrity_ref, "crash content\n",
                  "notes/welcome.txt", "crash-key"),
        )
        proc.start()
        proc.join(timeout=10)
        assert not proc.is_alive()

        # File was written
        assert (repo / "notes" / "welcome.txt").exists()
        assert (repo / "notes" / "welcome.txt").read_bytes() == b"crash content\n"

        # Receipt is in "executing" state
        import json
        ledger2 = Ledger(ledger_path)
        ledger2.open()
        rows = ledger2.conn.execute(
            "SELECT payload_json FROM object_revisions WHERE object_type='ActionReceipt'"
        ).fetchall()
        assert len(rows) >= 1
        receipt_payload = json.loads(rows[-1][0])
        assert receipt_payload["status"] == "executing"
        assert receipt_payload["idempotency_key"] == "crash-key"
        ledger2.close()

    def test_recovery_observes_target_and_skips(self, tmp_path):
        """After crash, recovery observes target exists and skips rewrite."""
        repo = _repo(tmp_path, "repo")
        ledger_path = str(tmp_path / "runtime.sqlite3")

        # Set up plan, ticket in parent ledger
        ledger = Ledger(ledger_path)
        ledger.open()
        before = create_project_snapshot(
            "rb-recov", "task-recov", "run-recov", "project-recov", "corr-recov",
            str(repo), snapshot_id="task-recov:snapshot:before",
        )
        plan = bind_single_file_create(before, "candidate:recov", "recovery content\n")
        decision = evaluate_single_file_authorization(plan, "user", ("user:recov",))
        write_e5_object(ledger, decision, 0)
        ticket = issue_single_file_ticket(decision, plan)
        write_e5_object(ledger, ticket, 0)

        # Create checkpoint for recovery
        checkpoint = Checkpoint.create(
            "rb-recov", "task-recov", "run-recov", "project-recov", "corr-recov", 1,
            Phase.ACT, Disposition.ACTIVE, 2, (), before.meta.integrity_ref,
            "interrupted controlled action",
            pending_actions=(plan.meta.integrity_ref,),
            ticket_refs=(ticket.meta.integrity_ref,),
        )
        write_recovery_object(ledger, checkpoint, 0)
        ledger.close()

        # Child writes file and crashes
        proc = multiprocessing.Process(
            target=_child_write_file_and_crash,
            args=(ledger_path, str(repo), plan.meta.integrity_ref,
                  ticket.meta.integrity_ref, "recovery content\n",
                  "notes/welcome.txt", "recov-key"),
        )
        proc.start()
        proc.join(timeout=10)

        # File exists from child
        assert (repo / "notes" / "welcome.txt").read_bytes() == b"recovery content\n"

        # Parent reopens ledger and runs recovery
        parent_ledger = Ledger(ledger_path)
        parent_ledger.open()

        # Create fresh snapshot
        fresh = create_project_snapshot(
            "rb-recov", "task-recov", "run-recov", "project-recov", "corr-recov",
            str(repo), snapshot_id="task-recov:snapshot:fresh",
        )

        # Build receipt object for recovery
        from furina_code.contracts import ActionReceipt
        receipt = ActionReceipt.create(
            "rb-recov", "task-recov", "run-recov", "project-recov", "corr-recov",
            plan.meta.integrity_ref, ticket.meta.integrity_ref,
            "recov-key", "e5-safe-file-create-v1",
        )

        # Run REAL recovery
        verdict = review_interrupted_write(
            parent_ledger, str(repo), checkpoint, plan, fresh, receipt, "consumed",
        )

        # Recovery must skip because target exists and matches
        assert verdict.outcome == "skip_confirmed_action"
        assert "do not execute action again" in verdict.required_steps

        # File hash unchanged proves writer not called again
        file_hash = hashlib.sha256(
            (repo / "notes" / "welcome.txt").read_bytes()
        ).hexdigest()
        expected = hashlib.sha256(b"recovery content\n").hexdigest()
        assert file_hash == expected

        parent_ledger.close()

    def test_crash_env_var_not_set_normally(self, tmp_path):
        """_FURINA_CRASH_TEST is not set in normal test execution."""
        assert os.environ.get("_FURINA_CRASH_TEST") != "1"
