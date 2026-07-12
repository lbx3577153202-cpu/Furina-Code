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
from furina_code.contracts.errors import ContractInvalid


def _make_request(tmp_path, **overrides):
    sandbox_ref = overrides.pop("sandbox_path_ref", "sandbox")
    defaults = dict(
        run_binding_id="rb-1", invocation_id="inv-1",
        backend_session_ref="rb-1:inv-1", backend_profile_ref="sha256:bp",
        context_ref="sha256:ctx", context_digest="sha256:cd",
        instruction_text="test instruction", instruction_profile_ref="profile:1",
        config_ref="config:1", sandbox_policy_ref="sandbox:1",
        request_digest="sha256:" + "0" * 64,
        model_ref=None, timeout_seconds=60,
        max_stdout_bytes=10_000_000, max_stderr_bytes=1_000_000,
        fresh_session=True, sandbox_path_ref=sandbox_ref,
    )
    defaults.update(overrides)
    req = BackendInvocationRequest(**defaults)
    digest = compute_backend_request_digest(req)
    return BackendInvocationRequest(**{**defaults, "request_digest": digest})


def _write_valid_candidate(sandbox, **overrides):
    candidate = {
        "schema_version": "1.0",
        "candidate_type": "repository_baseline_report",
        "backend_profile_ref": overrides.get("backend_profile_ref", "sha256:bp"),
        "backend_session_ref": "test",
        "context_ref": overrides.get("context_ref", "sha256:ctx"),
        "context_digest": overrides.get("context_digest", "sha256:cd"),
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
    def test_probe_available(self, tmp_path):
        fb = FileBackend(tmp_path)
        result = fb.probe(BackendProbeRequest(executable_ref="file-backend", probe_timeout_seconds=30))
        assert result.available is True
        assert result.version == "file-backend-1.0"

    def test_probe_unavailable_missing_root(self, tmp_path):
        fb = FileBackend(tmp_path / "nonexistent")
        result = fb.probe(BackendProbeRequest(executable_ref="file-backend", probe_timeout_seconds=30))
        assert result.available is False
        assert "runtime_root_invalid" in result.errors

    def test_probe_unavailable_file_not_dir(self, tmp_path):
        root_file = tmp_path / "rootfile"
        root_file.write_text("x")
        fb = FileBackend(root_file)
        result = fb.probe(BackendProbeRequest(executable_ref="file-backend", probe_timeout_seconds=30))
        assert result.available is False
        assert "runtime_root_invalid" in result.errors


class TestFileBackendPrepare:
    def test_prepare_verifies_digest(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        plan = fb.prepare(req)
        assert plan.request is req
        assert plan.credential_mode == "none"

    def test_prepare_fails_on_invalid_digest(self, tmp_path):
        fb = FileBackend(tmp_path)
        # Create request with intentionally wrong digest directly
        req = BackendInvocationRequest(
            run_binding_id="rb-1", invocation_id="inv-1",
            backend_session_ref="rb-1:inv-1", backend_profile_ref="sha256:bp",
            context_ref="sha256:ctx", context_digest="sha256:cd",
            instruction_text="test", instruction_profile_ref="profile:1",
            config_ref="config:1", sandbox_policy_ref="sandbox:1",
            request_digest="sha256:" + "f" * 64,
            model_ref=None, timeout_seconds=60,
            max_stdout_bytes=10_000_000, max_stderr_bytes=1_000_000,
            fresh_session=True, sandbox_path_ref="sandbox",
        )
        with pytest.raises(ContractInvalid):
            fb.prepare(req)

    def test_prepare_rejects_traversal_ref(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path, sandbox_path_ref="../escape")
        with pytest.raises(Exception):
            fb.prepare(req)


class TestFileBackendInvoke:
    def test_awaiting_external(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        plan = fb.prepare(req)
        result = fb.invoke(plan)
        assert result.transport_status == TransportStatus.AWAITING_EXTERNAL.value

    def test_succeeded_path_exists(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        (sandbox / "candidate.json").write_text("{}")
        plan = fb.prepare(req)
        result = fb.invoke(plan)
        assert result.transport_status == TransportStatus.SUCCEEDED.value

    def test_symlink_rejected(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        real = sandbox / "real.json"
        real.write_text("{}")
        link = sandbox / "candidate.json"
        link.symlink_to(real)
        plan = fb.prepare(req)
        result = fb.invoke(plan)
        assert result.transport_status == TransportStatus.SANDBOX_VIOLATION.value

    def test_invoke_does_not_read_content(self, tmp_path):
        """invoke only checks existence, not content."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        # Write invalid content — invoke should still succeed (only checks existence)
        (sandbox / "candidate.json").write_bytes(b"\x80\x81")  # invalid UTF-8
        plan = fb.prepare(req)
        result = fb.invoke(plan)
        assert result.transport_status == TransportStatus.SUCCEEDED.value


class TestFileBackendCollect:
    def test_collect_reads_candidate(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)
        result = fb.collect(plan, invoke_result)
        assert result.transport_status == TransportStatus.SUCCEEDED.value
        assert result.candidate_digest is not None
        assert result.candidate_ref == "output/collected_candidate.json"

    def test_collect_creates_canonical_artifact(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)
        fb.collect(plan, invoke_result)
        canonical = sandbox / "output" / "collected_candidate.json"
        assert canonical.exists()

    def test_collect_invalid_utf8(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        (sandbox / "candidate.json").write_bytes(b"\x80\x81\x82")
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)
        result = fb.collect(plan, invoke_result)
        assert result.transport_status == TransportStatus.INVALID_UTF8.value

    def test_collect_invalid_json(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        (sandbox / "candidate.json").write_text("not json")
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)
        result = fb.collect(plan, invoke_result)
        assert result.transport_status == TransportStatus.PROTOCOL_ERROR.value

    def test_collect_candidate_mutation_safe(self, tmp_path):
        """After collect, modifying original candidate doesn't change frozen evidence."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)
        collect_result = fb.collect(plan, invoke_result)
        original_digest = collect_result.candidate_digest

        # Mutate original
        (sandbox / "candidate.json").write_text('{"mutated": true}')

        # Canonical artifact digest should still match
        canonical = sandbox / "output" / "collected_candidate.json"
        canonical_bytes = canonical.read_bytes()
        import hashlib
        canonical_digest = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
        assert original_digest == canonical_digest


class TestFileBackendStrictValidate:
    def test_pass_on_valid(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        transport = fb.collect(plan, transport)
        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.SUCCEEDED.value

    def test_context_ref_mismatch(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path, context_ref="sha256:wrong")
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        transport = fb.collect(plan, transport)
        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.CANDIDATE_REJECTED.value

    def test_context_digest_mismatch(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path, context_digest="sha256:wrong")
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        transport = fb.collect(plan, transport)
        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.CANDIDATE_REJECTED.value

    def test_backend_profile_ref_mismatch(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path, backend_profile_ref="sha256:wrong")
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        transport = fb.collect(plan, transport)
        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.CANDIDATE_REJECTED.value

    def test_requested_actions_non_empty(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
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
        transport = fb.collect(plan, transport)
        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.CANDIDATE_REJECTED.value

    def test_validate_uses_frozen_canonical_artifact(self, tmp_path):
        """strict_validate reads canonical artifact, not original file."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        transport = fb.collect(plan, transport)

        # Mutate original candidate
        (sandbox / "candidate.json").write_text('{"mutated": true}')

        # strict_validate should still pass using canonical artifact
        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.SUCCEEDED.value

    def test_canonical_digest_mismatch(self, tmp_path):
        """If canonical artifact is tampered, strict_validate returns ambiguous."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        transport = fb.collect(plan, transport)

        # Tamper canonical artifact
        canonical = sandbox / "output" / "collected_candidate.json"
        canonical.write_text('{"tampered": true}')

        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.AMBIGUOUS.value

    def test_error_no_absolute_paths(self, tmp_path):
        """error_detail must not contain absolute paths."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path, context_ref="sha256:wrong")
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        transport = fb.collect(plan, transport)
        result = fb.strict_validate(req, transport)
        assert str(tmp_path) not in (result.error_detail or "")


class TestFileBackendSandboxEscape:
    def test_traversal_ref_rejected(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path, sandbox_path_ref="../escape")
        with pytest.raises(ContractInvalid):
            fb.prepare(req)

    def test_resolved_escape_rejected(self, tmp_path):
        """Sandbox resolving outside runtime_root must be rejected."""
        fb = FileBackend(tmp_path)
        # Use a ref that resolves outside tmp_path
        outside = tmp_path.parent / "outside_sandbox"
        outside.mkdir(exist_ok=True)
        try:
            # Build request pointing outside runtime root
            req = BackendInvocationRequest(
                run_binding_id="rb-1", invocation_id="inv-1",
                backend_session_ref="rb-1:inv-1", backend_profile_ref="sha256:bp",
                context_ref="sha256:ctx", context_digest="sha256:cd",
                instruction_text="test", instruction_profile_ref="profile:1",
                config_ref="config:1", sandbox_policy_ref="sandbox:1",
                request_digest="sha256:" + "0" * 64,
                model_ref=None, timeout_seconds=60,
                max_stdout_bytes=10_000_000, max_stderr_bytes=1_000_000,
                fresh_session=True, sandbox_path_ref=str(outside),
            )
            # Fix digest
            from furina_code.backend.port import compute_backend_request_digest
            req = BackendInvocationRequest(
                **{**req.__dict__, "request_digest": compute_backend_request_digest(req)}
            )
            with pytest.raises(ContractInvalid, match="escapes runtime root"):
                fb.prepare(req)
        finally:
            outside.rmdir()
