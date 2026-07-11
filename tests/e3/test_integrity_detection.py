"""E3 tests — integrity tamper detection."""

import json
import pytest
from furina_code.contracts import IntegrityCheckFailed
from furina_code.ledger import Ledger


class TestIntegrityDetection:
    def test_tampered_payload_detected_on_read(self, tmp_path):
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()

        # Write a valid object
        from furina_code.contracts import RunBinding
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
        ledger.close()

        # Directly tamper with the payload in the database
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE object_revisions SET payload_json=? WHERE object_type='RunBinding' AND object_id='rb-1' AND revision=1",
            (json.dumps({"subject_ref": "TAMPERED", "user_ref": "TAMPERED"}, sort_keys=True),),
        )
        conn.commit()
        conn.close()

        # Re-open and try to read
        ledger2 = Ledger(db_path)
        ledger2.open()
        with pytest.raises(IntegrityCheckFailed):
            ledger2.get_latest("RunBinding", "rb-1")
        ledger2.close()

    def test_tampered_revision_column_detected_on_get_revision(self, tmp_path):
        """Tamper revision column and meta_json; get_revision() detects integrity mismatch."""
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()

        from furina_code.contracts import RunBinding
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
        ledger.close()

        # Tamper: update revision column and meta_json to 999,
        # also set supersedes_ref so CanonicalMeta contract passes.
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE object_revisions SET revision=999, "
            "meta_json=json_set(json_set(meta_json, '$.revision', 999), "
            "'$.supersedes_ref', 'RunBinding:rb-1:rev1') "
            "WHERE object_type='RunBinding' AND object_id='rb-1' AND revision=1"
        )
        conn.commit()
        conn.close()

        ledger2 = Ledger(db_path)
        ledger2.open()
        # get_revision(999) finds the row, but integrity_ref won't match recomputed
        with pytest.raises(IntegrityCheckFailed):
            ledger2.get_revision("RunBinding", "rb-1", 999)
        ledger2.close()

    def test_valid_object_passes_integrity_check(self, tmp_path):
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()

        from furina_code.contracts import RunBinding
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

        # Read should succeed
        result = ledger.get_latest("RunBinding", "rb-1")
        assert result is not None
        meta, read_payload = result
        assert meta.revision == 1
        assert read_payload["subject_ref"] == "u"

        ledger.close()
