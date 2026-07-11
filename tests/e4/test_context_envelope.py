"""E4 tests — ContextEnvelope creation."""

from furina_code.contracts import TaskDossier, TaskDossierStatus
from furina_code.world.snapshot import create_project_snapshot
from furina_code.readonly.context import create_context_envelope, write_context_packet
from pathlib import Path


class TestContextEnvelope:
    def test_create_from_snapshot_and_dossier(self, tmp_path):
        repo = str(Path(__file__).resolve().parents[2])
        snap = create_project_snapshot(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c", workspace=repo,
        )
        dossier = TaskDossier.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            source_intent_ref="cli:inspect",
            structured_goal="Generate repository baseline report",
            success_criteria=("HEAD observed",),
            scope=("metadata",), exclusions=(), unknowns=(),
            risk_class="low", user_constraints=(),
        )
        ctx = create_context_envelope(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            snapshot=snap, dossier=dossier,
        )
        assert ctx.meta.object_type == "ContextEnvelope"
        assert ctx.instruction_profile_id == "e4-repository-baseline-v1"
        assert "structured_goal" in ctx.context_payload
        assert "snapshot_summary" in ctx.context_payload

    def test_context_payload_filtered(self, tmp_path):
        """Context packet should not contain absolute paths or secrets."""
        repo = str(Path(__file__).resolve().parents[2])
        snap = create_project_snapshot(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c", workspace=repo,
        )
        dossier = TaskDossier.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            source_intent_ref="cli:inspect",
            structured_goal="test", success_criteria=(),
            scope=(), exclusions=(), unknowns=(),
            risk_class="low", user_constraints=(),
        )
        ctx = create_context_envelope(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            snapshot=snap, dossier=dossier,
        )
        # No absolute paths in context_payload
        import json
        payload_str = json.dumps(ctx.context_payload)
        assert "E:\\" not in payload_str
        assert "C:\\" not in payload_str

    def test_write_context_packet(self, tmp_path):
        repo = str(Path(__file__).resolve().parents[2])
        snap = create_project_snapshot(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c", workspace=repo,
        )
        dossier = TaskDossier.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            source_intent_ref="cli:inspect",
            structured_goal="test", success_criteria=(),
            scope=(), exclusions=(), unknowns=(),
            risk_class="low", user_constraints=(),
        )
        ctx = create_context_envelope(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            snapshot=snap, dossier=dossier,
        )
        out_path = str(tmp_path / "context.json")
        digest = write_context_packet(ctx, out_path)
        assert digest.startswith("sha256:")
        assert Path(out_path).is_file()
