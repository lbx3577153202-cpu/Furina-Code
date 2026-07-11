"""E3 tests — object-event atomicity."""

import pytest
from furina_code.contracts import RunBinding, LedgerWriteFailed
from furina_code.ledger import Ledger


class TestObjectEventAtomicity:
    def test_event_failure_rolls_back_object(self, tmp_path, monkeypatch):
        """Force event INSERT to fail via duplicate event_id.
        Object revision INSERT succeeds first, then event INSERT hits UNIQUE
        constraint → transaction ROLLBACK → object revision is gone too.
        """
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
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
        events_before = ledger.get_events("rb-1")
        assert len(events_before) == 1
        first_event_id = events_before[0]["event_id"]

        # Second write — monkeypatch _new_event_id to return same event_id
        obj2 = RunBinding.create(
            run_binding_id="rb-2", task_id="t-2", task_run_id="tr-2",
            project_ref="p", correlation_id="c",
            subject_ref="u2", user_ref="u2", task_ref="t2",
            allowed_tool_classes=(), source_refs=(),
        )
        payload2 = {
            "subject_ref": obj2.subject_ref, "user_ref": obj2.user_ref,
            "project_ref": obj2.project_ref, "task_ref": obj2.task_ref,
            "allowed_tool_classes": [], "status": obj2.status.value,
            "source_refs": [],
        }

        # Force duplicate event_id
        monkeypatch.setattr(ledger, "_new_event_id", lambda meta: first_event_id)

        with pytest.raises(LedgerWriteFailed):
            ledger.write_object(obj2.meta, payload2, caller_organ="I1-A", expected_revision=0)

        # Verify: rb-2 object revision does NOT exist
        assert ledger.get_head_revision("RunBinding", "rb-2") == 0

        # Verify: rb-1 is unchanged
        assert ledger.get_head_revision("RunBinding", "rb-1") == 1

        # Verify: event count unchanged
        events_after = ledger.get_events("rb-1")
        assert len(events_after) == 1

        # Verify: old revision still readable and intact
        result = ledger.get_latest("RunBinding", "rb-1")
        assert result is not None
        meta, read_payload = result
        assert meta.revision == 1
        assert read_payload["subject_ref"] == "u"

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

    def test_revision_conflict_rolls_back_cleanly(self, tmp_path):
        """Revision conflict leaves head and events unchanged."""
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()

        obj = RunBinding.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
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

        from furina_code.contracts import RevisionConflict
        obj2 = RunBinding.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            subject_ref="u2", user_ref="u2", task_ref="t2",
            allowed_tool_classes=(), source_refs=(),
        )
        with pytest.raises(RevisionConflict):
            ledger.write_object(obj2.meta, {
                "subject_ref": obj2.subject_ref, "user_ref": obj2.user_ref,
                "project_ref": obj2.project_ref, "task_ref": obj2.task_ref,
                "allowed_tool_classes": [], "status": obj2.status.value,
                "source_refs": [],
            }, caller_organ="I1-A", expected_revision=0)

        assert ledger.get_head_revision("RunBinding", "rb-1") == 1
        events = ledger.get_events("rb-1")
        assert len(events) == 1

        ledger.close()
