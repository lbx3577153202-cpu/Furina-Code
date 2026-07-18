"""Furina Code continuity — rebuild ContinuityView from ledger."""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts.errors import BindingMismatch
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


@dataclass(frozen=True)
class AuthorityBundle:
    """Integrity-checked local authority available after a backend/session loss.

    This is intentionally an index of persisted formal objects, not a second
    mutable state store.  A fresh backend receives references reconstructed
    from the ledger and cannot make its own session the authority for task
    state, approval, reality evidence, or experience.
    """

    run_binding_id: str
    object_refs_by_type: dict[str, tuple[str, ...]]
    latest_task_dossier_ref: str
    latest_task_run_ref: str
    unresolved_action_refs: tuple[str, ...]


def rebuild_continuity(ledger: Ledger, run_binding_id: str) -> ContinuityView:
    """Rebuild ContinuityView from verified events and current TaskRun state.

    Uses only verified (integrity-checked) events.  ``last_event_sequence`` is
    scoped to the given *run_binding_id*, not the global maximum.  Raises
    ``BindingMismatch`` when the binding has no events (fail-closed).
    """
    events = ledger.get_verified_events(run_binding_id)
    last_seq = ledger.get_last_sequence(run_binding_id)

    if not events:
        raise BindingMismatch(
            f"No events found for run_binding_id={run_binding_id}",
            {"run_binding_id": run_binding_id},
        )

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

    latest_event = task_run_events[-1]
    parts = latest_event["aggregate_ref"].split(":", 1)
    task_run_id = parts[1] if len(parts) == 2 else parts[0]

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

    _, payload = result

    checkpoint_events = [e for e in events if e["event_type"].startswith("Checkpoint.")]
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


def rebuild_authority_bundle(ledger: Ledger, run_binding_id: str) -> AuthorityBundle:
    """Rebuild the formal local authority required by the L3 session-loss gate.

    A missing binding, dossier, or task run is fail-closed: a clean backend
    must not be told that it can continue an incompletely reconstructed task.
    The returned references are all read through Ledger integrity validation.
    """
    objects = ledger.get_latest_for_binding(run_binding_id)
    if not objects:
        raise BindingMismatch(
            f"No current formal objects found for run_binding_id={run_binding_id}",
            {"run_binding_id": run_binding_id},
        )

    grouped: dict[str, list[str]] = {}
    unresolved: list[str] = []
    latest_dossier_ref: str | None = None
    latest_task_run_ref: str | None = None
    for meta, payload in objects:
        grouped.setdefault(meta.object_type, []).append(meta.integrity_ref)
        if meta.object_type == "TaskDossier":
            latest_dossier_ref = meta.integrity_ref
        elif meta.object_type == "TaskRun":
            latest_task_run_ref = meta.integrity_ref
        elif meta.object_type == "ActionReceipt" and payload.get("status") in {
            "started", "executing", "outcome_unknown",
        }:
            unresolved.append(meta.integrity_ref)

    required = {"RunBinding", "TaskDossier", "TaskRun"}
    missing = sorted(required - set(grouped))
    if missing or latest_dossier_ref is None or latest_task_run_ref is None:
        raise BindingMismatch(
            "Local authority bundle is incomplete; a fresh backend cannot continue",
            {"run_binding_id": run_binding_id, "missing_object_types": missing},
        )

    return AuthorityBundle(
        run_binding_id=run_binding_id,
        object_refs_by_type={key: tuple(value) for key, value in grouped.items()},
        latest_task_dossier_ref=latest_dossier_ref,
        latest_task_run_ref=latest_task_run_ref,
        unresolved_action_refs=tuple(unresolved),
    )
