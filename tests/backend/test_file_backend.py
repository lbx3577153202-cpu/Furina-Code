"""Tests for FileBackend shadow adapter."""

import json
import pytest
from pathlib import Path
from furina_code.backend.file_backend import FileBackend
from furina_code.backend.port import (
    BackendInvocationRequest,
    BackendProbeRequest,
    TransportStatus,
    compute_backend_request_digest,
)


def _make_request(tmp_path, **overrides):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(exist_ok=True)
    defaults = dict(
        run_binding_id="rb-1", invocation_id="inv-1",
        backend_session_ref="rb-1:inv-1", backend_profile_ref="sha256:bp",
        context_ref="sha256:ctx", context_digest="sha256:cd",
        instruction_text="test", instruction_profile_ref="profile:1",
        config_ref="config:1", sandbox_policy_ref="sandbox:1",
        request_digest="sha256:" + "0" * 64,
        model_ref=None, timeout_seconds=60,
        max_stdout_bytes=10_000_000, max_stderr_bytes=1_000_000,
        fresh_session=True, sandbox_path_ref=str(sandbox),
    )
    defaults.update(overrides)
    req = BackendInvocationRequest(**defaults)
    # Fix digest
    digest = compute_backend_request_digest(req)
    return BackendInvocationRequest(
        **{**defaults, "request_digest": digest, "sandbox_path_ref": str(sandbox)},
    )


def _write_valid_candidate(sandbox, context_ref="sha256:ctx", context_digest="sha256:cd",
                           backend_profile_ref="sha256:bp"):
    candidate = {
        "schema_version": "1.0",
        "candidate_type": "repository_baseline_report",
        "backend_profile_ref": backend_profile_ref,
        "backend_session_ref": "test",
        "context_ref": context_ref,
        "context_digest": context_digest,
        "content": {
            "repository_head": "a" * 40, "branch": "main", "working_tree": "clean",
            "tracked_file_count": 10, "untracked_file_count": 0,
            "python_requires": ">=3.12", "runtime_dependencies": [],
            "dev_dependencies": [], "pytest_testpaths": ["tests"],
            "ci_config": {"present": False, "sha256": None}, "blind_spots": [],
        },
        "claimed_assumptions": [], "requested_actions": [],
    }
    path = sandbox / "candidate.json"
    path.write_text(json.dumps(candidate), encoding="utf-8")
    return path


class TestFileBackendProbe:
    def test_probe_returns_available(self):
        fb = FileBackend()
        result = fb.probe(BackendProbeRequest(executable_ref="file-backend", probe_timeout_seconds=30))
        assert result.available is True
        assert result.version == "file-backend-1.0"
        assert result.executable_ref == "file-backend"


class TestFileBackendPrepare:
    def test_prepare_returns_plan(self, tmp_path):
        fb = FileBackend()
        req = _make_request(tmp_path)
        plan = fb.prepare(req)
        assert plan.request is req
        assert plan.executable_args == ()
        assert plan.credential_mode == "none"
        assert plan.env_key_allowlist == ()


class TestFileBackendInvoke:
    def test_awaiting_external(self, tmp_path):
        fb = FileBackend()
        req = _make_request(tmp_path)
        plan = fb.prepare(req)
        result = fb.invoke(plan)
        assert result.transport_status == TransportStatus.AWAITING_EXTERNAL.value
        assert result.error_code is None

    def test_succeeded_with_valid_candidate(self, tmp_path):
        fb = FileBackend()
        req = _make_request(tmp_path)
        _write_valid_candidate(Path(req.sandbox_path_ref))
        plan = fb.prepare(req)
        result = fb.invoke(plan)
        assert result.transport_status == TransportStatus.SUCCEEDED.value
        assert result.candidate_digest is not None
        assert result.candidate_ref == "candidate.json"

    def test_symlink_rejected(self, tmp_path):
        fb = FileBackend()
        req = _make_request(tmp_path)
        sandbox = Path(req.sandbox_path_ref)
        real = sandbox / "real_candidate.json"
        real.write_text("{}")
        link = sandbox / "candidate.json"
        link.symlink_to(real)
        plan = fb.prepare(req)
        result = fb.invoke(plan)
        assert result.transport_status == TransportStatus.SANDBOX_VIOLATION.value


class TestFileBackendStrictValidate:
    def test_pass_on_valid(self, tmp_path):
        fb = FileBackend()
        req = _make_request(tmp_path)
        _write_valid_candidate(Path(req.sandbox_path_ref))
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.SUCCEEDED.value

    def test_context_ref_mismatch(self, tmp_path):
        fb = FileBackend()
        req = _make_request(tmp_path, context_ref="sha256:wrong")
        _write_valid_candidate(Path(req.sandbox_path_ref))
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.CANDIDATE_REJECTED.value

    def test_context_digest_mismatch(self, tmp_path):
        fb = FileBackend()
        req = _make_request(tmp_path, context_digest="sha256:wrong")
        _write_valid_candidate(Path(req.sandbox_path_ref))
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.CANDIDATE_REJECTED.value

    def test_backend_profile_ref_mismatch(self, tmp_path):
        fb = FileBackend()
        req = _make_request(tmp_path, backend_profile_ref="sha256:wrong")
        _write_valid_candidate(Path(req.sandbox_path_ref))
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.CANDIDATE_REJECTED.value

    def test_requested_actions_non_empty(self, tmp_path):
        fb = FileBackend()
        req = _make_request(tmp_path)
        sandbox = Path(req.sandbox_path_ref)
        candidate = {
            "schema_version": "1.0", "candidate_type": "repository_baseline_report",
            "backend_profile_ref": "sha256:bp", "backend_session_ref": "test",
            "context_ref": "sha256:ctx", "context_digest": "sha256:cd",
            "content": {"repository_head": "a" * 40, "branch": "main",
                        "working_tree": "clean", "tracked_file_count": 0,
                        "untracked_file_count": 0, "python_requires": None,
                        "runtime_dependencies": [], "dev_dependencies": [],
                        "pytest_testpaths": [], "ci_config": {"present": False, "sha256": None},
                        "blind_spots": []},
            "claimed_assumptions": [], "requested_actions": ["write_file"],
        }
        (sandbox / "candidate.json").write_text(json.dumps(candidate))
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.CANDIDATE_REJECTED.value

    def test_invalid_json(self, tmp_path):
        fb = FileBackend()
        req = _make_request(tmp_path)
        sandbox = Path(req.sandbox_path_ref)
        (sandbox / "candidate.json").write_text("not json")
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.PROTOCOL_ERROR.value

    def test_extra_text_before_json(self, tmp_path):
        fb = FileBackend()
        req = _make_request(tmp_path)
        sandbox = Path(req.sandbox_path_ref)
        # This will fail JSON parsing
        (sandbox / "candidate.json").write_text("Here is the result:\n{}")
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.PROTOCOL_ERROR.value

    def test_not_succeeded_skips_validate(self, tmp_path):
        fb = FileBackend()
        req = _make_request(tmp_path)
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        assert transport.transport_status == TransportStatus.AWAITING_EXTERNAL.value
        result = fb.strict_validate(req, transport)
        # Should pass through unchanged
        assert result.transport_status == TransportStatus.AWAITING_EXTERNAL.value
