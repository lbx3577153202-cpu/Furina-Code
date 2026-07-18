"""B3: Test-only crash injection for side-effect/receipt boundary.

Uses multiprocessing to simulate a real process crash: a child process
writes the file, then terminates without persisting the final receipt.
The parent process reopens the ledger and runs recovery.

Production code must NOT expose this module.
"""

from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
from typing import Any


def _child_write_and_crash(
    ledger_path: str,
    workspace: str,
    plan_data: dict[str, Any],
    ticket_data: dict[str, Any],
    snapshot_data: dict[str, Any],
    idempotency_key: str,
    run_data: dict[str, Any],
) -> None:
    """Child process: write file, persist executing receipt, then crash.

    This function runs in a separate process. It:
    1. Opens a fresh ledger
    2. Runs enforcement checks
    3. Writes the file
    4. Persists the receipt in "executing" state
    5. Terminates WITHOUT finalizing the receipt (simulates crash)
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

    from furina_code.contracts import ActionReceipt, EnforcementVerdict
    from furina_code.contracts.meta import now_utc
    from furina_code.ledger import Ledger
    from furina_code.world.controlled_write import (
        _idempotency_used,
        _inside_workspace,
        _ticket_is_current,
        write_e5_object,
    )

    ledger = Ledger(ledger_path)
    ledger.open()

    # Reconstruct objects from serialized data
    from furina_code.contracts import (
        AuthorizationTicket,
        BoundActionPlan,
        ProjectSnapshot,
        TaskRun,
    )

    plan = BoundActionPlan.create(
        plan_data["run_binding_id"], plan_data["task_id"], plan_data["task_run_id"],
        plan_data["project_ref"], plan_data["correlation_id"], plan_data["candidate_ref"],
        plan_data["task_revision"], plan_data["baseline_snapshot_ref"],
        plan_data["baseline_snapshot_sha256"], tuple(plan_data["target_scope"]),
        tuple(plan_data["operations"]), plan_data["expected_diff"],
        plan_data["risk"], plan_data["rollback_or_compensation"],
        tuple(plan_data["preconditions"]),
    )

    # Run enforcement (simplified - skip full reconstruction for test)
    now = now_utc()
    enforcement = EnforcementVerdict.create(
        run_binding_id=plan.meta.run_binding_id, task_id=plan.meta.task_id,
        task_run_id=plan.meta.task_run_id, project_ref=plan.meta.project_ref,
        correlation_id=plan.meta.correlation_id, ticket_ref="child:ticket",
        plan_ref=plan.meta.integrity_ref, current_snapshot_ref="child:snapshot",
        decision="allow", reason="child process enforcement",
        verdict_id=f"{plan.meta.task_id}:enforcement:child:{now.timestamp()}",
        causation_ref="child:cause",
    )
    write_e5_object(ledger, enforcement, 0)

    # Create executing receipt
    receipt = ActionReceipt.create(
        run_binding_id=plan.meta.run_binding_id, task_id=plan.meta.task_id,
        task_run_id=plan.meta.task_run_id, project_ref=plan.meta.project_ref,
        correlation_id=plan.meta.correlation_id, plan_ref=plan.meta.integrity_ref,
        ticket_ref="child:ticket", idempotency_key=idempotency_key,
        tool_ref="e5-safe-file-create-v1", causation_ref=enforcement.meta.integrity_ref,
    )
    write_e5_object(ledger, receipt, 0)

    # Write the file
    target_path = plan.operations[0]["path"]
    target = _inside_workspace(Path(workspace), target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(plan.operations[0]["content"])

    # CRASH: terminate without finalizing receipt
    # The receipt stays in "executing" state
    ledger.close()
    os._exit(1)  # Simulate abrupt process termination


class CrashSimulator:
    """Test-only simulator that spawns a child process to write and crash.

    The child writes the file and persists an executing receipt,
    then terminates abruptly. The parent can then reopen the ledger
    and run recovery.
    """

    def __init__(self, ledger_path: str, workspace: str) -> None:
        self.ledger_path = ledger_path
        self.workspace = workspace

    def write_and_crash(
        self,
        plan: Any,
        idempotency_key: str,
    ) -> None:
        """Spawn child process that writes file and crashes."""
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
        }

        proc = multiprocessing.Process(
            target=_child_write_and_crash,
            args=(
                self.ledger_path, self.workspace, plan_data,
                {}, {}, idempotency_key, {},
            ),
        )
        proc.start()
        proc.join(timeout=10)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
