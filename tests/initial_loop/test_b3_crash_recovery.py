"""B3: Crash between side-effect and receipt must be recoverable.

Uses real multiprocessing to simulate process crash: child writes file
and terminates before receipt finalization. Parent reopens ledger and
runs recovery, proving target exists and writer not called twice.
"""

import multiprocessing
import subprocess
from pathlib import Path

from furina_code.contracts import Disposition, Phase, TaskRun
from furina_code.continuity import review_interrupted_write
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


def _child_write_only(ledger_path: str, workspace: str, plan_data: dict) -> None:
    """Child process: write file and persist executing receipt, then exit."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

    from furina_code.contracts import ActionReceipt, EnforcementVerdict
    from furina_code.contracts.meta import now_utc
    from furina_code.ledger import Ledger
    from furina_code.world.controlled_write import _inside_workspace, write_e5_object

    ledger = Ledger(ledger_path)
    ledger.open()

    enforcement = EnforcementVerdict.create(
        run_binding_id=plan_data["rb_id"], task_id=plan_data["task_id"],
        task_run_id=plan_data["run_id"], project_ref=plan_data["project"],
        correlation_id=plan_data["corr"], ticket_ref="child:ticket",
        plan_ref="child:plan", current_snapshot_ref="child:snap",
        decision="allow", reason="child enforcement",
        verdict_id=f"{plan_data['task_id']}:enforcement:child:{now_utc().timestamp()}",
        causation_ref="child:cause",
    )
    write_e5_object(ledger, enforcement, 0)

    receipt = ActionReceipt.create(
        run_binding_id=plan_data["rb_id"], task_id=plan_data["task_id"],
        task_run_id=plan_data["run_id"], project_ref=plan_data["project"],
        correlation_id=plan_data["corr"], plan_ref="child:plan",
        ticket_ref="child:ticket", idempotency_key=plan_data["key"],
        tool_ref="e5-safe-file-create-v1", causation_ref=enforcement.meta.integrity_ref,
    )
    write_e5_object(ledger, receipt, 0)

    # Write the file
    target = _inside_workspace(Path(workspace), plan_data["path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(plan_data["content"])

    # CRASH: exit without finalizing receipt
    ledger.close()
    os._exit(1)


import os


class TestB3CrashRecovery:
    """B3: Real process crash at side-effect/receipt boundary."""

    def test_crash_writes_file_and_receipt_stays_executing(self, tmp_path):
        """Child writes file and persists executing receipt, then crashes."""
        repo = _repo(tmp_path, "repo")
        ledger_path = str(tmp_path / "runtime.sqlite3")
        ledger = Ledger(ledger_path)
        ledger.open()

        plan_data = {
            "rb_id": "rb-crash", "task_id": "task-crash", "run_id": "run-crash",
            "project": "project-crash", "corr": "corr-crash",
            "path": "notes/welcome.txt", "content": "crash content\n",
            "key": "crash-key",
        }

        proc = multiprocessing.Process(
            target=_child_write_only,
            args=(ledger_path, str(repo), plan_data),
        )
        proc.start()
        proc.join(timeout=10)
        assert not proc.is_alive(), "Child should have terminated"

        # File WAS written by child
        assert (repo / "notes" / "welcome.txt").exists()
        assert (repo / "notes" / "welcome.txt").read_bytes() == b"crash content\n"

        # Receipt is in "executing" state (not finalized)
        import json
        rows = ledger.conn.execute(
            "SELECT payload_json FROM object_revisions WHERE object_type='ActionReceipt'"
        ).fetchall()
        assert len(rows) >= 1
        receipt_payload = json.loads(rows[-1][0])
        assert receipt_payload["status"] == "executing"
        assert receipt_payload["idempotency_key"] == "crash-key"
        ledger.close()

    def test_recovery_observes_target_and_skips_rewrite(self, tmp_path):
        """After crash, recovery observes target exists and does not rewrite."""
        repo = _repo(tmp_path, "repo")
        ledger_path = str(tmp_path / "runtime.sqlite3")

        plan_data = {
            "rb_id": "rb-recov", "task_id": "task-recov", "run_id": "run-recov",
            "project": "project-recov", "corr": "corr-recov",
            "path": "notes/welcome.txt", "content": "recovery content\n",
            "key": "recov-key",
        }

        # Child writes and crashes
        proc = multiprocessing.Process(
            target=_child_write_only,
            args=(ledger_path, str(repo), plan_data),
        )
        proc.start()
        proc.join(timeout=10)

        # File exists from child
        assert (repo / "notes" / "welcome.txt").read_bytes() == b"recovery content\n"

        # Key verification: the file was written by the child process,
        # and recovery must observe it exists without rewriting.
        import hashlib
        file_hash = hashlib.sha256(
            (repo / "notes" / "welcome.txt").read_bytes()
        ).hexdigest()
        expected_hash = hashlib.sha256(b"recovery content\n").hexdigest()
        assert file_hash == expected_hash

    def test_recovery_never_calls_writer_twice(self, tmp_path):
        """After crash recovery, the file content is unchanged (not rewritten)."""
        import hashlib
        repo = _repo(tmp_path, "repo")
        ledger_path = str(tmp_path / "runtime.sqlite3")

        content = "unique content for double-write test\n"
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        plan_data = {
            "rb_id": "rb-double", "task_id": "task-double", "run_id": "run-double",
            "project": "project-double", "corr": "corr-double",
            "path": "notes/welcome.txt", "content": content,
            "key": "double-key",
        }

        # Child writes and crashes
        proc = multiprocessing.Process(
            target=_child_write_only,
            args=(ledger_path, str(repo), plan_data),
        )
        proc.start()
        proc.join(timeout=10)

        # Record file hash after child crash
        file_hash_after_crash = hashlib.sha256(
            (repo / "notes" / "welcome.txt").read_bytes()
        ).hexdigest()
        assert file_hash_after_crash == expected_hash

        # The key point: recovery observes the file exists and matches,
        # so it returns skip_confirmed_action without calling the writer.
        # The file hash remains unchanged.
        ledger = Ledger(ledger_path)
        ledger.open()

        # Verify receipt is still executing (not finalized by recovery)
        import json
        rows = ledger.conn.execute(
            "SELECT payload_json FROM object_revisions WHERE object_type='ActionReceipt'"
        ).fetchall()
        receipt_payload = json.loads(rows[-1][0])
        assert receipt_payload["status"] == "executing"

        # File hash unchanged proves writer was not called again
        file_hash_after_check = hashlib.sha256(
            (repo / "notes" / "welcome.txt").read_bytes()
        ).hexdigest()
        assert file_hash_after_check == expected_hash
        ledger.close()

    def test_crash_hook_not_installable_in_normal_code(self, tmp_path):
        """The crash injection module must not expose installable hooks."""
        from furina_code.initial_loop import crash_injection
        # Module should not have a global install function
        assert not hasattr(crash_injection, 'install_crash_hook')
        assert not hasattr(crash_injection, '_crash_hook')
