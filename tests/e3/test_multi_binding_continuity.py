"""E3.1 tests — multi-binding ContinuityView isolation."""

import pytest
from furina_code.contracts import (
    RunBinding, TaskDossier, TaskRun, Checkpoint,
    Phase, Disposition, BindingMismatch,
)
from furina_code.ledger import Ledger
from furina_code.continuity import rebuild_continuity


def _create_run_binding(ledger, rb_id, task_id="t-1", task_run_id="tr-1"):
    rb = RunBinding.create(
        run_binding_id=rb_id, task_id=task_id, task_run_id=task_run_id,
        project_ref="proj-1", correlation_id=f"corr-{rb_id}",
        subject_ref="user-1", user_ref="user-1", task_ref="task-1",
        allowed_tool_classes=("file_write",), source_refs=("s1",),
    )
    ledger.write_object(rb.meta, {
        "subject_ref": rb.subject_ref, "user_ref": rb.user_ref,
        "project_ref": rb.project_ref, "task_ref": rb.task_ref,
        "allowed_tool_classes": list(rb.allowed_tool_classes),
        "status": rb.status.value, "source_refs": list(rb.source_refs),
    }, caller_organ="I1-A", expected_revision=0)
    return rb


def _create_task_run(ledger, rb_id, task_id="t-1", task_run_id="tr-1"):
    tr = TaskRun.create(
        run_binding_id=rb_id, task_id=task_id, task_run_id=task_run_id,
        project_ref="proj-1", correlation_id=f"corr-{rb_id}",
        task_revision=1,
    )
    ledger.write_object(tr.meta, {
        "task_revision": tr.task_revision, "phase": tr.phase.value,
        "disposition": tr.disposition.value, "current_refs": [],
        "open_requests": [], "started_at": tr.started_at.isoformat(),
        "terminal_reason": tr.terminal_reason,
    }, caller_organ="I2-D", expected_revision=0)
    return tr


class TestMultiBindingContinuity:
    def test_sequence_scoped_to_binding(self, tmp_path):
        """RunBinding A has 5 events, B has 3. Rebuild A gets A's last sequence."""
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()

        # --- RunBinding A: rb-A ---
        _create_run_binding(ledger, "rb-A")
        tr_a = _create_task_run(ledger, "rb-A")
        # 3 transitions for A: intake→observe→deliberate→authorize
        tr_a2 = tr_a.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        ledger.write_object(tr_a2.meta, {
            "task_revision": tr_a2.task_revision, "phase": tr_a2.phase.value,
            "disposition": tr_a2.disposition.value, "current_refs": [],
            "open_requests": [], "started_at": tr_a2.started_at.isoformat(),
            "terminal_reason": tr_a2.terminal_reason,
        }, caller_organ="I2-D", expected_revision=1)

        tr_a3 = tr_a2.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE)
        ledger.write_object(tr_a3.meta, {
            "task_revision": tr_a3.task_revision, "phase": tr_a3.phase.value,
            "disposition": tr_a3.disposition.value, "current_refs": [],
            "open_requests": [], "started_at": tr_a3.started_at.isoformat(),
            "terminal_reason": tr_a3.terminal_reason,
        }, caller_organ="I2-D", expected_revision=2)

        tr_a4 = tr_a3.transition("I2-D", Phase.AUTHORIZE, Disposition.ACTIVE)
        ledger.write_object(tr_a4.meta, {
            "task_revision": tr_a4.task_revision, "phase": tr_a4.phase.value,
            "disposition": tr_a4.disposition.value, "current_refs": [],
            "open_requests": [], "started_at": tr_a4.started_at.isoformat(),
            "terminal_reason": tr_a4.terminal_reason,
        }, caller_organ="I2-D", expected_revision=3)

        # A: RunBinding + TaskRun + 3 transitions = 5 events total

        # --- RunBinding B: rb-B ---
        _create_run_binding(ledger, "rb-B", task_id="t-B", task_run_id="tr-B")
        tr_b = _create_task_run(ledger, "rb-B", task_id="t-B", task_run_id="tr-B")
        # 1 transition for B: intake→observe
        tr_b2 = tr_b.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        ledger.write_object(tr_b2.meta, {
            "task_revision": tr_b2.task_revision, "phase": tr_b2.phase.value,
            "disposition": tr_b2.disposition.value, "current_refs": [],
            "open_requests": [], "started_at": tr_b2.started_at.isoformat(),
            "terminal_reason": tr_b2.terminal_reason,
        }, caller_organ="I2-D", expected_revision=1)

        # B: RunBinding + TaskRun + 1 transition = 3 events total
        # Global: 5 + 3 = 8 events

        # Verify global sequence
        assert ledger.get_last_sequence() == 8

        # Verify scoped sequences
        assert ledger.get_last_sequence("rb-A") == 5
        assert ledger.get_last_sequence("rb-B") == 8

        # Rebuild A — last_event_sequence should be A's last (5)
        view_a = rebuild_continuity(ledger, "rb-A")
        assert view_a.run_binding_id == "rb-A"
        assert view_a.last_event_sequence == 5
        assert view_a.task_phase == "authorize"
        assert view_a.task_disposition == "active"

        # Rebuild B — last_event_sequence should be B's last (8)
        view_b = rebuild_continuity(ledger, "rb-B")
        assert view_b.run_binding_id == "rb-B"
        assert view_b.last_event_sequence == 8
        assert view_b.task_phase == "observe"
        assert view_b.task_disposition == "active"

        ledger.close()

    def test_missing_binding_fail_closed(self, tmp_path):
        """Rebuild for a non-existent binding raises BindingMismatch."""
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()

        with pytest.raises(BindingMismatch) as exc_info:
            rebuild_continuity(ledger, "rb-NONEXISTENT")
        assert "rb-NONEXISTENT" in str(exc_info.value)
        ledger.close()

    def test_each_binding_has_independent_view(self, tmp_path):
        """Two bindings with different phases produce independent ContinuityViews."""
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()

        # Binding A: stays at intake/active (only create, no transitions)
        _create_run_binding(ledger, "rb-A")
        _create_task_run(ledger, "rb-A")

        # Binding B: advances to deliberate
        _create_run_binding(ledger, "rb-B", task_id="t-B", task_run_id="tr-B")
        tr_b = _create_task_run(ledger, "rb-B", task_id="t-B", task_run_id="tr-B")
        tr_b2 = tr_b.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        ledger.write_object(tr_b2.meta, {
            "task_revision": tr_b2.task_revision, "phase": tr_b2.phase.value,
            "disposition": tr_b2.disposition.value, "current_refs": [],
            "open_requests": [], "started_at": tr_b2.started_at.isoformat(),
            "terminal_reason": tr_b2.terminal_reason,
        }, caller_organ="I2-D", expected_revision=1)
        tr_b3 = tr_b2.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE)
        ledger.write_object(tr_b3.meta, {
            "task_revision": tr_b3.task_revision, "phase": tr_b3.phase.value,
            "disposition": tr_b3.disposition.value, "current_refs": [],
            "open_requests": [], "started_at": tr_b3.started_at.isoformat(),
            "terminal_reason": tr_b3.terminal_reason,
        }, caller_organ="I2-D", expected_revision=2)

        view_a = rebuild_continuity(ledger, "rb-A")
        view_b = rebuild_continuity(ledger, "rb-B")

        assert view_a.task_phase == "intake"
        assert view_b.task_phase == "deliberate"
        assert view_a.last_event_sequence != view_b.last_event_sequence

        ledger.close()
