"""Tests for MiMoCodeCLIAdapter."""

import ast
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from furina_code.backend.mimo_cli_adapter import MiMoCodeCLIAdapter
from furina_code.backend.port import (
    BackendInvocationRequest,
    BackendProbeRequest,
    BackendTransportResult,
    TransportStatus,
    compute_backend_request_digest,
)
from furina_code.contracts.errors import ContractInvalid


def _make_request(**overrides):
    defaults = dict(
        run_binding_id="rb-test", invocation_id="file-test",
        backend_session_ref="rb-test:file-test",
        backend_profile_ref="sha256:bp",
        context_ref="sha256:ctx", context_digest="sha256:cd",
        instruction_text="respond with exactly: OK",
        instruction_profile_ref="sha256:profile",
        config_ref="e4:mimo-cli:v1",
        sandbox_policy_ref="trusted-runtime-only:v1",
        request_digest="sha256:" + "0" * 64,
        model_ref="mimo/mimo-auto",
        timeout_seconds=60,
        max_stdout_bytes=10_000_000, max_stderr_bytes=1_000_000,
        fresh_session=True, sandbox_path_ref="sandbox/test",
    )
    defaults.update(overrides)
    req = BackendInvocationRequest(**defaults)
    digest = compute_backend_request_digest(req)
    return BackendInvocationRequest(**{**defaults, "request_digest": digest})


def _make_adapter(tmp_path, **kwargs):
    defaults = dict(runtime_root=tmp_path)
    defaults.update(kwargs)
    return MiMoCodeCLIAdapter(**defaults)


def _mock_popen_success(text="OK"):
    """Factory for MockPopen that returns successful JSON output."""
    class MockPopen:
        def __init__(self, args, **kwargs):
            self.returncode = 0
            self.pid = 99999
            self._stdout_dest = kwargs.get("stdout")
            self._stderr_dest = kwargs.get("stderr")
            # Write output to file dests (simulating file-based capture)
            if self._stdout_dest:
                self._stdout_dest.write(
                    json.dumps({"type": "text", "part": {"text": text}}).encode()
                    + b"\n"
                )
                self._stdout_dest.flush()
            if self._stderr_dest:
                self._stderr_dest.write(b"")
                self._stderr_dest.flush()

        def wait(self, timeout=None):
            return 0

    return MockPopen


