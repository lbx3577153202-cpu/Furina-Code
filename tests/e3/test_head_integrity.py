"""E3.2 tests — object head integrity fail-closed."""

import sqlite3
import pytest
from furina_code.contracts import RunBinding, IntegrityCheckFailed
from furina_code.ledger import Ledger
from furina_code.continuity import rebuild_continuity


def _write_binding(ledger, rb_id="rb-1"):
    obj = RunBinding.create(
        run_binding_id=rb_id, task_id="t-1", task_run_id="tr-1",
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


class TestHeadIntegrity:
    def test_broken_head_raises_integrity_error(self, tmp_path):
        """Head points to non-existent revision → INTEGRITY_CHECK_FAILED."""
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()
        _write_binding(ledger)
        ledger.close()

        # Tamper: point head to revision 999
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE object_heads SET current_revision=999 "
            "WHERE object_type='RunBinding' AND object_id='rb-1'"
        )
        conn.commit()
        conn.close()

        ledger2 = Ledger(db_path)
        ledger2.open()
        with pytest.raises(IntegrityCheckFailed):
            ledger2.get_latest("RunBinding", "rb-1")
        ledger2.close()

    def test_broken_head_does_not_return_none(self, tmp_path):
        """get_latest must NOT return None when head > 0 but revision missing."""
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()
        _write_binding(ledger)
        ledger.close()

        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE object_heads SET current_revision=999 "
            "WHERE object_type='RunBinding' AND object_id='rb-1'"
        )
        conn.commit()
        conn.close()

        ledger2 = Ledger(db_path)
        ledger2.open()
        # Must raise, not return None
        with pytest.raises(IntegrityCheckFailed):
            ledger2.get_latest("RunBinding", "rb-1")
        ledger2.close()

    def test_tampered_revision_column_detected(self, tmp_path):
        """Tamper with revision column and meta_json → INTEGRITY_CHECK_FAILED.

        Updates both column and meta_json revision to 999 but keeps the
        original integrity_ref.  The recomputed hash won't match because
        the data changed.
        """
        db_path = str(tmp_path / "test.sqlite3")
        ledger = Ledger(db_path)
        ledger.open()
        _write_binding(ledger)
        ledger.close()

        conn = sqlite3.connect(db_path)
        # Set revision=999, meta_json revision=999, and supersedes_ref so
        # CanonicalMeta contract passes, but integrity_ref won't match.
        conn.execute(
            "UPDATE object_revisions SET revision=999, "
            "meta_json=json_set(json_set(meta_json, '$.revision', 999), "
            "'$.supersedes_ref', 'RunBinding:rb-1:rev1') "
            "WHERE object_type='RunBinding' AND object_id='rb-1' AND revision=1"
        )
        conn.execute(
            "UPDATE object_heads SET current_revision=999 "
            "WHERE object_type='RunBinding' AND object_id='rb-1'"
        )
        conn.commit()
        conn.close()

        ledger2 = Ledger(db_path)
        ledger2.open()
        with pytest.raises(IntegrityCheckFailed):
            ledger2.get_latest("RunBinding", "rb-1")
        ledger2.close()
