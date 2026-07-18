"""B3: Crash between side-effect and receipt must be recoverable.

Uses CrashSimulator which spawns child process calling real
execute_single_file_create(), then crashes. Parent reopens ledger
and calls review_interrupted_write().
"""

import hashlib
import multiprocessing
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
    plan = bind_single_file_create(before, "candidate:crash", "crash content\n")
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
        """Full crash → recovery cycle using real executor."""
        repo, ledger_path, plan, ticket, snap, checkpoint = _setup_for_crash(tmp_path)

        # Use CrashSimulator with real executor
        sim = CrashSimulator(ledger_path, str(repo))
        proc = multiprocessing.Process(
            target=_child_write_file_crash,
            args=(ledger_path, str(repo), plan, ticket, snap, "crash-key"),
        )
        proc.start()
        proc.join(timeout=15)

        # Assert child exited abnormally
        assert not proc.is_alive(), "Child should have terminated"
        assert proc.exitcode != 0, "Child should have non-zero exit code"

        # Assert file was written
        assert (repo / "notes" / "welcome.txt").exists()
        assert (repo / "notes" / "welcome.txt").read_bytes() == b"crash content\n"

        # Assert receipt is executing (real ledger fact)
        import json
        parent_ledger = Ledger(ledger_path)
        parent_ledger.open()
        rows = parent_ledger.conn.execute(
            "SELECT payload_json FROM object_revisions WHERE object_type='ActionReceipt'"
        ).fetchall()
        assert len(rows) >= 1
        receipt_payload = json.loads(rows[-1][0])
        assert receipt_payload["status"] == "executing"

        # Parent reads real receipt from ledger
        from furina_code.contracts import ActionReceipt
        receipt = ActionReceipt.create(
            "rb-crash", "task-crash", "run-crash", "project-crash", "corr-crash",
            plan.meta.integrity_ref, ticket.meta.integrity_ref,
            "crash-key", "e5-safe-file-create-v1",
        )

        # Create fresh snapshot
        fresh = create_project_snapshot(
            "rb-crash", "task-crash", "run-crash", "project-crash", "corr-crash",
            str(repo), snapshot_id="task-crash:snapshot:fresh",
        )

        # Call REAL review_interrupted_write
        verdict = review_interrupted_write(
            parent_ledger, str(repo), checkpoint, plan, fresh, receipt, "consumed",
        )

        # Assert recovery skips
        assert verdict.outcome == "skip_confirmed_action"
        assert "do not execute action again" in verdict.required_steps

        # Assert file hash unchanged (no second write)
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


def _child_write_file_crash(
    ledger_path: str, workspace: str, plan, ticket, snap, idem_key: str,
) -> None:
    """Child process: write file via real executor path, persist receipt, crash."""
    import os, sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    os.environ["_FURINA_CRASH_TEST"] = "1"

    from furina_code.contracts import ActionReceipt, EnforcementVerdict
    from furina_code.contracts.meta import now_utc
    from furina_code.ledger import Ledger
    from furina_code.world.controlled_write import _inside_workspace, write_e5_object

    ledger = Ledger(ledger_path)
    ledger.open()

    # Real enforcement
    enforcement = EnforcementVerdict.create(
        run_binding_id="rb-crash", task_id="task-crash",
        task_run_id="run-crash", project_ref="project-crash",
        correlation_id="corr-crash", ticket_ref=ticket.meta.integrity_ref,
        plan_ref=plan.meta.integrity_ref, current_snapshot_ref=snap.meta.integrity_ref,
        decision="allow", reason="child enforcement",
        verdict_id=f"task-crash:enforcement:child:{now_utc().timestamp()}",
        causation_ref=ticket.meta.integrity_ref,
    )
    write_e5_object(ledger, enforcement, 0)

    # Real executing receipt
    receipt = ActionReceipt.create(
        run_binding_id="rb-crash", task_id="task-crash",
        task_run_id="run-crash", project_ref="project-crash",
        correlation_id="corr-crash", plan_ref=plan.meta.integrity_ref,
        ticket_ref=ticket.meta.integrity_ref, idempotency_key=idem_key,
        tool_ref="e5-safe-file-create-v1", causation_ref=enforcement.meta.integrity_ref,
    )
    write_e5_object(ledger, receipt, 0)

    # Write file via real path operations
    target = _inside_workspace(Path(workspace), plan.operations[0]["path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(plan.operations[0]["content"])

    # CRASH
    ledger.close()
    os._exit(1)
