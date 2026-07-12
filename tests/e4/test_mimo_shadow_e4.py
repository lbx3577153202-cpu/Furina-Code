"""Tests for MiMo shadow E4 integration."""

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from furina_code.cli import main as cli_main
from furina_code.ledger import Ledger
from tests.e4.conftest import (
    write_candidate_file,
    get_run_binding_id,
)


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class TestDefaultBackend:
    def test_default_backend_is_file(self, tmp_path, capsys):
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
    def test_mimo_backend_unavailable_fails(self, tmp_path, capsys):
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime),
                              "--backend", "mimo-cli"])
        assert exit_code == 1


class TestMimoSchemaValidation:
    def test_invalid_json_rejected(self):
        from furina_code.backend.mimo_cli_adapter import MiMoCodeCLIAdapter
        from furina_code.contracts.errors import ContractInvalid
        from furina_code.backend.port import BackendInvocationRequest
        req = _make_req()
        with pytest.raises(ContractInvalid, match="MIMO_OUTPUT_INVALID_JSON"):
            MiMoCodeCLIAdapter._build_candidate(req, "not json {{{")

    def test_non_object_rejected(self):
        from furina_code.backend.mimo_cli_adapter import MiMoCodeCLIAdapter
        from furina_code.contracts.errors import ContractInvalid
        req = _make_req()
        with pytest.raises(ContractInvalid, match="MIMO_OUTPUT_NOT_OBJECT"):
            MiMoCodeCLIAdapter._build_candidate(req, '["array"]')

    def test_missing_field_rejected(self):
        from furina_code.backend.mimo_cli_adapter import MiMoCodeCLIAdapter
        from furina_code.contracts.errors import ContractInvalid
        req = _make_req()
        with pytest.raises(ContractInvalid, match="MIMO_OUTPUT_MISSING_FIELD"):
            MiMoCodeCLIAdapter._build_candidate(req, json.dumps({
                "repository_head": "abc", "branch": "main"}))

    def test_wrong_type_rejected(self):
        from furina_code.backend.mimo_cli_adapter import MiMoCodeCLIAdapter
        from furina_code.contracts.errors import ContractInvalid
        req = _make_req()
        valid = _valid_content()
        valid["tracked_file_count"] = "not_int"
        with pytest.raises(ContractInvalid, match="MIMO_OUTPUT_WRONG_TYPE"):
            MiMoCodeCLIAdapter._build_candidate(req, json.dumps(valid))

    def test_invalid_working_tree_rejected(self):
        from furina_code.backend.mimo_cli_adapter import MiMoCodeCLIAdapter
        from furina_code.contracts.errors import ContractInvalid
        req = _make_req()
        valid = _valid_content()
        valid["working_tree"] = "unknown"
        with pytest.raises(ContractInvalid, match="MIMO_OUTPUT_INVALID_WORKING_TREE"):
            MiMoCodeCLIAdapter._build_candidate(req, json.dumps(valid))

    def test_valid_candidate_accepted(self):
        from furina_code.backend.mimo_cli_adapter import MiMoCodeCLIAdapter
        req = _make_req()
        result = MiMoCodeCLIAdapter._build_candidate(req, json.dumps(_valid_content()))
        assert result["schema_version"] == "1.0"
        assert result["candidate_type"] == "repository_baseline_report"
        assert result["content"]["repository_head"] == "abc123"


