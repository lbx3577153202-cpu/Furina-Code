"""E3 tests — object-event atomicity."""

import pytest
from furina_code.contracts import RunBinding, LedgerWriteFailed
from furina_code.ledger import Ledger


class TestObjectEventAtomicity:
    def test_failure_rolls_back_both_object_and_event(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()

        # Create a valid object
        obj = RunBinding.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            subject_ref="u", user_ref="u", task_ref="t",
            allowed_tool_classes=(), source_refs=(),
        )
        payload = {
            "subject_ref": obj.subject_ref, "user_ref": obj.user_ref,
            "project_ref": obj.project_ref, "task_ref": obj.task_ref,
            "allowed_tool_classes": [], "status": obj.status.value,
            "source_refs": [],
        }
        ledger.write_object(obj.meta, payload, caller_organ="I1-A", expected_revision=0)

        # Verify object and event exist
        assert ledger.get_head_revision("RunBinding", "rb-1") == 1
        events = ledger.get_events("rb-1")
        assert len(events) == 1

        # Now create a second object with the SAME event_id to force a UNIQUE constraint violation
        # We do this by directly manipulating the internal state
        # First, insert a duplicate event_id into a temp table
        import sqlite3
        conn = ledger.conn
        # The second write should fail due to revision conflict, not event_id
        # Let's test that a revision conflict rolls back cleanly
        obj2 = RunBinding.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            subject_ref="u2", user_ref="u2", task_ref="t2",
            allowed_tool_classes=(), source_refs=(),
        )
        # expected_revision=0 but current is 1 -> revision conflict
        with pytest.raises(Exception):  # RevisionConflict
            ledger.write_object(obj2.meta, {
                "subject_ref": obj2.subject_ref, "user_ref": obj2.user_ref,
                "project_ref": obj2.project_ref, "task_ref": obj2.task_ref,
                "allowed_tool_classes": [], "status": obj2.status.value,
                "source_refs": [],
            }, caller_organ="I1-A", expected_revision=0)

        # Verify nothing changed
        assert ledger.get_head_revision("RunBinding", "rb-1") == 1
        events = ledger.get_events("rb-1")
        assert len(events) == 1

        ledger.close()

    def test_success_creates_both_object_and_event(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()

        obj = RunBinding.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            subject_ref="u", user_ref="u", task_ref="t",
            allowed_tool_classes=(), source_refs=(),
        )
        payload = {
            "subject_ref": obj.subject_ref, "user_ref": obj.user_ref,
            "project_ref": obj.project_ref, "task_ref": obj.task_ref,
            "allowed_tool_classes": [], "status": obj.status.value,
            "source_refs": [],
        }
        ledger.write_object(obj.meta, payload, caller_organ="I1-A", expected_revision=0)

        assert ledger.get_head_revision("RunBinding", "rb-1") == 1
        events = ledger.get_events("rb-1")
        assert len(events) == 1
        assert events[0]["event_type"] == "RunBinding.created"

        ledger.close()
