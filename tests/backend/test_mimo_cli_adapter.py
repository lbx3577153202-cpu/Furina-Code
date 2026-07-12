"""Tests for MiMoCodeCLIAdapter."""

import ast
import hashlib
import json
import os
import subprocess
import sys
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
        run_binding_id="rb-test",
        invocation_id="file-test",
        backend_session_ref="rb-test:file-test",
        backend_profile_ref="sha256:bp",
        context_ref="sha256:ctx",
        context_digest="sha256:cd",
        instruction_text="respond with exactly: OK",
        instruction_profile_ref="sha256:profile",
        config_ref="e4:mimo-cli:v1",
        sandbox_policy_ref="trusted-runtime-only:v1",
        request_digest="sha256:" + "0" * 64,
        model_ref="mimo/mimo-auto",
        timeout_seconds=60,
        max_stdout_bytes=10_000_000,
        max_stderr_bytes=1_000_000,
        fresh_session=True,
        sandbox_path_ref="sandbox/test",
    )
    defaults.update(overrides)
    req = BackendInvocationRequest(**defaults)
    digest = compute_backend_request_digest(req)
    return BackendInvocationRequest(**{**defaults, "request_digest": digest})


def _make_transport(request, **overrides):
    defaults = dict(
        invocation_id=request.invocation_id,
        request_digest=request.request_digest,
        backend_session_ref=request.backend_session_ref,
        provider_session_ref=None,
        provider_ref="mimo-cli",
        executable_version="1.0",
        started_at="2024-01-01T00:00:00Z",
        finished_at="2024-01-01T00:00:01Z",
        command_args_digest="sha256:" + "0" * 64,
        stdout_ref=None, stdout_digest=None, stdout_bytes=0, stdout_truncated=False,
        stderr_ref=None, stderr_digest=None, stderr_bytes=0, stderr_truncated=False,
        candidate_ref="sandbox/candidate.json",
        candidate_digest="sha256:" + "aa" * 32,
        manifest_before_ref=None, manifest_before_digest=None,
        manifest_after_ref=None, manifest_after_digest=None,
        transport_status=TransportStatus.SUCCEEDED.value,
        error_code=None, error_detail=None,
    )
    defaults.update(overrides)
    return BackendTransportResult(**defaults)


class TestProbe:
    def test_probe_returns_result(self):
        """Probe returns a result (available may be False if mimo not on PATH)."""
        adapter = MiMoCodeCLIAdapter()
        result = adapter.probe(BackendProbeRequest(
            executable_ref="mimo", probe_timeout_seconds=10,
        ))
        assert isinstance(result.available, bool)
        assert result.executable_ref == "mimo"

    def test_probe_unavailable(self):
        adapter = MiMoCodeCLIAdapter(mimo_executable="nonexistent_mimo_xyz")
        result = adapter.probe(BackendProbeRequest(
            executable_ref="mimo", probe_timeout_seconds=10,
        ))
        assert result.available is False
        assert any("executable_not_found" in e for e in result.errors)


