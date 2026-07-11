"""E3.1 tests — event integrity verification and tamper detection."""

import json
import sqlite3
import pytest
from furina_code.contracts import RunBinding, IntegrityCheckFailed, LedgerWriteFailed
from furina_code.ledger import Ledger


def _write_binding(ledger, run_binding_id="rb-1"):
    obj = RunBinding.create(
        run_binding_id=run_binding_id, task_id="t-1", task_run_id="tr-1",
        project_ref="p", correlation_id="c",
        subject_ref="u", user_ref="u", task_ref="t",
        allowed_tool_classes=(), source_refs=(),
    )
    ledger.write_object(obj.meta, {
        "subject_ref": obj.subject_ref, "user_ref": obj.user_ref,
        "project_ref": obj.project_ref, "task_ref": obj.task_ref,
        "allowed_tool_classes": [], "status": obj.status.value,
        "source_refs": [],
    }, caller_organ="I1-A", expected_revision=0)


class TestEventIntegrityVerification:
    def test_valid_events_pass_verification(self, tmp_path):
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()
        _write_binding(ledger)
        events = ledger.get_verified_events("rb-1")
        assert len(events) == 1
        assert events[0]["event_type"] == "RunBinding.created"
        ledger.close()

    def test_tampered_event_type_detected(self, tmp_path):
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()
        _write_binding(ledger)
        ledger.close()

        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE event_envelopes SET event_type='TAMPERED' WHERE sequence=1"
        )
        conn.commit()
        conn.close()

        ledger2 = Ledger(db_path)
        ledger2.open()
        with pytest.raises(IntegrityCheckFailed):
            ledger2.get_verified_events("rb-1")
        ledger2.close()

    def test_tampered_aggregate_revision_detected(self, tmp_path):
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()
        _write_binding(ledger)
        ledger.close()

        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE event_envelopes SET aggregate_revision=999 WHERE sequence=1"
        )
        conn.commit()
        conn.close()

        ledger2 = Ledger(db_path)
        ledger2.open()
        with pytest.raises(IntegrityCheckFailed):
            ledger2.get_verified_events("rb-1")
        ledger2.close()

    def test_tampered_run_binding_id_detected(self, tmp_path):
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()
        _write_binding(ledger)
        ledger.close()

        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE event_envelopes SET run_binding_id='rb-TAMPERED' WHERE sequence=1"
        )
        conn.commit()
        conn.close()

        ledger2 = Ledger(db_path)
        ledger2.open()
        # After tampering, the event is under "rb-TAMPERED", not "rb-1".
        # Query with tampered id to find the event; integrity check should fail.
        with pytest.raises(IntegrityCheckFailed):
            ledger2.get_verified_events("rb-TAMPERED")
        ledger2.close()

    def test_tampered_sequence_detected(self, tmp_path):
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()
        _write_binding(ledger)
        ledger.close()

        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE event_envelopes SET sequence=999 WHERE sequence=1"
        )
        conn.commit()
        conn.close()

        ledger2 = Ledger(db_path)
        ledger2.open()
        with pytest.raises(IntegrityCheckFailed):
            ledger2.get_verified_events("rb-1")
        ledger2.close()

    def test_tampered_integrity_ref_detected(self, tmp_path):
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()
        _write_binding(ledger)
        ledger.close()

        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE event_envelopes SET integrity_ref='sha256:aaaa' WHERE sequence=1"
        )
        conn.commit()
        conn.close()

        ledger2 = Ledger(db_path)
        ledger2.open()
        with pytest.raises(IntegrityCheckFailed):
            ledger2.get_verified_events("rb-1")
        ledger2.close()

    def test_unverified_events_bypass_check(self, tmp_path):
        """get_events() does NOT verify integrity (raw read)."""
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()
        _write_binding(ledger)
        ledger.close()

        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE event_envelopes SET event_type='TAMPERED' WHERE sequence=1"
        )
        conn.commit()
        conn.close()

        ledger2 = Ledger(db_path)
        ledger2.open()
        # get_events() returns raw data without integrity check
        events = ledger2.get_events("rb-1")
        assert len(events) == 1
        assert events[0]["event_type"] == "TAMPERED"
        ledger2.close()


