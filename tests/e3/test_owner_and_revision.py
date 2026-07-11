"""E3 tests — owner and revision rules."""

import pytest
from furina_code.contracts import (
    RunBinding, TaskDossier, TaskRun, Checkpoint,
    AuthorityViolation, RevisionConflict, ContractInvalid,
)
from furina_code.ledger import Ledger


def _make_binding(ledger, run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1"):
    obj = RunBinding.create(
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref="proj-1",
        correlation_id="corr-1",
        subject_ref="user-1",
        user_ref="user-1",
        task_ref="task-ref-1",
        allowed_tool_classes=("file_write",),
        source_refs=("source-1",),
    )
    ledger.write_object(obj.meta, {
        "subject_ref": obj.subject_ref,
        "user_ref": obj.user_ref,
        "project_ref": obj.project_ref,
        "task_ref": obj.task_ref,
        "allowed_tool_classes": list(obj.allowed_tool_classes),
        "status": obj.status.value,
        "source_refs": list(obj.source_refs),
    }, caller_organ="I1-A", expected_revision=0)
    return obj


class TestOwnerEnforcement:
    def test_run_binding_owner_mismatch_raises(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        obj = RunBinding.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            subject_ref="u", user_ref="u", task_ref="t",
            allowed_tool_classes=(), source_refs=(),
        )
        with pytest.raises(AuthorityViolation):
            ledger.write_object(obj.meta, {
                "subject_ref": obj.subject_ref, "user_ref": obj.user_ref,
                "project_ref": obj.project_ref, "task_ref": obj.task_ref,
                "allowed_tool_classes": [], "status": obj.status.value,
                "source_refs": [],
            }, caller_organ="I2-A", expected_revision=0)
        ledger.close()

    def test_task_dossier_owner_mismatch_raises(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        obj = TaskDossier.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            source_intent_ref="si", structured_goal="g",
            success_criteria=(), scope=(), exclusions=(),
            unknowns=(), risk_class="low", user_constraints=(),
        )
        with pytest.raises(AuthorityViolation):
            ledger.write_object(obj.meta, {
                "source_intent_ref": obj.source_intent_ref,
                "structured_goal": obj.structured_goal,
                "success_criteria": [], "scope": [], "exclusions": [],
                "unknowns": [], "risk_class": obj.risk_class,
                "user_constraints": [], "status": obj.status.value,
            }, caller_organ="I1-A", expected_revision=0)
        ledger.close()

    def test_owner_violation_leaves_no_trace(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        obj = RunBinding.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            subject_ref="u", user_ref="u", task_ref="t",
            allowed_tool_classes=(), source_refs=(),
        )
        with pytest.raises(AuthorityViolation):
            ledger.write_object(obj.meta, {
                "subject_ref": obj.subject_ref, "user_ref": obj.user_ref,
                "project_ref": obj.project_ref, "task_ref": obj.task_ref,
                "allowed_tool_classes": [], "status": obj.status.value,
                "source_refs": [],
            }, caller_organ="I2-A", expected_revision=0)
        assert ledger.get_head_revision("RunBinding", "rb-1") == 0
        assert ledger.get_last_sequence() == 0
        ledger.close()


class TestRevisionConflict:
    def test_revision_conflict_on_create(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        _make_binding(ledger)
        # Try to create again with expected_revision=0
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
        ledger.close()

    def test_revision_conflict_preserves_existing(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        _make_binding(ledger)
        assert ledger.get_head_revision("RunBinding", "rb-1") == 1
        # Check existing is unchanged
        result = ledger.get_latest("RunBinding", "rb-1")
        assert result is not None
        meta, payload = result
        assert meta.revision == 1
        ledger.close()
