"""Tests for E4 FileBackend bridge integration."""

import ast
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from furina_code.cli import main as cli_main
from furina_code.backend.file_backend import FileBackend
from furina_code.backend.port import (
    BackendInvocationRequest,
    TransportStatus,
    compute_backend_request_digest,
)
from furina_code.contracts.errors import ContractInvalid
from furina_code.readonly.file_backend_bridge import (
    build_e4_file_backend_request,
    prepare_e4_file_transport,
)


def _get_prepare_output(tmp_path):
    """Run prepare and return parsed output."""
    repo = str(Path(__file__).resolve().parents[2])
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    exit_code = cli_main(["inspect", "prepare",
                          "--workspace", repo,
                          "--runtime-dir", str(runtime)])
    assert exit_code == 0
    # Read stdout from the last print — we need to capture it
    # Instead, read the ledger for verification
    return runtime


class TestPrepareOutputFields:
    def test_prepare_preserves_all_core_fields(self, tmp_path, capsys):
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        # All original fields must be present
        assert "run_binding_id" in output
        assert "task_id" in output
        assert "task_run_id" in output
        assert "project_snapshot_ref" in output
        assert "backend_profile_ref" in output
        assert "context_envelope_ref" in output
        assert "context_packet_path" in output
        assert "context_digest" in output
        assert "status" in output
        assert output["status"] == "AWAITING_EXTERNAL_CANDIDATE"

    def test_prepare_outputs_awaiting_external_transport(self, tmp_path, capsys):
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["backend_transport_status"] == "awaiting_external"

    def test_candidate_drop_path_inside_runtime(self, tmp_path, capsys):
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        drop_path = Path(output["candidate_drop_path"])
        assert str(drop_path).startswith(str(runtime))

    def test_candidate_drop_path_outside_repository(self, tmp_path, capsys):
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        repo_root = Path(repo).resolve()
        drop_path = Path(output["candidate_drop_path"]).resolve()
        try:
            drop_path.relative_to(repo_root)
            pytest.fail("candidate_drop_path must be outside repository")
        except ValueError:
            pass  # good — outside repo

    def test_sandbox_ref_is_relative(self, tmp_path, capsys):
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        sandbox_ref = output["backend_sandbox_ref"]
        assert not Path(sandbox_ref).is_absolute()
        assert ".." not in Path(sandbox_ref).parts
        assert sandbox_ref.startswith("backend/")


