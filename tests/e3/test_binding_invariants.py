"""E3.1 tests — binding invariants and stable identity enforcement."""

import pytest
from datetime import datetime, timezone
from furina_code.contracts import (
    RunBinding, TaskRun, CanonicalMeta, SCHEMA_VERSION, compute_integrity_ref,
    BindingMismatch, AuthorityViolation, Phase, Disposition, now_utc, OWNER_MAP,
)
from furina_code.ledger import Ledger


def _create_task_run(ledger, run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1"):
    tr = TaskRun.create(
        run_binding_id=run_binding_id, task_id=task_id, task_run_id=task_run_id,
        project_ref="proj-1", correlation_id="c-1", task_revision=1,
    )
    ledger.write_object(tr.meta, {
        "task_revision": tr.task_revision, "phase": tr.phase.value,
        "disposition": tr.disposition.value, "current_refs": [],
        "open_requests": [], "started_at": tr.started_at.isoformat(),
        "terminal_reason": tr.terminal_reason,
    }, caller_organ="I2-D", expected_revision=0)
    return tr


def _make_revision2_meta(ledger, original_meta, **overrides):
    """Build a revision-2 CanonicalMeta, optionally overriding stable fields."""
    now = now_utc()
    fields = {
        "schema_version": original_meta.schema_version,
        "object_type": original_meta.object_type,
        "object_id": original_meta.object_id,
        "owner_organ": original_meta.owner_organ,
        "run_binding_id": original_meta.run_binding_id,
        "task_id": original_meta.task_id,
        "task_run_id": original_meta.task_run_id,
        "project_ref": original_meta.project_ref,
    }
    fields.update(overrides)
    supersedes = f"{fields['object_type']}:{fields['object_id']}:rev1"
    payload = {"phase": "observe", "disposition": "active"}
    meta_fields = {
        **fields,
        "revision": 2,
        "correlation_id": "c-1",
        "causation_ref": supersedes,
        "created_at": now.isoformat(),
        "recorded_at": now.isoformat(),
        "classification": "project_internal",
        "supersedes_ref": supersedes,
    }
    integrity = compute_integrity_ref(meta_fields, payload)
    return CanonicalMeta(
        revision=2, correlation_id="c-1", causation_ref=supersedes,
        created_at=now, recorded_at=now,
        classification="project_internal",
        integrity_ref=integrity, supersedes_ref=supersedes,
        **fields,
    ), payload


class TestStableIdentityEnforcement:
    def test_run_binding_id_drift_rejected(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _create_task_run(ledger)
        meta2, payload2 = _make_revision2_meta(ledger, tr.meta, run_binding_id="rb-OTHER")
        with pytest.raises(BindingMismatch) as exc_info:
            ledger.write_object(meta2, payload2, caller_organ="I2-D", expected_revision=1)
        assert "run_binding_id" in str(exc_info.value.details.get("field", ""))
        ledger.close()

    def test_task_id_drift_rejected(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _create_task_run(ledger)
        meta2, payload2 = _make_revision2_meta(ledger, tr.meta, task_id="t-OTHER")
        with pytest.raises(BindingMismatch) as exc_info:
            ledger.write_object(meta2, payload2, caller_organ="I2-D", expected_revision=1)
        assert "task_id" in str(exc_info.value.details.get("field", ""))
        ledger.close()

    def test_task_run_id_drift_rejected(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _create_task_run(ledger)
        meta2, payload2 = _make_revision2_meta(ledger, tr.meta, task_run_id="tr-OTHER")
        with pytest.raises(BindingMismatch) as exc_info:
            ledger.write_object(meta2, payload2, caller_organ="I2-D", expected_revision=1)
        assert "task_run_id" in str(exc_info.value.details.get("field", ""))
        ledger.close()

    def test_project_ref_drift_rejected(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _create_task_run(ledger)
        meta2, payload2 = _make_revision2_meta(ledger, tr.meta, project_ref="proj-OTHER")
        with pytest.raises(BindingMismatch) as exc_info:
            ledger.write_object(meta2, payload2, caller_organ="I2-D", expected_revision=1)
        assert "project_ref" in str(exc_info.value.details.get("field", ""))
        ledger.close()

    def test_owner_organ_drift_rejected(self, tmp_path):
        """owner_organ drift is caught by check_owner as AUTHORITY_VIOLATION."""
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _create_task_run(ledger)
        meta2, payload2 = _make_revision2_meta(ledger, tr.meta, owner_organ="I9-X")
        with pytest.raises(AuthorityViolation):
            ledger.write_object(meta2, payload2, caller_organ="I2-D", expected_revision=1)
        ledger.close()

    def test_object_type_drift_rejected(self, tmp_path):
        """object_type drift is caught by check_owner as AUTHORITY_VIOLATION."""
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _create_task_run(ledger)
        meta2, payload2 = _make_revision2_meta(ledger, tr.meta, object_type="RunBinding")
        with pytest.raises(AuthorityViolation):
            ledger.write_object(meta2, payload2, caller_organ="I2-D", expected_revision=1)
        ledger.close()

    def test_unchanged_identity_accepted(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _create_task_run(ledger)
        # Valid transition through the normal path
        tr2 = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        ledger.write_object(tr2.meta, {
            "task_revision": tr2.task_revision, "phase": tr2.phase.value,
            "disposition": tr2.disposition.value, "current_refs": [],
            "open_requests": [], "started_at": tr2.started_at.isoformat(),
            "terminal_reason": tr2.terminal_reason,
        }, caller_organ="I2-D", expected_revision=1)
        assert ledger.get_head_revision("TaskRun", "tr-1") == 2
        ledger.close()

    def test_binding_drift_leaves_head_unchanged(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _create_task_run(ledger)
        meta2, payload2 = _make_revision2_meta(ledger, tr.meta, run_binding_id="rb-OTHER")
        with pytest.raises(BindingMismatch):
            ledger.write_object(meta2, payload2, caller_organ="I2-D", expected_revision=1)
        assert ledger.get_head_revision("TaskRun", "tr-1") == 1
        events = ledger.get_events("rb-1")
        assert len(events) == 1
        ledger.close()

    def test_transition_cannot_modify_binding(self, tmp_path):
        """TaskRun.transition() inherits identity — caller cannot change binding fields."""
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _create_task_run(ledger, run_binding_id="rb-X", task_id="t-X", task_run_id="tr-X")
        tr2 = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        assert tr2.meta.run_binding_id == "rb-X"
        assert tr2.meta.task_id == "t-X"
        assert tr2.meta.task_run_id == "tr-X"
        assert tr2.meta.project_ref == "proj-1"
        ledger.close()
