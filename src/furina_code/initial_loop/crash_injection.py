"""B3: Test-only crash injection for side-effect/receipt boundary.

Parent writes plan, decision, ticket, snapshot, and act/active TaskRun
to the ledger, then spawns a child process.  The child loads these objects
from the ledger using the loader (preserving original integrity_refs),
calls execute_single_file_create() with _FURINA_CRASH_TEST=1, and exits
non-zero after the executor writes the file and executing receipt.

Parent reopens the ledger, loads real receipt/ticket/checkpoint using
the loader, and calls review_interrupted_write().

Production code never sets _FURINA_CRASH_TEST.
"""

from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
from typing import Any


def _child_real_executor_crash(
    ledger_path: str,
    workspace: str,
    plan_oid: str,
    ticket_oid: str,
    snapshot_oid: str,
    run_oid: str,
    idempotency_key: str,
) -> None:
    """Child process: load objects from ledger, call REAL executor, crash.

    Uses contracts.loader to reconstruct formal objects from ledger data
    with original integrity_refs preserved.  Calls execute_single_file_create()
    once.  _FURINA_CRASH_TEST=1 causes the executor to return with receipt
    in "executing" state after writing the file.  Then the child exits non-zero.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

    os.environ["_FURINA_CRASH_TEST"] = "1"

    from furina_code.contracts.loader import (
        load_action_receipt,
        load_authorization_ticket,
        load_bound_action_plan,
        load_task_run,
    )
    from furina_code.ledger import Ledger
    from furina_code.world.controlled_write import execute_single_file_create

    ledger = Ledger(ledger_path)
    ledger.open()

    # Load objects from ledger with original integrity_refs
    plan = load_bound_action_plan(ledger, plan_oid)
    ticket = load_authorization_ticket(ledger, ticket_oid)
    run = load_task_run(ledger, run_oid)

    # Create act-time snapshot (real git inspection)
    from furina_code.world import create_project_snapshot
    snapshot = create_project_snapshot(
        plan.meta.run_binding_id, plan.meta.task_id, plan.meta.task_run_id,
        plan.meta.project_ref, plan.meta.correlation_id, workspace,
        snapshot_id=snapshot_oid,
    )

    # Call the REAL executor exactly once
    execute_single_file_create(
        ledger, workspace, plan, ticket, snapshot,
        idempotency_key, run,
    )

    # Crash: exit without finalizing receipt
    ledger.close()
    os._exit(1)


class CrashSimulator:
    """Test-only simulator using real E5 executor with crash injection."""

    def __init__(self, ledger_path: str, workspace: str) -> None:
        self.ledger_path = ledger_path
        self.workspace = workspace

    def write_and_crash(
        self,
        plan_oid: str,
        ticket_oid: str,
        snapshot_oid: str,
        run_oid: str,
        idempotency_key: str,
    ) -> int:
        """Spawn child that loads objects from ledger, calls real executor, crashes.

        Returns the child's exit code (expected: non-zero).
        """
        proc = multiprocessing.Process(
            target=_child_real_executor_crash,
            args=(
                self.ledger_path, self.workspace,
                plan_oid, ticket_oid, snapshot_oid, run_oid,
                idempotency_key,
            ),
        )
        proc.start()
        proc.join(timeout=30)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
        return proc.exitcode