class TestRequestIntegrity:
    def test_request_no_absolute_paths(self, tmp_path):
        from furina_code.readonly.context import create_context_envelope, write_context_packet
        from furina_code.world.snapshot import create_project_snapshot
        from furina_code.contracts.objects import TaskDossier, RunBinding

        repo = str(Path(__file__).resolve().parents[2])
        rb_id = "rb-test"
        task_id = "task-test"
        tr_id = "tr-test"
        proj = "test"
        corr = "corr-test"

        # Minimal objects for bridge request
        rb = RunBinding.create(
            run_binding_id=rb_id, task_id=task_id, task_run_id=tr_id,
            project_ref=proj, correlation_id=corr,
            subject_ref="cli", user_ref="cli", task_ref=task_id,
            allowed_tool_classes=("git_read",), source_refs=(),
        )
        td = TaskDossier.create(
            run_binding_id=rb_id, task_id=task_id, task_run_id=tr_id,
            project_ref=proj, correlation_id=corr,
            source_intent_ref="cli:inspect",
            structured_goal="test", success_criteria=(),
            scope=(), exclusions=(), unknowns=(),
            risk_class="low", user_constraints=(),
            causation_ref=rb.meta.integrity_ref,
        )

        snapshot = create_project_snapshot(
            run_binding_id=rb_id, task_id=task_id, task_run_id=tr_id,
            project_ref=proj, correlation_id=corr,
            workspace=repo, causation_ref=td.meta.integrity_ref,
        )
        ctx = create_context_envelope(
            run_binding_id=rb_id, task_id=task_id, task_run_id=tr_id,
            project_ref=proj, correlation_id=corr,
            snapshot=snapshot, dossier=td,
            backend_ref="sha256:test",
            causation_ref=snapshot.meta.integrity_ref,
        )

        request = build_e4_file_backend_request(
            run_binding_id=rb_id,
            task_run_id=tr_id,
            backend_profile_ref="sha256:bp",
            context_ref=ctx.meta.integrity_ref,
            context_digest=ctx.context_digest,
            instruction_profile=ctx.instruction_profile,
        )

        # No absolute paths in any string field
        for field_name in [
            "run_binding_id", "invocation_id", "backend_session_ref",
            "backend_profile_ref", "context_ref", "context_digest",
            "instruction_text", "instruction_profile_ref",
            "config_ref", "sandbox_policy_ref", "sandbox_path_ref",
        ]:
            val = getattr(request, field_name)
            assert not Path(val).is_absolute(), f"{field_name} is absolute: {val}"
            assert ".." not in val, f"{field_name} contains traversal: {val}"

    def test_request_digest_is_valid(self):
        request = build_e4_file_backend_request(
            run_binding_id="rb-test",
            task_run_id="tr-test",
            backend_profile_ref="sha256:bp",
            context_ref="sha256:ctx",
            context_digest="sha256:cd",
            instruction_profile={"id": "test", "version": "1.0"},
        )
        # Should not raise
        from furina_code.backend.port import verify_backend_request_digest
        verify_backend_request_digest(request)

    def test_request_digest_changes_with_instruction_profile(self):
        r1 = build_e4_file_backend_request(
            run_binding_id="rb-test", task_run_id="tr-test",
            backend_profile_ref="sha256:bp", context_ref="sha256:ctx",
            context_digest="sha256:cd",
            instruction_profile={"id": "v1", "version": "1.0"},
        )
        r2 = build_e4_file_backend_request(
            run_binding_id="rb-test", task_run_id="tr-test",
            backend_profile_ref="sha256:bp", context_ref="sha256:ctx",
            context_digest="sha256:cd",
            instruction_profile={"id": "v2", "version": "2.0"},
        )
        assert r1.request_digest != r2.request_digest

    def test_invalid_request_digest_fail_closed(self, tmp_path):
        from furina_code.backend.file_backend import FileBackend
        from furina_code.backend.port import BackendInvocationPlan

        runtime = tmp_path / "runtime"
        runtime.mkdir()
        backend = FileBackend(runtime_root=runtime)

        request = build_e4_file_backend_request(
            run_binding_id="rb-test", task_run_id="tr-test",
            backend_profile_ref="sha256:bp", context_ref="sha256:ctx",
            context_digest="sha256:cd",
            instruction_profile={"id": "test", "version": "1.0"},
        )
        # Tamper with digest
        tampered = BackendInvocationRequest(
            run_binding_id=request.run_binding_id,
            invocation_id=request.invocation_id,
            backend_session_ref=request.backend_session_ref,
            backend_profile_ref=request.backend_profile_ref,
            context_ref=request.context_ref,
            context_digest=request.context_digest,
            instruction_text=request.instruction_text,
            instruction_profile_ref=request.instruction_profile_ref,
            config_ref=request.config_ref,
            sandbox_policy_ref=request.sandbox_policy_ref,
            request_digest="sha256:" + "ff" * 64,
            model_ref=request.model_ref,
            timeout_seconds=request.timeout_seconds,
            max_stdout_bytes=request.max_stdout_bytes,
            max_stderr_bytes=request.max_stderr_bytes,
            fresh_session=request.fresh_session,
            sandbox_path_ref=request.sandbox_path_ref,
        )

        with pytest.raises(ContractInvalid):
            backend.prepare(tampered)


class TestFileBackendAvailability:
    def test_probe_unavailable_on_invalid_root(self):
        from furina_code.backend.file_backend import FileBackend
        from furina_code.backend.port import BackendProbeRequest

        backend = FileBackend(runtime_root=Path("/nonexistent/path/xyz"))
        probe = backend.probe(BackendProbeRequest(
            executable_ref="file-backend", probe_timeout_seconds=5,
        ))
        assert not probe.available
        assert any("runtime_root_invalid" in e for e in probe.errors)

    def test_prepare_unavailable_root_raises(self, tmp_path):
        backend = FileBackend(
            runtime_root=Path("/nonexistent/path/xyz"),
            forbidden_roots=(Path("/forbidden"),),
        )
        request = build_e4_file_backend_request(
            run_binding_id="rb-test", task_run_id="tr-test",
            backend_profile_ref="sha256:bp", context_ref="sha256:ctx",
            context_digest="sha256:cd",
            instruction_profile={"id": "test", "version": "1.0"},
        )
        with pytest.raises(ContractInvalid, match="runtime_root_invalid"):
            backend.prepare(request)

    def test_bridge_raises_on_unavailable_root(self, tmp_path):
        with pytest.raises(ContractInvalid, match="FILE_BACKEND_UNAVAILABLE"):
            prepare_e4_file_transport(
                runtime_dir=Path("/nonexistent/path"),
                repository_root=Path("/forbidden"),
                run_binding_id="rb-test",
                task_run_id="tr-test",
                backend_profile_ref="sha256:bp",
                context_ref="sha256:ctx",
                context_digest="sha256:cd",
                instruction_profile={"id": "test", "version": "1.0"},
            )


class TestSandboxCreated:
    def test_sandbox_dir_created_by_prepare(self, tmp_path, capsys):
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        # The sandbox directory should exist
        sandbox_dir = runtime / output["backend_sandbox_ref"]
        assert sandbox_dir.exists()
        assert sandbox_dir.is_dir()