class TestEventSequence:
    def test_consecutive_sequences_strictly_increasing(self, tmp_path):
        """Three writes produce sequences 1, 2, 3 with verified integrity."""
        from furina_code.contracts import TaskRun, Phase, Disposition

        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()

        # Write 1: RunBinding
        _write_binding(ledger, "rb-1")

        # Write 2: TaskRun
        tr = TaskRun.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c", task_revision=1,
        )
        ledger.write_object(tr.meta, {
            "task_revision": tr.task_revision, "phase": tr.phase.value,
            "disposition": tr.disposition.value, "current_refs": [],
            "open_requests": [], "started_at": tr.started_at.isoformat(),
            "terminal_reason": tr.terminal_reason,
        }, caller_organ="I2-D", expected_revision=0)

        # Write 3: TaskRun transition
        tr2 = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        ledger.write_object(tr2.meta, {
            "task_revision": tr2.task_revision, "phase": tr2.phase.value,
            "disposition": tr2.disposition.value, "current_refs": [],
            "open_requests": [], "started_at": tr2.started_at.isoformat(),
            "terminal_reason": tr2.terminal_reason,
        }, caller_organ="I2-D", expected_revision=1)

        events = ledger.get_verified_events("rb-1")
        assert len(events) == 3
        sequences = [e["sequence"] for e in events]
        assert sequences == sorted(sequences), "Sequences must be increasing"
        assert len(set(sequences)) == 3, "No duplicate sequences"
        # Strictly increasing
        for i in range(1, len(sequences)):
            assert sequences[i] > sequences[i - 1]

        ledger.close()

    def test_post_rollback_sequence_consistent_with_integrity(self, tmp_path, monkeypatch):
        """After a rollback, the next successful write's sequence matches integrity."""
        from furina_code.contracts import TaskRun, Phase, Disposition

        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()

        _write_binding(ledger, "rb-1")
        first_events = ledger.get_events("rb-1")
        first_event_id = first_events[0]["event_id"]

        # Write a TaskRun successfully
        tr = TaskRun.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c", task_revision=1,
        )
        ledger.write_object(tr.meta, {
            "task_revision": tr.task_revision, "phase": tr.phase.value,
            "disposition": tr.disposition.value, "current_refs": [],
            "open_requests": [], "started_at": tr.started_at.isoformat(),
            "terminal_reason": tr.terminal_reason,
        }, caller_organ="I2-D", expected_revision=0)

        # Now try to write another binding but force event failure
        obj_bad = RunBinding.create(
            run_binding_id="rb-bad", task_id="t-bad", task_run_id="tr-bad",
            project_ref="p", correlation_id="c",
            subject_ref="u", user_ref="u", task_ref="t",
            allowed_tool_classes=(), source_refs=(),
        )
        monkeypatch.setattr(ledger, "_new_event_id", lambda meta: first_event_id)

        with pytest.raises(LedgerWriteFailed):
            ledger.write_object(obj_bad.meta, {
                "subject_ref": "u", "user_ref": "u",
                "project_ref": "p", "task_ref": "t",
                "allowed_tool_classes": [], "status": "active",
                "source_refs": [],
            }, caller_organ="I1-A", expected_revision=0)

        # Undo monkeypatch so the next write gets a fresh event_id
        monkeypatch.undo()

        # Now write a valid TaskRun transition — should succeed with correct sequence
        tr2 = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        ledger.write_object(tr2.meta, {
            "task_revision": tr2.task_revision, "phase": tr2.phase.value,
            "disposition": tr2.disposition.value, "current_refs": [],
            "open_requests": [], "started_at": tr2.started_at.isoformat(),
            "terminal_reason": tr2.terminal_reason,
        }, caller_organ="I2-D", expected_revision=1)

        events = ledger.get_verified_events("rb-1")
        # rb-1 events: 1 (RunBinding) + 1 (TaskRun rev1) + 1 (TaskRun rev2) = 3
        assert len(events) == 3
        sequences = [e["sequence"] for e in events]
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == 3

        # Verify each event's integrity (already done by get_verified_events, but explicit)
        for evt in events:
            assert evt["integrity_ref"].startswith("sha256:")

        ledger.close()
