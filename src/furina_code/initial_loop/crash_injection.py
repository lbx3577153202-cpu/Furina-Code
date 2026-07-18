"""B3: Test-only crash injection for side-effect/receipt boundary.

Uses multiprocessing with _FURINA_CRASH_TEST=1 environment variable
to activate the crash seam in the real execute_single_file_create().
Child process writes file via real E5 executor, then crashes.
Parent reopens ledger and runs review_interrupted_write().

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
    plan_data: dict[str, Any],
    idempotency_key: str,
) -> None:
    """Child process: use REAL E5 executor with crash injection.

    Sets _FURINA_CRASH_TEST=1 so execute_single_file_create() will
    raise after writing the file but before finalizing the receipt.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

    # Activate crash injection in the real executor
    os.environ["_FURINA_CRASH_TEST"] = "1"

    from furina_code.contracts import (
        AuthorizationTicket,
        BoundActionPlan,
        ProjectSnapshot,
        TaskRun,
    )
    from furina_code.ledger import Ledger
    from furina_code.world.controlled_write import execute_single_file_create

    ledger = Ledger(ledger_path)
    ledger.open()

    # Reconstruct objects from serialized data using real constructors
    plan = BoundActionPlan.create(
        plan_data["run_binding_id"], plan_data["task_id"], plan_data["task_run_id"],
        plan_data["project_ref"], plan_data["correlation_id"], plan_data["candidate_ref"],
        plan_data["task_revision"], plan_data["baseline_snapshot_ref"],
        plan_data["baseline_snapshot_sha256"], tuple(plan_data["target_scope"]),
        tuple(plan_data["operations"]), plan_data["expected_diff"],
        plan_data["risk"], plan_data["rollback_or_compensation"],
        tuple(plan_data["preconditions"]),
    )

    ticket = AuthorizationTicket.create(
        plan_data["run_binding_id"], plan_data["task_id"], plan_data["task_run_id"],
        plan_data["project_ref"], plan_data["correlation_id"],
        plan_data["decision_ref"], plan.meta.integrity_ref,
        plan.task_revision, plan.baseline_snapshot_ref,
        plan.target_scope, plan_data["valid_from_dt"], plan_data["expires_at_dt"],
        ticket_id=plan_data["ticket_id"],
    )

    run = TaskRun.create(
        plan_data["run_binding_id"], plan_data["task_id"], plan_data["run_run_id"],
        plan_data["project_ref"], plan_data["correlation_id"], plan.task_revision,
    )

    snapshot = ProjectSnapshot.create(
        plan_data["run_binding_id"], plan_data["task_id"], plan_data["run_run_id"],
        plan_data["project_ref"], plan_data["correlation_id"], workspace,
        snapshot_id=plan_data["snapshot_id"],
    )

    # Use the REAL executor - crash injection activates via env var
    try:
        execute_single_file_create(
            ledger, workspace, plan, ticket, snapshot,
            idempotency_key, run,
        )
    except SystemExit:
        pass  # Expected from os._exit
    except Exception:
        pass  # Crash test may raise

    # CRASH: terminate without finalizing receipt
    ledger.close()
    os._exit(1)


class CrashSimulator:
    """Test-only simulator using real E5 executor with crash injection."""

    def __init__(self, ledger_path: str, workspace: str) -> None:
        self.ledger_path = ledger_path
        self.workspace = workspace

    def write_and_crash(
        self,
        plan: Any,
        ticket: Any,
        snapshot: Any,
        run: Any,
        idempotency_key: str,
    ) -> None:
        """Spawn child process that uses real executor and crashes."""
        from datetime import timezone

        plan_data = {
            "run_binding_id": plan.meta.run_binding_id,
            "task_id": plan.meta.task_id,
            "task_run_id": plan.meta.task_run_id,
            "project_ref": plan.meta.project_ref,
            "correlation_id": plan.meta.correlation_id,
            "candidate_ref": plan.candidate_ref,
            "task_revision": plan.task_revision,
            "baseline_snapshot_ref": plan.baseline_snapshot_ref,
            "baseline_snapshot_sha256": plan.baseline_snapshot_sha256,
            "target_scope": list(plan.target_scope),
            "operations": list(plan.operations),
            "expected_diff": plan.expected_diff,
            "risk": plan.risk,
            "rollback_or_compensation": plan.rollback_or_compensation,
            "preconditions": list(plan.preconditions),
            "decision_ref": ticket.decision_ref,
            "ticket_id": ticket.meta.object_id,
            "valid_from_dt": ticket.valid_from,
            "expires_at_dt": ticket.expires_at,
            "run_run_id": run.meta.task_run_id,
            "snapshot_id": snapshot.meta.object_id,
        }

        proc = multiprocessing.Process(
            target=_child_real_executor_crash,
            args=(self.ledger_path, self.workspace, plan_data, idempotency_key),
        )
        proc.start()
        proc.join(timeout=10)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