class TestProbe:
    def test_probe_returns_result(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        result = adapter.probe(BackendProbeRequest(
            executable_ref="mimo", probe_timeout_seconds=10,
        ))
        assert isinstance(result.available, bool)

    def test_probe_unavailable(self, tmp_path):
        adapter = _make_adapter(tmp_path, mimo_executable="nonexistent_mimo_xyz")
        result = adapter.probe(BackendProbeRequest(
            executable_ref="mimo", probe_timeout_seconds=10,
        ))
        assert result.available is False


class TestPrepare:
    def test_prepare_verifies_digest(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)
        assert "run" in plan.executable_args

    def test_prepare_rejects_bad_digest(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = BackendInvocationRequest(
            run_binding_id="rb-test", invocation_id="file-test",
            backend_session_ref="test", backend_profile_ref="sha256:bp",
            context_ref="sha256:ctx", context_digest="sha256:cd",
            instruction_text="test", instruction_profile_ref="sha256:p",
            config_ref="c", sandbox_policy_ref="s",
            request_digest="sha256:" + "ff" * 64,
            model_ref=None, timeout_seconds=60,
            max_stdout_bytes=10_000_000, max_stderr_bytes=1_000_000,
            fresh_session=True, sandbox_path_ref="sandbox/test",
        )
        with pytest.raises(ContractInvalid):
            adapter.prepare(req)

    def test_prepare_no_continue_flag(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)
        assert "--continue" not in plan.executable_args

    def test_prepare_uses_format_json(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)
        assert "--format" in plan.executable_args
        assert "json" in plan.executable_args


class TestInvoke:
    def test_invoke_success_writes_candidate(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen",
                    _mock_popen_success("OK")):
            transport = adapter.invoke(plan)

        assert transport.transport_status == TransportStatus.SUCCEEDED.value

        # Candidate file must exist at runtime_root/sandbox_path_ref/candidate.json
        candidate_path = tmp_path / req.sandbox_path_ref / "candidate.json"
        assert candidate_path.exists()
        data = json.loads(candidate_path.read_bytes())
        assert data["content"]["text"] == "OK"

    def test_candidate_digest_matches_file_bytes(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen",
                    _mock_popen_success("hello")):
            transport = adapter.invoke(plan)

        candidate_path = tmp_path / req.sandbox_path_ref / "candidate.json"
        actual_bytes = candidate_path.read_bytes()
        import hashlib
        expected_digest = "sha256:" + hashlib.sha256(actual_bytes).hexdigest()
        assert transport.candidate_digest == expected_digest

    def test_candidate_persists_after_temp_cleanup(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen",
                    _mock_popen_success("persist")):
            transport = adapter.invoke(plan)

        candidate_path = tmp_path / req.sandbox_path_ref / "candidate.json"
        assert candidate_path.exists()

    def test_invoke_no_continue_in_args(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)

        captured_args = []
        def capture_popen(args, **kwargs):
            captured_args.extend(args)
            return _mock_popen_success()(args, **kwargs)

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", capture_popen):
            adapter.invoke(plan)

        assert "--continue" not in captured_args
        assert "-c" not in captured_args

    def test_invoke_exit_zero_stderr_error(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)

        class ErrorPopen:
            def __init__(self, args, **kwargs):
                self.returncode = 0
                self.pid = 99999
                sout = kwargs.get("stdout")
                serr = kwargs.get("stderr")
                if sout:
                    sout.write(json.dumps({"type": "text", "part": {"text": "hello"}}).encode() + b"\n")
                    sout.flush()
                if serr:
                    serr.write(b"Error: Model not found.\n")
                    serr.flush()

            def wait(self, timeout=None):
                return 0

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", ErrorPopen):
            transport = adapter.invoke(plan)

        assert transport.transport_status == TransportStatus.PROTOCOL_ERROR.value
        assert transport.error_code == "provider_error"

    def test_invoke_invalid_json(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)

        class BadJsonPopen:
            def __init__(self, args, **kwargs):
                self.returncode = 0
                self.pid = 99999
                dest = kwargs.get("stdout")
                if dest:
                    dest.write(b"not json {{{")
                    dest.flush()

            def wait(self, timeout=None):
                return 0

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", BadJsonPopen):
            transport = adapter.invoke(plan)

        assert transport.transport_status == TransportStatus.PROTOCOL_ERROR.value

    def test_invoke_timeout(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request(timeout_seconds=1)
        plan = adapter.prepare(req)

        call_count = [0]
        class TimeoutPopen:
            def __init__(self, args, **kwargs):
                self.returncode = -1
                self.pid = 99999

            def wait(self, timeout=None):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise subprocess.TimeoutExpired(cmd="mimo", timeout=timeout)
                return -1

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", TimeoutPopen):
            with patch("furina_code.backend.mimo_cli_adapter.MiMoCodeCLIAdapter._kill_process_tree"):
                transport = adapter.invoke(plan)

        assert transport.transport_status == TransportStatus.TIMEOUT.value

    def test_invoke_command_args_digest_not_empty(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen",
                    _mock_popen_success()):
            transport = adapter.invoke(plan)

        from furina_code.backend.port import compute_empty_args_digest
        assert transport.command_args_digest != compute_empty_args_digest()

    def test_invoke_stdout_overflow(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request(max_stdout_bytes=10)
        plan = adapter.prepare(req)

        class LargePopen:
            def __init__(self, args, **kwargs):
                self.returncode = 0
                self.pid = 99999
                dest = kwargs.get("stdout")
                if dest:
                    dest.write(b"x" * 100 + b"\n")
                    dest.flush()

            def wait(self, timeout=None):
                return 0

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", LargePopen):
            transport = adapter.invoke(plan)

        assert transport.transport_status == TransportStatus.OUTPUT_TOO_LARGE.value

    def test_invoke_stderr_overflow(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request(max_stderr_bytes=5)
        plan = adapter.prepare(req)

        class StderrOverflowPopen:
            def __init__(self, args, **kwargs):
                self.returncode = 0
                self.pid = 99999
                sout = kwargs.get("stdout")
                serr = kwargs.get("stderr")
                if sout:
                    sout.write(json.dumps({"type": "text", "part": {"text": "OK"}}).encode() + b"\n")
                    sout.flush()
                if serr:
                    serr.write(b"very long stderr output that exceeds limit")
                    serr.flush()

            def wait(self, timeout=None):
                return 0

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", StderrOverflowPopen):
            transport = adapter.invoke(plan)

        assert transport.transport_status == TransportStatus.OUTPUT_TOO_LARGE.value


class TestCollect:
    def test_collect_rebinds_digest(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen",
                    _mock_popen_success("test")):
            transport = adapter.invoke(plan)

        result = adapter.collect(plan, transport)
        assert result.transport_status == TransportStatus.SUCCEEDED.value
        assert result.candidate_digest == transport.candidate_digest

    def test_collect_detects_tampered_file(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen",
                    _mock_popen_success("original")):
            transport = adapter.invoke(plan)

        # Tamper the candidate file
        candidate_path = tmp_path / req.sandbox_path_ref / "candidate.json"
        candidate_path.write_text('{"tampered": true}')

        result = adapter.collect(plan, transport)
        assert result.transport_status == TransportStatus.AMBIGUOUS.value


class TestStrictValidate:
    def test_strict_validate_succeeds(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen",
                    _mock_popen_success()):
            transport = adapter.invoke(plan)

        result = adapter.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.SUCCEEDED.value

    def test_strict_validate_rejects_missing_file(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen",
                    _mock_popen_success()):
            transport = adapter.invoke(plan)

        # Delete candidate file
        candidate_path = tmp_path / req.sandbox_path_ref / "candidate.json"
        candidate_path.unlink()

        result = adapter.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.AMBIGUOUS.value

    def test_strict_validate_rejects_tampered_file(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen",
                    _mock_popen_success()):
            transport = adapter.invoke(plan)

        # Tamper the file
        candidate_path = tmp_path / req.sandbox_path_ref / "candidate.json"
        candidate_path.write_text('{"tampered": true}')

        result = adapter.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.AMBIGUOUS.value

    def test_strict_validate_rejects_bad_request_digest(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request()
        plan = adapter.prepare(req)

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen",
                    _mock_popen_success()):
            transport = adapter.invoke(plan)

        bad_req = BackendInvocationRequest(
            run_binding_id="rb-test", invocation_id="file-test",
            backend_session_ref="test", backend_profile_ref="sha256:bp",
            context_ref="sha256:ctx", context_digest="sha256:cd",
            instruction_text="test", instruction_profile_ref="sha256:p",
            config_ref="c", sandbox_policy_ref="s",
            request_digest="sha256:" + "ff" * 64,
            model_ref=None, timeout_seconds=60,
            max_stdout_bytes=10_000_000, max_stderr_bytes=1_000_000,
            fresh_session=True, sandbox_path_ref="sandbox/test",
        )
        result = adapter.strict_validate(bad_req, transport)
        assert result.transport_status == TransportStatus.AMBIGUOUS.value


class TestAuthorityBoundary:
    def test_no_ledger_import(self):
        path = Path(__file__).resolve().parents[2] / "src" / "furina_code" / "backend" / "mimo_cli_adapter.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "ledger" not in alias.name.lower()
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    assert "ledger" not in node.module.lower()

    def test_no_formal_object_imports(self):
        path = Path(__file__).resolve().parents[2] / "src" / "furina_code" / "backend" / "mimo_cli_adapter.py"
        source = path.read_text(encoding="utf-8")
        for name in ("CandidateEnvelope.create", "BackendProfile.create",
                      "TaskRun.create", "CompletionVerdict.create"):
            assert name not in source

    def test_no_shell_true(self):
        path = Path(__file__).resolve().parents[2] / "src" / "furina_code" / "backend" / "mimo_cli_adapter.py"
        source = path.read_text(encoding="utf-8")
        assert "shell=True" not in source

    def test_plan_refs_no_repo_path(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        repo_path = str(Path(__file__).resolve().parents[2])
        req = _make_request()
        plan = adapter.prepare(req)
        assert repo_path not in plan.cwd_ref
        assert repo_path not in plan.env_policy_ref


class TestPathContainment:
    def test_rejects_absolute_ref(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request(sandbox_path_ref="/etc/passwd")
        plan = adapter.prepare(req)

        class MockPopen:
            def __init__(self, args, **kwargs):
                self.returncode = 0
                self.pid = 99999
            def wait(self, timeout=None):
                return 0

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", MockPopen):
            transport = adapter.invoke(plan)
        assert transport.transport_status == TransportStatus.SANDBOX_VIOLATION.value

    def test_rejects_traversal_ref(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request(sandbox_path_ref="../escape")
        plan = adapter.prepare(req)

        class MockPopen:
            def __init__(self, args, **kwargs):
                self.returncode = 0
                self.pid = 99999
            def wait(self, timeout=None):
                return 0

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", MockPopen):
            transport = adapter.invoke(plan)
        assert transport.transport_status == TransportStatus.SANDBOX_VIOLATION.value

    def test_rejects_empty_ref(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request(sandbox_path_ref="")
        plan = adapter.prepare(req)

        class MockPopen:
            def __init__(self, args, **kwargs):
                self.returncode = 0
                self.pid = 99999
            def wait(self, timeout=None):
                return 0

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", MockPopen):
            transport = adapter.invoke(plan)
        assert transport.transport_status == TransportStatus.SANDBOX_VIOLATION.value

    def test_rejects_runtime_in_forbidden_root(self, tmp_path):
        forbidden = tmp_path / "forbidden"
        forbidden.mkdir()
        inner = forbidden / "child"
        inner.mkdir()
        adapter = _make_adapter(inner, forbidden_roots=(forbidden,))
        req = _make_request(sandbox_path_ref="sandbox/test")
        plan = adapter.prepare(req)

        class MockPopen:
            def __init__(self, args, **kwargs):
                self.returncode = 0
                self.pid = 99999
            def wait(self, timeout=None):
                return 0

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", MockPopen):
            transport = adapter.invoke(plan)
        assert transport.transport_status == TransportStatus.SANDBOX_VIOLATION.value

    def test_rejects_ref_in_forbidden_root(self, tmp_path):
        forbidden = tmp_path / "forbidden"
        forbidden.mkdir()
        adapter = _make_adapter(forbidden, forbidden_roots=(forbidden,))
        req = _make_request(sandbox_path_ref="sandbox/test")
        plan = adapter.prepare(req)

        class MockPopen:
            def __init__(self, args, **kwargs):
                self.returncode = 0
                self.pid = 99999
            def wait(self, timeout=None):
                return 0

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", MockPopen):
            transport = adapter.invoke(plan)
        assert transport.transport_status == TransportStatus.SANDBOX_VIOLATION.value

    def test_normal_relative_sandbox_succeeds(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request(sandbox_path_ref="sandbox/test")
        plan = adapter.prepare(req)

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen",
                    _mock_popen_success("OK")):
            transport = adapter.invoke(plan)
        assert transport.transport_status == TransportStatus.SUCCEEDED.value
        assert (tmp_path / "sandbox" / "test" / "candidate.json").exists()

    def test_no_file_outside_runtime_root(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        adapter = _make_adapter(tmp_path)
        req = _make_request(sandbox_path_ref="../outside/leaked.json")
        plan = adapter.prepare(req)

        class MockPopen:
            def __init__(self, args, **kwargs):
                self.returncode = 0
                self.pid = 99999
            def wait(self, timeout=None):
                return 0

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", MockPopen):
            transport = adapter.invoke(plan)
        assert transport.transport_status == TransportStatus.SANDBOX_VIOLATION.value
        assert not (outside / "leaked.json").exists()

    def test_collect_rejects_bad_path(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request(sandbox_path_ref="sandbox/test")
        plan = adapter.prepare(req)

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen",
                    _mock_popen_success()):
            transport = adapter.invoke(plan)

        # Create a plan with bad ref for collect
        bad_req = _make_request(sandbox_path_ref="../escape")
        bad_plan = adapter.prepare(bad_req)
        result = adapter.collect(bad_plan, transport)
        assert result.transport_status == TransportStatus.SANDBOX_VIOLATION.value

    def test_strict_validate_rejects_bad_path(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        req = _make_request(sandbox_path_ref="sandbox/test")
        plan = adapter.prepare(req)

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen",
                    _mock_popen_success()):
            transport = adapter.invoke(plan)

        bad_req = _make_request(sandbox_path_ref="../escape")
        result = adapter.strict_validate(bad_req, transport)
        assert result.transport_status == TransportStatus.SANDBOX_VIOLATION.value


class TestRealMiMoShadowSmoke:
    @pytest.mark.skipif(
        os.environ.get("MIMO_SMOKE_TEST") != "1",
        reason="MIMO_SMOKE_TEST not set",
    )
    def test_smoke(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        probe = adapter.probe(BackendProbeRequest(
            executable_ref="mimo", probe_timeout_seconds=10,
        ))
        if not probe.available:
            pytest.skip("MiMo not available")

        req = _make_request(
            instruction_text="respond with exactly: SMOKE_OK",
            model_ref="mimo/mimo-auto",
            timeout_seconds=60,
        )
        plan = adapter.prepare(req)
        transport = adapter.invoke(plan)
        assert transport.transport_status == TransportStatus.SUCCEEDED.value

        collected = adapter.collect(plan, transport)
        assert collected.transport_status == TransportStatus.SUCCEEDED.value

        validated = adapter.strict_validate(req, collected)
        assert validated.transport_status == TransportStatus.SUCCEEDED.value
