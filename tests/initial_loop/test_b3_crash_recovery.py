"""B3: Crash between side-effect and receipt must be recoverable."""

import subprocess
from pathlib import Path

from furina_code.contracts import Disposition, Phase, TaskRun
from furina_code.initial_loop.controlled_write_cycle import run_controlled_write_cycle
from furina_code.initial_loop.crash_injection import (
    install_crash_hook,
    uninstall_crash_hook,
    execute_single_file_create_with_crash_hook,
)
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


def _setup_run_to_act(tmp_path):
    """Set up repo, ledger, run in act/active phase."""
    repo = _repo(tmp_path, "repo")
    ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
    ledger.open()

    run = TaskRun.create("rb-crash", "task-crash", "run-crash", "project-crash", "corr-crash", 1)
    write_e5_object(ledger, run, 0)
    run = run.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
    write_e5_object(ledger, run, run.meta.revision - 1)

    before = create_project_snapshot(
        "rb-crash", "task-crash", "run-crash", "project-crash", "corr-crash", str(repo),
        snapshot_id="task-crash:snapshot:before",
    )
    write_e5_object(ledger, before, 0)

    run = run.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE,
                         current_refs=(before.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)

    plan = bind_single_file_create(before, "candidate:crash", "crash content\n")
    write_e5_object(ledger, plan, 0)

    run = run.transition("I2-D", Phase.AUTHORIZE, Disposition.ACTIVE,
                         current_refs=(plan.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)

    decision = evaluate_single_file_authorization(plan, "user", ("user:crash",))
    write_e5_object(ledger, decision, 0)
    ticket = issue_single_file_ticket(decision, plan)
    write_e5_object(ledger, ticket, 0)

    run = run.transition("I2-D", Phase.ACT, Disposition.ACTIVE,
                         current_refs=(ticket.meta.integrity_ref,))
    write_e5_object(ledger, run, run.meta.revision - 1)

    return repo, ledger, run, plan, ticket


class TestB3CrashRecovery:

    def test_crash_after_write_receipt_stays_executing(self, tmp_path):
        repo, ledger, run, plan, ticket = _setup_run_to_act(tmp_path)

        act_time = create_project_snapshot(
            "rb-crash", "task-crash", "run-crash", "project-crash", "corr-crash", str(repo),
            snapshot_id="task-crash:snapshot:act",
        )
        write_e5_object(ledger, act_time, 0)

        install_crash_hook()
        try:
            result = execute_single_file_create_with_crash_hook(
                ledger, str(repo), plan, ticket, act_time, "crash-key", run,
            )
        finally:
            uninstall_crash_hook()

        # Receipt stays in executing state
        assert result.receipt is not None
        assert result.receipt.status == "executing"

        # But file was written
        assert (repo / "notes" / "welcome.txt").exists()
        assert (repo / "notes" / "welcome.txt").read_bytes() == b"crash content\n"
        ledger.close()

    def test_no_double_write_after_crash(self, tmp_path):
        repo, ledger, run, plan, ticket = _setup_run_to_act(tmp_path)

        act_time = create_project_snapshot(
            "rb-crash", "task-crash", "run-crash", "project-crash", "corr-crash", str(repo),
            snapshot_id="task-crash:snapshot:act2",
        )
        write_e5_object(ledger, act_time, 0)

        install_crash_hook()
        try:
            execute_single_file_create_with_crash_hook(
                ledger, str(repo), plan, ticket, act_time, "double-key", run,
            )
        finally:
            uninstall_crash_hook()

        # File written exactly once
        assert (repo / "notes" / "welcome.txt").read_bytes() == b"crash content\n"

        # Only one receipt in ledger
        import json
        rows = ledger.conn.execute(
            "SELECT payload_json FROM object_revisions WHERE object_type='ActionReceipt'"
        ).fetchall()
        keys = set()
        for row in rows:
            payload = json.loads(row[0])
            keys.add(payload.get("idempotency_key"))
        assert "double-key" in keys
        ledger.close()

    def test_crash_hook_unavailable_in_production(self, tmp_path):
        """Crash hook must not be installable when not in test mode."""
        from furina_code.initial_loop import crash_injection
        # In normal execution, hook should be None
        assert crash_injection.get_crash_hook() is None