class TestMimoMockClosedLoop:
    def test_mock_closed_loop_with_verification(self, tmp_path, capsys):
        """Mock _run_process to simulate MiMo structured JSON output."""
        from furina_code.backend.mimo_cli_adapter import MiMoCodeCLIAdapter
        from furina_code.backend.port import (
            BackendProbeResult, BackendTransportResult,
            TransportStatus,
        )
        from datetime import datetime, timezone

        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        mimo_response = _valid_content()
        mimo_response["repository_head"] = "a1b2c3d4e5f6"
        mimo_response["tracked_file_count"] = 100
        mimo_jsonl = json.dumps({"type": "text", "part": {"text": json.dumps(mimo_response)}}) + "\n"

        mock_probe = BackendProbeResult(
            available=True, version="mock-1.0", executable_ref="mimo",
            supported_flags=(), model_ids=(), errors=(),
        )

        def mock_run_process(self_inner, plan_inner, temp_cwd, stdout_file, stderr_file,
                             started_at, max_stdout, max_stderr, timeout, args_digest):
            request = plan_inner.request
            with open(stdout_file, "wb") as f:
                f.write(mimo_jsonl.encode("utf-8"))

            text_content = json.loads(mimo_jsonl)["part"]["text"]
            candidate = MiMoCodeCLIAdapter._build_candidate(request, text_content)
            candidate_bytes = json.dumps(candidate, ensure_ascii=False).encode("utf-8")

            candidate_path = self_inner._resolve_candidate_path(request)
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path.write_bytes(candidate_bytes)

            now = datetime.now(timezone.utc).isoformat()
            return BackendTransportResult(
                invocation_id=request.invocation_id,
                request_digest=request.request_digest,
                backend_session_ref=request.backend_session_ref,
                provider_session_ref="mock_session_123",
                provider_ref="mimo-cli",
                executable_version="mimo-cli-1.0",
                started_at=now, finished_at=now,
                command_args_digest=args_digest,
                stdout_ref=None,
                stdout_digest=_sha256_bytes(mimo_jsonl.encode()),
                stdout_bytes=len(mimo_jsonl), stdout_truncated=False,
                stderr_ref=None, stderr_digest=None,
                stderr_bytes=0, stderr_truncated=False,
                candidate_ref=f"{request.sandbox_path_ref}/candidate.json",
                candidate_digest=_sha256_bytes(candidate_bytes),
                manifest_before_ref=None, manifest_before_digest=None,
                manifest_after_ref=None, manifest_after_digest=None,
                transport_status=TransportStatus.SUCCEEDED.value,
                error_code=None, error_detail=None,
            )

        with patch.object(MiMoCodeCLIAdapter, "probe", return_value=mock_probe):
            with patch.object(MiMoCodeCLIAdapter, "_run_process", mock_run_process):
                exit_code = cli_main(["inspect", "prepare",
                                      "--workspace", repo,
                                      "--runtime-dir", str(runtime),
                                      "--backend", "mimo-cli"])

        assert exit_code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out.splitlines()[-1])
        assert output["backend_transport_status"] == "succeeded"

        candidate_path = Path(output["candidate_drop_path"])
        assert candidate_path.exists()
        candidate_data = json.loads(candidate_path.read_text(encoding="utf-8"))
        assert candidate_data["content"]["repository_head"] == "a1b2c3d4e5f6"

        rb_id = output["run_binding_id"]
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        bp_events = [e for e in ledger.get_verified_events(rb_id) if e["event_type"].startswith("BackendProfile.")]
        assert len(bp_events) == 1

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", str(candidate_path)])
        assert exit_code == 0

        events = ledger.get_verified_events(rb_id)
        cv_events = [e for e in events if e["event_type"].startswith("CompletionVerdict.")]
        vv_events = [e for e in events if e["event_type"].startswith("VerificationVerdict.")]
        ledger.close()
        assert len(cv_events) >= 1
        assert len(vv_events) >= 1


class TestAuthorityBoundary:
    def test_adapter_no_ledger_in_prepare(self, tmp_path, capsys):
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        cli_main(["inspect", "prepare",
                  "--workspace", repo,
                  "--runtime-dir", str(runtime),
                  "--backend", "mimo-cli"])
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
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)
        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path])
        assert exit_code == 0
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        events = ledger.get_verified_events(rb_id)
        cv_events = [e for e in events if e["event_type"].startswith("CompletionVerdict.")]
        ledger.close()
        assert len(cv_events) >= 1


def _make_req(**overrides):
    from furina_code.backend.port import BackendInvocationRequest, compute_backend_request_digest
    defaults = dict(
        run_binding_id="rb-test", invocation_id="inv",
        backend_session_ref="s", backend_profile_ref="bp",
        context_ref="ctx", context_digest="cd",
        instruction_text="test", instruction_profile_ref="ip",
        config_ref="c", sandbox_policy_ref="sp",
        request_digest="sha256:" + "0" * 64,
        model_ref=None, timeout_seconds=60,
        max_stdout_bytes=10_000_000, max_stderr_bytes=1_000_000,
        fresh_session=True, sandbox_path_ref="sb",
    )
    defaults.update(overrides)
    req = BackendInvocationRequest(**defaults)
    return BackendInvocationRequest(**{**defaults, "request_digest": compute_backend_request_digest(req)})


def _valid_content():
    return {
        "repository_head": "abc123", "branch": "main", "working_tree": "clean",
        "tracked_file_count": 0, "untracked_file_count": 0,
        "python_requires": None, "runtime_dependencies": [],
        "dev_dependencies": [], "pytest_testpaths": [],
        "ci_config": {"present": False, "sha256": None}, "blind_spots": [],
    }
