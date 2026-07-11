"""E3.1 tests — event integrity verification and tamper detection."""

import json
import sqlite3
import pytest
from furina_code.contracts import RunBinding, IntegrityCheckFailed
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
