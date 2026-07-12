"""Tests for MiMo shadow E4 integration."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from furina_code.cli import main as cli_main
from furina_code.ledger import Ledger
from tests.e4.conftest import (
    write_candidate_file,
    get_run_binding_id,
    get_candidate_drop_path,
    get_task_run_id,
)


class TestDefaultBackend:
    def test_default_backend_is_file(self, tmp_path, capsys):
        """Default --backend is file, same as existing behavior."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out.splitlines()[-1])
        assert output["backend_transport_status"] == "awaiting_external"

    def test_explicit_file_backend(self, tmp_path, capsys):
        """--backend file is equivalent to default."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime),
                              "--backend", "file"])
        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out.splitlines()[-1])
        assert output["backend_transport_status"] == "awaiting_external"


class TestMimoRequiresExplicitOptIn:
    def test_mimo_backend_requires_flag(self, tmp_path, capsys):
        """MiMo backend must be explicitly enabled."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        # Without --backend mimo-cli, should use file backend
        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out.splitlines()[-1])
        assert output["backend_transport_status"] == "awaiting_external"

    def test_mimo_backend_unavailable_fails(self, tmp_path, capsys):
        """--backend mimo-cli with unavailable mimo must fail gracefully."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime),
                              "--backend", "mimo-cli"])
        # Should fail because mimo is not on PATH in this context
        assert exit_code == 1


class TestMimoMockIntegration:
    def test_mimo_mock_closed_loop(self, tmp_path, capsys):
        """Mock MiMo returning structured JSON through full prepare -> finalize loop."""
        from furina_code.backend.mimo_cli_adapter import MiMoCodeCLIAdapter
        from furina_code.backend.port import (
            BackendProbeResult, BackendTransportResult,
            TransportStatus, compute_empty_args_digest,
        )
        from furina_code.contracts.meta import canonical_json_dumps
        import hashlib
        from datetime import datetime, timezone

        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        # The structured JSON MiMo should return
        mimo_response = {
            "repository_head": "abc123def456",
            "branch": "main",
            "working_tree": "clean",
            "tracked_file_count": 42,
            "untracked_file_count": 3,
            "python_requires": ">=3.12",
            "runtime_dependencies": ["click"],
            "dev_dependencies": ["pytest"],
            "pytest_testpaths": ["tests"],
            "ci_config": {"present": True, "sha256": "abc123"},
            "blind_spots": ["file contents not inspected"],
        }

        # Build the candidate that the adapter would write
        candidate = {
            "schema_version": "1.0",
            "candidate_type": "repository_baseline_report",
            "backend_profile_ref": "sha256:mock_bp",
            "backend_session_ref": "mock_session",
            "context_ref": "sha256:mock_ctx",
            "context_digest": "sha256:mock_cd",
            "content": mimo_response,
            "claimed_assumptions": [],
            "requested_actions": [],
        }
        candidate_bytes = json.dumps(candidate, ensure_ascii=False).encode("utf-8")
        candidate_digest = "sha256:" + hashlib.sha256(candidate_bytes).hexdigest()

        mock_probe = BackendProbeResult(
            available=True, version="mock-1.0", executable_ref="mimo",
            supported_flags=(), model_ids=(), errors=(),
        )

        # Mock the full adapter lifecycle to return successful results
        def mock_prepare(self, request):
            from furina_code.backend.port import BackendInvocationPlan, compute_backend_request_digest
            verify_digest = compute_backend_request_digest(request)
            return BackendInvocationPlan(
                request=request,
                executable_args=("mimo", "run", "--format", "json"),
                cwd_ref=request.sandbox_path_ref,
                env_policy_ref="mimo-cli:inherit",
                env_key_allowlist=(),
                credential_mode="inherit",
                provider_state_policy_ref="mimo-cli:fresh-session",
            )

        def mock_invoke(self, plan):
            request = plan.request
            now = datetime.now(timezone.utc).isoformat()
            # Write candidate to sandbox
            sandbox = self._runtime_root / request.sandbox_path_ref
            candidate_path = sandbox / "candidate.json"
            candidate_local = {
                "schema_version": "1.0",
                "candidate_type": "repository_baseline_report",
                "backend_profile_ref": request.backend_profile_ref,
                "backend_session_ref": request.backend_session_ref,
                "context_ref": request.context_ref,
                "context_digest": request.context_digest,
                "content": mimo_response,
                "claimed_assumptions": [],
                "requested_actions": [],
            }
            candidate_local_bytes = json.dumps(candidate_local, ensure_ascii=False).encode("utf-8")
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path.write_bytes(candidate_local_bytes)
            return BackendTransportResult(
                invocation_id=request.invocation_id,
                request_digest=request.request_digest,
                backend_session_ref=request.backend_session_ref,
                provider_session_ref="mock_session_123",
                provider_ref="mimo-cli",
                executable_version="mimo-cli-1.0",
                started_at=now, finished_at=now,
                command_args_digest=compute_empty_args_digest(),
                stdout_ref=None,
                stdout_digest="sha256:" + "aa" * 32,
                stdout_bytes=100, stdout_truncated=False,
                stderr_ref=None,
                stderr_digest=None,
                stderr_bytes=0, stderr_truncated=False,
                candidate_ref=f"{request.sandbox_path_ref}/candidate.json",
                candidate_digest="sha256:" + hashlib.sha256(candidate_local_bytes).hexdigest(),
                manifest_before_ref=None, manifest_before_digest=None,
                manifest_after_ref=None, manifest_after_digest=None,
                transport_status=TransportStatus.SUCCEEDED.value,
                error_code=None, error_detail=None,
            )

        with patch.object(MiMoCodeCLIAdapter, "probe", return_value=mock_probe):
            with patch.object(MiMoCodeCLIAdapter, "prepare", mock_prepare):
                with patch.object(MiMoCodeCLIAdapter, "invoke", mock_invoke):
                    exit_code = cli_main(["inspect", "prepare",
                                          "--workspace", repo,
                                          "--runtime-dir", str(runtime),
                                          "--backend", "mimo-cli"])

        assert exit_code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out.splitlines()[-1])
        assert output["backend_transport_status"] == "succeeded"

        # Candidate should exist at deterministic path
        candidate_path = Path(output["candidate_drop_path"])
        assert candidate_path.exists()

        # Candidate should have proper content fields
        candidate_data = json.loads(candidate_path.read_text(encoding="utf-8"))
        assert candidate_data["schema_version"] == "1.0"
        assert candidate_data["candidate_type"] == "repository_baseline_report"
        assert candidate_data["content"]["repository_head"] == "abc123def456"
        assert candidate_data["content"]["branch"] == "main"
        assert candidate_data["content"]["tracked_file_count"] == 42

        # Finalize should consume this candidate
        rb_id = output["run_binding_id"]
        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", str(candidate_path)])
        assert exit_code == 0

        # Verify CompletionVerdict and VerificationVerdict exist
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        events = ledger.get_verified_events(rb_id)
        cv_events = [e for e in events if e["event_type"].startswith("CompletionVerdict.")]
        vv_events = [e for e in events if e["event_type"].startswith("VerificationVerdict.")]
        ledger.close()
        assert len(cv_events) >= 1
        assert len(vv_events) >= 1


class TestAuthorityBoundary:
    def test_adapter_no_ledger_in_prepare(self, tmp_path, capsys):
        """MiMo adapter path must not write Ledger or create formal objects."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        # Even when mimo fails, it shouldn't touch Ledger for adapter operations
        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime),
                              "--backend", "mimo-cli"])

        # The prepare should have created Ledger objects (TaskRun etc.)
        # but the adapter itself should not have written any
        ledger_path = runtime / "inspect.sqlite3"
        if ledger_path.exists():
            ledger = Ledger(str(ledger_path))
            ledger.open()
            conn = ledger.conn
            cur = conn.execute("SELECT DISTINCT run_binding_id FROM event_envelopes LIMIT 1")
            row = cur.fetchone()
            if row:
                events = ledger.get_verified_events(row[0])
                adapter_events = [e for e in events if "mimo" in e.get("producer_organ", "").lower()]
                assert len(adapter_events) == 0
            ledger.close()


class TestFinalizeConsumesMimoCandidate:
    def test_finalize_works_with_any_candidate_source(self, tmp_path, capsys):
        """Finalize should consume candidate regardless of its source (file or mimo)."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        # Use default file backend to create the prepare state
        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])

        # Write a candidate at the deterministic path
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path])
        assert exit_code == 0

        # Verify completion
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        events = ledger.get_verified_events(rb_id)
        cv_events = [e for e in events if e["event_type"].startswith("CompletionVerdict.")]
        ledger.close()
        assert len(cv_events) >= 1
