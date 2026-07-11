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
            backend_ref="sha256:bp",
        )
        assert ctx.meta.object_type == "ContextEnvelope"
        assert ctx.purpose == "repository-baseline-observation"
        assert ctx.context_digest.startswith("sha256:")
        assert len(ctx.redactions) > 0
        assert ctx.backend_ref == "sha256:bp"

    def test_context_no_secrets(self, tmp_path):
        """Context packet must not leak absolute paths, tokens, or env vars."""
        import os
        # Inject decoy values into environment
        decoy_token = "sk-test-decoy-token-12345"
        decoy_env_key = "FURINA_TEST_DECOY_VAR"
        os.environ[decoy_env_key] = decoy_token

        try:
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
            import json
            payload_str = json.dumps(ctx.context_payload)
            full_str = json.dumps(ctx.__dict__, default=str)

            # Absolute paths must not leak
            assert "E:\\" not in payload_str
            assert "C:\\" not in payload_str

            # Decoy token must not leak
            assert decoy_token not in payload_str
            assert decoy_token not in full_str

            # Decoy env key must not leak
            assert decoy_env_key not in payload_str

            # Redactions must cover expected categories
            assert "environment_variables" in ctx.redactions
            assert "credentials" in ctx.redactions
            assert "absolute_workspace_path" in ctx.redactions

            # classification_summary and disclosure_basis must be set
            assert ctx.classification_summary
            assert ctx.disclosure_basis
        finally:
            del os.environ[decoy_env_key]

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
