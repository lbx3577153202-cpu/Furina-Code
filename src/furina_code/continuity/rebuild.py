"""Furina Code continuity — rebuild ContinuityView from ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts.meta import CanonicalMeta
from ..contracts.states import Phase, Disposition
from ..ledger.sqlite import Ledger


@dataclass(frozen=True)
class ContinuityView:
    run_binding_id: str
    last_event_sequence: int
    task_phase: str
    task_disposition: str
    open_request_refs: tuple[str, ...]
    unresolved_action_refs: tuple[str, ...]
    source_cursor: str | None


def rebuild_continuity(ledger: Ledger, run_binding_id: str) -> ContinuityView:
    """Rebuild ContinuityView from validated events and current TaskRun state."""
    events = ledger.get_events(run_binding_id)
    last_seq = ledger.get_last_sequence()

    # Find latest TaskRun from events
    task_run_events = [
        e for e in events
        if e["event_type"].startswith("TaskRun.")
        and e["aggregate_ref"].startswith("TaskRun:")
    ]

    if not task_run_events:
        return ContinuityView(
            run_binding_id=run_binding_id,
            last_event_sequence=last_seq,
            task_phase=Phase.INTAKE.value,
            task_disposition=Disposition.ACTIVE.value,
            open_request_refs=(),
            unresolved_action_refs=(),
            source_cursor=None,
        )

    # Get the latest TaskRun revision from the last event
    latest_event = task_run_events[-1]
    # Parse aggregate_ref to get object_id
    parts = latest_event["aggregate_ref"].split(":", 1)
    task_run_id = parts[1] if len(parts) == 2 else parts[0]
    revision = latest_event["aggregate_revision"]

    result = ledger.get_latest("TaskRun", task_run_id)
    if result is None:
        return ContinuityView(
            run_binding_id=run_binding_id,
            last_event_sequence=last_seq,
            task_phase=Phase.INTAKE.value,
            task_disposition=Disposition.ACTIVE.value,
            open_request_refs=(),
            unresolved_action_refs=(),
            source_cursor=None,
        )

    meta, payload = result

    # Find latest Checkpoint
    checkpoint_events = [
        e for e in events
        if e["event_type"].startswith("Checkpoint.")
    ]

    event_cursor = 0
    if checkpoint_events:
        latest_cp_event = checkpoint_events[-1]
        cp_parts = latest_cp_event["aggregate_ref"].split(":", 1)
        cp_id = cp_parts[1] if len(cp_parts) == 2 else cp_parts[0]
        cp_result = ledger.get_latest("Checkpoint", cp_id)
        if cp_result:
            _, cp_payload = cp_result
            event_cursor = cp_payload.get("event_cursor", 0)

    return ContinuityView(
        run_binding_id=run_binding_id,
        last_event_sequence=last_seq,
        task_phase=payload.get("phase", Phase.INTAKE.value),
        task_disposition=payload.get("disposition", Disposition.ACTIVE.value),
        open_request_refs=tuple(payload.get("open_requests", [])),
        unresolved_action_refs=(),
        source_cursor=str(event_cursor) if event_cursor > 0 else None,
    )