class TestPrepare:
    def test_prepare_verifies_digest(self):
        adapter = MiMoCodeCLIAdapter()
        req = _make_request()
        plan = adapter.prepare(req)
        assert plan.request == req
        assert "run" in plan.executable_args

    def test_prepare_rejects_bad_digest(self):
        adapter = MiMoCodeCLIAdapter()
        # Create request with intentionally wrong digest (bypass _make_request helper)
        req = BackendInvocationRequest(
            run_binding_id="rb-test", invocation_id="file-test",
            backend_session_ref="rb-test:file-test",
            backend_profile_ref="sha256:bp",
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

    def test_prepare_no_continue_flag(self):
        adapter = MiMoCodeCLIAdapter()
        req = _make_request()
        plan = adapter.prepare(req)
        assert "--continue" not in plan.executable_args
        assert "-c" not in plan.executable_args

    def test_prepare_uses_format_json(self):
        adapter = MiMoCodeCLIAdapter()
        req = _make_request()
        plan = adapter.prepare(req)
        assert "--format" in plan.executable_args
        assert "json" in plan.executable_args


class TestInvoke:
    def test_invoke_success(self):
        adapter = MiMoCodeCLIAdapter()
        req = _make_request()
        plan = adapter.prepare(req)

        class MockPopen:
            def __init__(self, args, **kwargs):
                self.returncode = 0
                self.stdout = MagicMock()
                self.stderr = MagicMock()
                self.pid = 99999

            def communicate(self, timeout=None):
                return (
                    json.dumps({"type": "text", "part": {"text": "OK"}}).encode()
                    + b"\n",
                    b"",
                )

            def wait(self):
                return 0

            def read(self):
                return b""

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", MockPopen):
            transport = adapter.invoke(plan)

        assert transport.transport_status == TransportStatus.SUCCEEDED.value
        assert transport.candidate_ref is not None
        assert transport.candidate_digest is not None

    def test_invoke_creates_temp_cwd(self):
        adapter = MiMoCodeCLIAdapter()
        req = _make_request()
        plan = adapter.prepare(req)

        captured_cwds = []

        class MockPopen:
            def __init__(self, args, **kwargs):
                captured_cwds.append(kwargs.get("cwd"))
                self.returncode = 0
                self.stdout = MagicMock()
                self.stderr = MagicMock()
                self.pid = 99999

            def communicate(self, timeout=None):
                return (
                    json.dumps({"type": "text", "part": {"text": "OK"}}).encode() + b"\n",
                    b"",
                )

            def wait(self):
                return 0

            def read(self):
                return b""

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", MockPopen):
            adapter.invoke(plan)

        assert len(captured_cwds) == 1

    def test_invoke_no_continue_flag(self):
        adapter = MiMoCodeCLIAdapter()
        req = _make_request()
        plan = adapter.prepare(req)

        captured_args = []

        class MockPopen:
            def __init__(self, args, **kwargs):
                captured_args.extend(args)
                self.returncode = 0
                self.stdout = MagicMock()
                self.stderr = MagicMock()
                self.pid = 99999

            def communicate(self, timeout=None):
                return (
                    json.dumps({"type": "text", "part": {"text": "OK"}}).encode() + b"\n",
                    b"",
                )

            def wait(self):
                return 0

            def read(self):
                return b""

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", MockPopen):
            adapter.invoke(plan)

        assert "--continue" not in captured_args
        assert "-c" not in captured_args

    def test_invoke_exit_code_zero_stderr_error(self):
        adapter = MiMoCodeCLIAdapter()
        req = _make_request()
        plan = adapter.prepare(req)

        class MockPopen:
            def __init__(self, args, **kwargs):
                self.returncode = 0
                self.stdout = MagicMock()
                self.stderr = MagicMock()
                self.pid = 99999

            def communicate(self, timeout=None):
                return (
                    b'{"type":"text","part":{"text":"hello"}}\n',
                    b"Error: Model not found: nonexistent/provider.\n",
                )

            def wait(self):
                return 0

            def read(self):
                return b""

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", MockPopen):
            transport = adapter.invoke(plan)

        assert transport.transport_status == TransportStatus.PROTOCOL_ERROR.value
        assert transport.error_code == "provider_error"

    def test_invoke_invalid_json(self):
        adapter = MiMoCodeCLIAdapter()
        req = _make_request()
        plan = adapter.prepare(req)

        class MockPopen:
            def __init__(self, args, **kwargs):
                self.returncode = 0
                self.stdout = MagicMock()
                self.stderr = MagicMock()
                self.pid = 99999

            def communicate(self, timeout=None):
                return (b"not valid json at all {{{", b"")

            def wait(self):
                return 0

            def read(self):
                return b""

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", MockPopen):
            transport = adapter.invoke(plan)

        assert transport.transport_status == TransportStatus.PROTOCOL_ERROR.value

    def test_invoke_timeout_kills_process(self):
        adapter = MiMoCodeCLIAdapter()
        req = _make_request(timeout_seconds=1)
        plan = adapter.prepare(req)

        class MockPopen:
            def __init__(self, args, **kwargs):
                self.returncode = -1
                self.stdout = MagicMock()
                self.stderr = MagicMock()
                self.stdout.read.return_value = b"partial"
                self.stderr.read.return_value = b"err"
                self.pid = 99999

            def communicate(self, timeout=None):
                raise subprocess.TimeoutExpired(cmd="mimo", timeout=timeout)

            def wait(self):
                return -1

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", MockPopen):
            with patch("furina_code.backend.mimo_cli_adapter.MiMoCodeCLIAdapter._kill_process_tree") as mock_kill:
                transport = adapter.invoke(plan)

        assert transport.transport_status == TransportStatus.TIMEOUT.value
        mock_kill.assert_called_once()

    def test_invoke_temp_cwd_cleaned(self):
        adapter = MiMoCodeCLIAdapter()
        req = _make_request()
        plan = adapter.prepare(req)

        created_cwds = []

        class MockPopen:
            def __init__(self, args, **kwargs):
                cwd = kwargs.get("cwd")
                if cwd:
                    created_cwds.append(cwd)
                self.returncode = 0
                self.stdout = MagicMock()
                self.stderr = MagicMock()
                self.pid = 99999

            def communicate(self, timeout=None):
                return (
                    json.dumps({"type": "text", "part": {"text": "OK"}}).encode() + b"\n",
                    b"",
                )

            def wait(self):
                return 0

            def read(self):
                return b""

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", MockPopen):
            adapter.invoke(plan)

        for cwd in created_cwds:
            assert not Path(cwd).exists(), f"Temp CWD {cwd} was not cleaned up"

    def test_invoke_stdout_truncated(self):
        adapter = MiMoCodeCLIAdapter()
        req = _make_request(max_stdout_bytes=100)
        plan = adapter.prepare(req)

        large_text = "x" * 200

        class MockPopen:
            def __init__(self, args, **kwargs):
                self.returncode = 0
                self.stdout = MagicMock()
                self.stderr = MagicMock()
                self.pid = 99999

            def communicate(self, timeout=None):
                return (
                    json.dumps({"type": "text", "part": {"text": large_text}}).encode() + b"\n",
                    b"",
                )

            def wait(self):
                return 0

            def read(self):
                return b""

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", MockPopen):
            transport = adapter.invoke(plan)

        assert transport.stdout_truncated is True

    def test_invoke_stderr_captured(self):
        adapter = MiMoCodeCLIAdapter()
        req = _make_request()
        plan = adapter.prepare(req)

        class MockPopen:
            def __init__(self, args, **kwargs):
                self.returncode = 0
                self.stdout = MagicMock()
                self.stderr = MagicMock()
                self.pid = 99999

            def communicate(self, timeout=None):
                return (
                    json.dumps({"type": "text", "part": {"text": "OK"}}).encode() + b"\n",
                    b"some warning on stderr\n",
                )

            def wait(self):
                return 0

            def read(self):
                return b""

        with patch("furina_code.backend.mimo_cli_adapter.subprocess.Popen", MockPopen):
            transport = adapter.invoke(plan)

        assert transport.stderr_bytes > 0


class TestStrictValidate:
    def test_strict_validate_succeeds(self):
        adapter = MiMoCodeCLIAdapter()
        req = _make_request()
        transport = _make_transport(req)
        result = adapter.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.SUCCEEDED.value

    def test_strict_validate_rejects_missing_candidate_ref(self):
        adapter = MiMoCodeCLIAdapter()
        req = _make_request()
        transport = _make_transport(req, candidate_ref=None, candidate_digest=None)
        result = adapter.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.AMBIGUOUS.value

    def test_strict_validate_rejects_digest_mismatch(self):
        adapter = MiMoCodeCLIAdapter()
        req = _make_request()
        transport = _make_transport(req, request_digest="sha256:" + "ff" * 64)
        result = adapter.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.AMBIGUOUS.value


class TestAuthorityBoundary:
    def test_adapter_does_not_import_ledger(self):
        adapter_path = Path(__file__).resolve().parents[2] / "src" / "furina_code" / "backend" / "mimo_cli_adapter.py"
        tree = ast.parse(adapter_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "ledger" not in alias.name.lower()
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    assert "ledger" not in node.module.lower()

    def test_adapter_does_not_import_formal_objects(self):
        adapter_path = Path(__file__).resolve().parents[2] / "src" / "furina_code" / "backend" / "mimo_cli_adapter.py"
        source = adapter_path.read_text(encoding="utf-8")
        assert "CandidateEnvelope.create" not in source
        assert "BackendProfile.create" not in source
        assert "TaskRun.create" not in source
        assert "CompletionVerdict.create" not in source

    def test_adapter_no_shell_true(self):
        adapter_path = Path(__file__).resolve().parents[2] / "src" / "furina_code" / "backend" / "mimo_cli_adapter.py"
        source = adapter_path.read_text(encoding="utf-8")
        assert "shell=True" not in source

    def test_adapter_uses_subprocess(self):
        adapter_path = Path(__file__).resolve().parents[2] / "src" / "furina_code" / "backend" / "mimo_cli_adapter.py"
        source = adapter_path.read_text(encoding="utf-8")
        assert "subprocess" in source

    def test_no_repo_path_in_plan_refs(self):
        """Plan refs (cwd_ref, env_policy_ref, etc.) must not contain repo paths."""
        adapter = MiMoCodeCLIAdapter()
        repo_path = str(Path(__file__).resolve().parents[2])
        req = _make_request(instruction_text="do something")
        plan = adapter.prepare(req)
        # Check that plan-level refs don't contain repo path
        assert repo_path not in plan.cwd_ref
        assert repo_path not in plan.env_policy_ref
        assert repo_path not in plan.credential_mode
        assert repo_path not in plan.provider_state_policy_ref


class TestRealMiMoShadowSmoke:
    """Opt-in smoke test with real MiMo."""

    @pytest.mark.skipif(
        os.environ.get("MIMO_SMOKE_TEST") != "1",
        reason="MIMO_SMOKE_TEST not set",
    )
    def test_real_mimo_shadow_smoke(self, tmp_path):
        adapter = MiMoCodeCLIAdapter()
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

        assert transport.transport_status == TransportStatus.SUCCEEDED.value, \
            f"Failed: {transport.error_code} — {transport.error_detail}"

        assert transport.candidate_ref is not None
        assert transport.candidate_digest is not None

        validated = adapter.strict_validate(req, transport)
        assert validated.transport_status == TransportStatus.SUCCEEDED.value
