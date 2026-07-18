"""B3: Test-only crash injection for side-effect/receipt boundary.

Provides a hook that can terminate the worker after filesystem mutation
but before ActionReceipt persistence. Production code must NOT expose this.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..contracts import BoundActionPlan, AuthorizationTicket, ProjectSnapshot, TaskRun
    from ..ledger import Ledger


class CrashInjectionHook:
    """Test-only hook that raises after the first filesystem mutation.

    This simulates a process crash between writing the file and persisting
    the final ActionReceipt. Production code must never use this.
    """

    def __init__(self) -> None:
        self._call_count = 0

    def __call__(self, target_path: Path, content: str) -> None:
        """Called after successful filesystem write. Raises on second call."""
        self._call_count += 1
        if self._call_count == 1:
            # First call: file was written, now "crash" before receipt
            raise _SimulatedCrash(
                f"Simulated crash after writing {target_path} "
                f"(call #{self._call_count})"
            )
        # Should never reach here in normal flow


class _SimulatedCrash(Exception):
    """Raised to simulate a process crash."""
    pass


# Global hook instance for tests only
_crash_hook: CrashInjectionHook | None = None


def install_crash_hook() -> CrashInjectionHook:
    """Install the crash hook. TEST USE ONLY."""
    global _crash_hook
    _crash_hook = CrashInjectionHook()
    return _crash_hook


def uninstall_crash_hook() -> None:
    """Remove the crash hook."""
    global _crash_hook
    _crash_hook = None


def get_crash_hook() -> CrashInjectionHook | None:
    """Get the current crash hook, if any."""
    return _crash_hook


def execute_single_file_create_with_crash_hook(
    ledger: Ledger,
    workspace: str,
    plan,  # BoundActionPlan
    ticket,  # AuthorizationTicket
    current_snapshot,  # ProjectSnapshot
    idempotency_key: str,
    task_run,  # TaskRun
):
    """Execute with optional crash injection. TEST USE ONLY.

    This is a wrapper around the real execute_single_file_create that
    allows a crash hook to terminate before the receipt is persisted.
    """
    import hashlib
    import json

    from ..contracts import ActionReceipt, AuthorizationTicket, EnforcementVerdict
    from ..contracts.meta import now_utc
    from ..contracts.objects import ProjectSnapshot
    from ..world.controlled_write import (
        _idempotency_used,
        _inside_workspace,
        _ticket_is_current,
        write_e5_object,
    )

    hook = get_crash_hook()

    # Run the standard enforcement checks
    now = now_utc()
    reasons: list[str] = []
    if ticket.status != "active" or not _ticket_is_current(ledger, ticket):
        reasons.append("ticket is not active at its current ledger revision")
    if not (ticket.plan_ref == plan.meta.integrity_ref and ticket.snapshot_ref == plan.baseline_snapshot_ref):
        reasons.append("ticket is not bound to this plan and baseline")
    if ticket.task_revision != plan.task_revision or ticket.scope != plan.target_scope:
        reasons.append("ticket task revision or scope differs from plan")
    if (task_run.phase.value, task_run.disposition.value) != ("act", "active"):
        reasons.append("TaskRun is not act/active")
    if task_run.task_revision != plan.task_revision:
        reasons.append("TaskRun task revision differs from plan")
    if not (ticket.valid_from <= now < ticket.expires_at):
        reasons.append("ticket is outside its validity interval")
    if current_snapshot.snapshot_sha256 != plan.baseline_snapshot_sha256 or not current_snapshot.is_clean:
        reasons.append("project snapshot drifted from the plan baseline")
    if _idempotency_used(ledger, idempotency_key):
        reasons.append("idempotency key was already used")

    allow = not reasons
    enforcement = EnforcementVerdict.create(
        run_binding_id=plan.meta.run_binding_id, task_id=plan.meta.task_id,
        task_run_id=plan.meta.task_run_id, project_ref=plan.meta.project_ref,
        correlation_id=plan.meta.correlation_id, ticket_ref=ticket.meta.integrity_ref,
        plan_ref=plan.meta.integrity_ref, current_snapshot_ref=current_snapshot.meta.integrity_ref,
        decision="allow" if allow else "deny",
        reason="all E5 enforcement checks passed" if allow else "; ".join(reasons),
        verdict_id=f"{plan.meta.task_id}:enforcement:{idempotency_key}:{now.timestamp()}",
        causation_ref=ticket.meta.integrity_ref,
    )
    write_e5_object(ledger, enforcement, 0)

    if not allow:
        from ..world.controlled_write import ExecutionResult
        return ExecutionResult(enforcement, None)

    consumed_ticket = ticket.consume()
    write_e5_object(ledger, consumed_ticket, ticket.meta.revision)

    # Create receipt in "executing" state
    receipt = ActionReceipt.create(
        run_binding_id=plan.meta.run_binding_id, task_id=plan.meta.task_id,
        task_run_id=plan.meta.task_run_id, project_ref=plan.meta.project_ref,
        correlation_id=plan.meta.correlation_id, plan_ref=plan.meta.integrity_ref,
        ticket_ref=consumed_ticket.meta.integrity_ref, idempotency_key=idempotency_key,
        tool_ref="e5-safe-file-create-v1", causation_ref=enforcement.meta.integrity_ref,
    )
    write_e5_object(ledger, receipt, 0)

    # Perform the filesystem write
    operation = plan.operations[0]
    target = _inside_workspace(Path(workspace), operation["path"])
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(operation["content"])

        # CRASH INJECTION POINT: if hook is installed, it will raise here
        if hook is not None:
            hook(target, operation["content"])

        # If we get here, persist the final receipt
        completed = receipt.finish(
            "applied", "sha256:" + hashlib.sha256(operation["content"].encode("utf-8")).hexdigest(),
            {"operation": "create_file", "path": operation["path"]},
            "target created exactly once",
        )
    except _SimulatedCrash:
        # Crash happened after write but before receipt finalization
        # The receipt stays in "executing" state - recovery must handle this
        from ..world.controlled_write import ExecutionResult
        return ExecutionResult(enforcement, receipt)
    except Exception as exc:
        completed = receipt.finish(
            "outcome_unknown", None,
            {"operation": "create_file", "error": type(exc).__name__},
            "write outcome unknown; automatic retry prohibited",
        )

    write_e5_object(ledger, completed, receipt.meta.revision)
    from ..world.controlled_write import ExecutionResult
    return ExecutionResult(enforcement, completed)