class TestFinalizeUnchanged:
    def test_full_loop_still_works(self, tmp_path, capsys):
        """Ensure existing prepare → finalize loop is not broken."""
        from tests.e4.conftest import write_candidate_file, get_run_binding_id

        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 0

        # Write candidate into the sandbox (as external agent would)
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        cand_path = Path(output["candidate_drop_path"])
        cand_path.parent.mkdir(parents=True, exist_ok=True)

        # Read context packet for proper candidate content
        ctx_data = json.loads((runtime / "context_packet.json").read_text(encoding="utf-8"))
        from furina_code.ledger import Ledger
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        conn = ledger.conn
        cur = conn.execute("SELECT object_id FROM object_heads WHERE object_type='BackendProfile' LIMIT 1")
        row = cur.fetchone()
        bp_ref = "e4-repository-baseline-v1"
        if row:
            result = ledger.get_latest("BackendProfile", row[0])
            if result:
                bp_ref = result[0].integrity_ref
        ledger.close()

        # Recompute context digest
        import hashlib
        from furina_code.contracts.meta import canonical_json_dumps
        digest_input = {
            "schema_version": ctx_data.get("schema_version", "1.0"),
            "snapshot_ref": ctx_data.get("snapshot_ref"),
            "task_dossier_ref": ctx_data.get("task_dossier_ref"),
            "context_payload": ctx_data.get("context_payload"),
            "instruction_profile": ctx_data.get("instruction_profile"),
        }
        ctx_digest = "sha256:" + hashlib.sha256(
            canonical_json_dumps(digest_input).encode("utf-8")
        ).hexdigest()

        snap = ctx_data.get("context_payload", {}).get("snapshot_summary", {})
        candidate = {
            "schema_version": "1.0",
            "candidate_type": "repository_baseline_report",
            "backend_profile_ref": bp_ref,
            "backend_session_ref": "test-session",
            "context_ref": ctx_data["context_envelope_ref"],
            "context_digest": ctx_digest,
            "content": {
                "repository_head": snap.get("head_sha", "a" * 40),
                "branch": snap.get("branch", "main"),
                "working_tree": "clean",
                "tracked_file_count": snap.get("tracked_file_count", 0),
                "untracked_file_count": snap.get("untracked_file_count", 0),
                "python_requires": snap.get("requires_python"),
                "runtime_dependencies": snap.get("runtime_deps", []),
                "dev_dependencies": snap.get("dev_deps", []),
                "pytest_testpaths": snap.get("pytest_testpaths", []),
                "ci_config": {"present": snap.get("ci_config_exists", False), "sha256": snap.get("ci_config_sha256")},
                "blind_spots": snap.get("blind_spots", []),
            },
            "claimed_assumptions": [],
            "requested_actions": [],
        }
        cand_path.write_text(json.dumps(candidate), encoding="utf-8")

        rb_id = output["run_binding_id"]
        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", str(cand_path)])
        assert exit_code == 0


class TestAuthorityBoundary:
    def test_bridge_does_not_import_ledger(self):
        bridge_path = Path(__file__).resolve().parents[2] / "src" / "furina_code" / "readonly" / "file_backend_bridge.py"
        tree = ast.parse(bridge_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "ledger" not in alias.name.lower(), \
                        f"file_backend_bridge imports ledger: {alias.name}"
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    assert "ledger" not in node.module.lower(), \
                        f"file_backend_bridge imports from ledger: {node.module}"

    def test_bridge_does_not_import_formal_objects(self):
        bridge_path = Path(__file__).resolve().parents[2] / "src" / "furina_code" / "readonly" / "file_backend_bridge.py"
        tree = ast.parse(bridge_path.read_text(encoding="utf-8"))
        forbidden_imports = {"CandidateEnvelope", "BackendProfile", "TaskRun",
                             "CompletionVerdict", "VerificationPlan", "VerificationVerdict"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.names:
                    for alias in node.names:
                        assert alias.name not in forbidden_imports, \
                            f"file_backend_bridge imports formal object: {alias.name}"

    def test_bridge_does_not_create_formal_objects(self):
        bridge_path = Path(__file__).resolve().parents[2] / "src" / "furina_code" / "readonly" / "file_backend_bridge.py"
        source = bridge_path.read_text(encoding="utf-8")
        # No .create() calls on formal objects
        assert "CandidateEnvelope.create" not in source
        assert "BackendProfile.create" not in source
        assert "TaskRun.create" not in source
        assert "CompletionVerdict.create" not in source

    def test_cli_prepare_output_has_three_new_fields(self, tmp_path, capsys):
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert "backend_transport_status" in output
        assert "backend_sandbox_ref" in output
        assert "candidate_drop_path" in output
