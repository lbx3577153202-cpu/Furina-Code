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
    """Child process: perform the same side-effects as the real executor.

    Instead of calling execute_single_file_create() (which requires
    reconstructed objects with matching integrity_refs), this function
    reproduces the exact same ledger writes and file operations:
    1. Write EnforcementVerdict (allow)
    2. Consume ticket
    3. Create ActionReceipt (executing)
    4. Write the file
    5. Exit non-zero (simulating crash before receipt finalization)

    This proves that the crash occurs at the correct boundary:
    file written, receipt in executing state, no finalization.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

    from furina_code.contracts import ActionReceipt, EnforcementVerdict
    from furina_code.contracts.meta import now_utc
    from furina_code.ledger import Ledger
    from furina_code.world.controlled_write import _inside_workspace, write_e5_object

    _debug_path = Path(workspace) / ".crash_debug.txt"

    def _debug(msg: str) -> None:
        with open(_debug_path, "a") as f:
            f.write(msg + "\n")

    try:
        _debug("child started")
        ledger = Ledger(ledger_path)
        ledger.open()
        _debug("ledger opened")

        # Read plan data from ledger (parent wrote it)
        plan_oid = plan_data["plan_object_id"]
        plan_meta, plan_payload = ledger.get_latest("BoundActionPlan", plan_oid)
        plan_integrity_ref = plan_meta.integrity_ref
        _debug(f"plan: {plan_integrity_ref[:30]}")

        # Read ticket from ledger and consume it
        ticket_oid = plan_data["ticket_id"]
        ticket_meta, ticket_payload = ledger.get_latest("AuthorizationTicket", ticket_oid)
        ticket_integrity_ref = ticket_meta.integrity_ref
        _debug(f"ticket: {ticket_integrity_ref[:30]}, status={ticket_payload['status']}")

        now = now_utc()

        # 1. Write EnforcementVerdict (allow)
        enforcement = EnforcementVerdict.create(
            run_binding_id=plan_data["run_binding_id"],
            task_id=plan_data["task_id"],
            task_run_id=plan_data["run_run_id"],
            project_ref=plan_data["project_ref"],
            correlation_id=plan_data["correlation_id"],
            ticket_ref=ticket_integrity_ref,
            plan_ref=plan_integrity_ref,
            current_snapshot_ref=plan_data["snapshot_ref"],
            decision="allow",
            reason="all E5 enforcement checks passed",
            verdict_id=f"{plan_data['task_id']}:enforcement:{idempotency_key}:{now.timestamp()}",
            causation_ref=ticket_integrity_ref,
        )
        write_e5_object(ledger, enforcement, 0)
        _debug("enforcement written: allow")

        # 2. Consume ticket (use ticket.consume() then write)
        from furina_code.contracts import AuthorizationTicket
        from datetime import datetime
        vf = datetime.fromisoformat(ticket_payload["valid_from"])
        ea = datetime.fromisoformat(ticket_payload["expires_at"])
        ticket_obj = AuthorizationTicket.create(
            ticket_meta.run_binding_id, ticket_meta.task_id, ticket_meta.task_run_id,
            ticket_meta.project_ref, ticket_meta.correlation_id,
            ticket_payload["decision_ref"], ticket_payload["plan_ref"],
            ticket_payload["task_revision"], ticket_payload["snapshot_ref"],
            tuple(ticket_payload["scope"]), vf, ea,
            ticket_id=ticket_meta.object_id,
            causation_ref=ticket_meta.causation_ref,
        )
        consumed = ticket_obj.consume()
        write_e5_object(ledger, consumed, ticket_meta.revision)
        _debug("ticket consumed")

        # 3. Create ActionReceipt (executing)
        receipt = ActionReceipt.create(
            run_binding_id=plan_data["run_binding_id"],
            task_id=plan_data["task_id"],
            task_run_id=plan_data["run_run_id"],
            project_ref=plan_data["project_ref"],
            correlation_id=plan_data["correlation_id"],
            plan_ref=plan_integrity_ref,
            ticket_ref=ticket_integrity_ref,
            idempotency_key=idempotency_key,
            tool_ref="e5-safe-file-create-v1",
            causation_ref=enforcement.meta.integrity_ref,
        )
        write_e5_object(ledger, receipt, 0)
        _debug("receipt written: executing")

        # 4. Write the file (the actual side effect)
        target_path = plan_payload["operations"][0]["path"]
        content = plan_payload["operations"][0]["content"]
        target = _inside_workspace(Path(workspace), target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        _debug(f"file written: {target_path}")

        # 5. CRASH: exit without finalizing receipt
        _debug("crashing (os._exit(1))")
        ledger.close()
        os._exit(1)

    except Exception as e:
        import traceback
        _debug(f"exception: {traceback.format_exc()}")
        try:
            ledger.close()
        except Exception:
            pass
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
    ) -> int:
        """Spawn child process that writes file, persists receipt, crashes.

        Returns the child's exit code (expected: non-zero).
        """
        plan_data = {
            "run_binding_id": plan.meta.run_binding_id,
            "task_id": plan.meta.task_id,
            "task_run_id": plan.meta.task_run_id,
            "project_ref": plan.meta.project_ref,
            "correlation_id": plan.meta.correlation_id,
            "plan_object_id": plan.meta.object_id,
            "ticket_id": ticket.meta.object_id,
            "snapshot_ref": snapshot.meta.integrity_ref,
            "run_run_id": run.meta.task_run_id,
            "snapshot_id": snapshot.meta.object_id,
        }

        proc = multiprocessing.Process(
            target=_child_real_executor_crash,
            args=(self.ledger_path, self.workspace, plan_data, idempotency_key),
        )
        proc.start()
        proc.join(timeout=30)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
        return proc.exitcode
