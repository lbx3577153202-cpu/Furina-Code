"""Tests for FileBackend shadow adapter."""

import json
import os
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

    def test_probe_symlink_root(self, tmp_path):
        """Runtime root that is a symlink must be unavailable."""
        real_root = tmp_path / "real"
        real_root.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real_root)
        fb = FileBackend(link)
        result = fb.probe(BackendProbeRequest(executable_ref="file-backend", probe_timeout_seconds=30))
        assert result.available is False
        assert "runtime_root_link_rejected" in result.errors

    def test_probe_forbidden_root_inside(self, tmp_path):
        forbidden = tmp_path / "forbidden"
        forbidden.mkdir()
        inside = forbidden / "inside"
        inside.mkdir()
        fb = FileBackend(inside, forbidden_roots=(forbidden,))
        result = fb.probe(BackendProbeRequest(executable_ref="file-backend", probe_timeout_seconds=30))
        assert result.available is False
        assert "runtime_root_forbidden" in result.errors

    def test_probe_forbidden_root_equal(self, tmp_path):
        """Runtime root equal to forbidden root must be rejected."""
        fb = FileBackend(tmp_path, forbidden_roots=(tmp_path,))
        result = fb.probe(BackendProbeRequest(executable_ref="file-backend", probe_timeout_seconds=30))
        assert result.available is False
        assert "runtime_root_forbidden" in result.errors

    def test_probe_forbidden_inside_runtime(self, tmp_path):
        """Forbidden root inside runtime_root must be rejected."""
        fb = FileBackend(tmp_path, forbidden_roots=(tmp_path / "child",))
        result = fb.probe(BackendProbeRequest(executable_ref="file-backend", probe_timeout_seconds=30))
        assert result.available is False
        assert "runtime_root_forbidden" in result.errors

    def test_probe_no_absolute_path_in_errors(self, tmp_path):
        fb = FileBackend(tmp_path / "nonexistent")
        result = fb.probe(BackendProbeRequest(executable_ref="file-backend", probe_timeout_seconds=30))
        for err in result.errors:
            assert str(tmp_path) not in err


class TestFileBackendLifecycleRechecks:
    def test_prepare_rechecks_boundary(self, tmp_path):
        """prepare must re-verify runtime boundary even without probe."""
        forbidden = tmp_path / "forbidden"
        forbidden.mkdir()
        inside = forbidden / "inside"
        inside.mkdir()
        fb = FileBackend(inside, forbidden_roots=(forbidden,))
        req = _make_request(inside)
        with pytest.raises(ContractInvalid, match="runtime_root_forbidden"):
            fb.prepare(req)


class TestFileBackendSandboxRef:
    def test_absolute_ref_rejected(self, tmp_path):
        fb = FileBackend(tmp_path)
        # Use forward-slash absolute to hit the absolute check (not backslash)
        req = _make_request(tmp_path, sandbox_path_ref="/tmp/sandbox")
        with pytest.raises(ContractInvalid, match="relative"):
            fb.prepare(req)

    def test_windows_backslash_rejected(self, tmp_path):
        """Backslash in ref must be rejected."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path, sandbox_path_ref="foo\\bar")
        with pytest.raises(ContractInvalid, match="forward slashes"):
            fb.prepare(req)

    def test_windows_drive_ref_rejected(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path, sandbox_path_ref="C:/sandbox")
        with pytest.raises(ContractInvalid, match="relative"):
            fb.prepare(req)

    def test_unc_ref_rejected(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path, sandbox_path_ref="//server/share")
        with pytest.raises(ContractInvalid, match="relative"):
            fb.prepare(req)

    def test_traversal_ref_rejected(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path, sandbox_path_ref="../escape")
        with pytest.raises(ContractInvalid, match="traversal"):
            fb.prepare(req)

    def test_empty_ref_rejected(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path, sandbox_path_ref="")
        with pytest.raises(ContractInvalid):
            fb.prepare(req)

    def test_dot_ref_rejected(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path, sandbox_path_ref=".")
        with pytest.raises(ContractInvalid, match="must not be"):
            fb.prepare(req)


class TestFileBackendPrepare:
    def test_prepare_verifies_digest(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        plan = fb.prepare(req)
        assert plan.request is req

    def test_prepare_fails_on_invalid_digest(self, tmp_path):
        fb = FileBackend(tmp_path)
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

    def test_dangling_symlink_rejected(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        link = sandbox / "candidate.json"
        link.symlink_to(sandbox / "nonexistent.json")
        plan = fb.prepare(req)
        result = fb.invoke(plan)
        assert result.transport_status == TransportStatus.SANDBOX_VIOLATION.value

    def test_non_regular_file_rejected(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        (sandbox / "candidate.json").mkdir()
        plan = fb.prepare(req)
        result = fb.invoke(plan)
        assert result.transport_status == TransportStatus.SANDBOX_VIOLATION.value


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

    def test_candidate_ref_relative_to_sandbox(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)
        result = fb.collect(plan, invoke_result)
        assert "sandbox" in result.candidate_ref
        assert result.candidate_ref.endswith("output/collected_candidate.json")

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

    def test_regular_content_change_captured(self, tmp_path):
        """Regular file content change before collect is captured by collect."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)

        # Change content (still valid JSON)
        (sandbox / "candidate.json").write_text(json.dumps({
            "schema_version": "1.0", "candidate_type": "repository_baseline_report",
            "backend_profile_ref": "sha256:bp", "backend_session_ref": "test",
            "context_ref": "sha256:ctx", "context_digest": "sha256:cd",
            "content": {"repository_head": "b" * 40, "branch": "main", "working_tree": "clean",
                        "tracked_file_count": 0, "untracked_file_count": 0, "python_requires": None,
                        "runtime_dependencies": [], "dev_dependencies": [], "pytest_testpaths": [],
                        "ci_config": {"present": False, "sha256": None}, "blind_spots": []},
            "claimed_assumptions": [], "requested_actions": [],
        }))

        result = fb.collect(plan, invoke_result)
        assert result.transport_status == TransportStatus.SUCCEEDED.value

    def test_symlink_swap_before_collect_rejected(self, tmp_path):
        """Candidate swapped to symlink before collect → sandbox_violation."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)

        # Replace with symlink
        (sandbox / "candidate.json").unlink()
        real = sandbox / "real.json"
        real.write_text("{}")
        (sandbox / "candidate.json").symlink_to(real)

        result = fb.collect(plan, invoke_result)
        assert result.transport_status == TransportStatus.SANDBOX_VIOLATION.value

    def test_candidate_disappearance_ambiguous(self, tmp_path):
        """Candidate disappears between invoke and collect → ambiguous."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        (sandbox / "candidate.json").write_text("{}")
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)
        (sandbox / "candidate.json").unlink()

        result = fb.collect(plan, invoke_result)
        assert result.transport_status == TransportStatus.AMBIGUOUS.value
        assert result.error_code == "candidate_changed_before_collection"

    def test_exclusive_create_idempotent(self, tmp_path):
        """Same candidate collect twice is idempotent."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)
        result1 = fb.collect(plan, invoke_result)
        result2 = fb.collect(plan, invoke_result)
        assert result2.candidate_digest == result1.candidate_digest

    def test_existing_different_digest_ambiguous(self, tmp_path):
        """Existing canonical artifact with different digest → ambiguous."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)

        # First collect
        fb.collect(plan, invoke_result)

        # Create a different artifact manually
        output = sandbox / "output"
        canonical = output / "collected_candidate.json"
        canonical.write_text('{"different": true}')

        # Now collect with original candidate — different digest
        result = fb.collect(plan, invoke_result)
        assert result.transport_status == TransportStatus.AMBIGUOUS.value

    def test_collect_preserves_evidence_on_ambiguous(self, tmp_path):
        """Ambiguous result must preserve transport evidence."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)

        # Make candidate disappear
        (sandbox / "candidate.json").unlink()

        result = fb.collect(plan, invoke_result)
        assert result.transport_status == TransportStatus.AMBIGUOUS.value
        # Evidence preserved
        assert result.request_digest == invoke_result.request_digest
        assert result.backend_session_ref == invoke_result.backend_session_ref


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

    def test_tampered_canonical_returns_ambiguous(self, tmp_path):
        """Tampered canonical artifact → ambiguous with evidence preserved."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        transport = fb.collect(plan, transport)

        canonical = sandbox / "output" / "collected_candidate.json"
        canonical.write_bytes(b"\x80\x81\x82")

        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.AMBIGUOUS.value
        assert result.candidate_ref == transport.candidate_ref
        assert result.request_digest == transport.request_digest
        assert result.backend_session_ref == transport.backend_session_ref

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

        (sandbox / "candidate.json").write_text('{"mutated": true}')
        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.SUCCEEDED.value

    def test_candidate_ref_binding_verified(self, tmp_path):
        """strict_validate checks transport.candidate_ref matches expected."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        transport = fb.collect(plan, transport)

        # Tamper candidate_ref
        import dataclasses
        bad_transport = dataclasses.replace(transport, candidate_ref="wrong/ref")
        result = fb.strict_validate(req, bad_transport)
        assert result.transport_status == TransportStatus.AMBIGUOUS.value

    def test_missing_digest_ambiguous(self, tmp_path):
        """Empty candidate_digest → ambiguous."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        transport = fb.invoke(plan)
        transport = fb.collect(plan, transport)

        import dataclasses
        bad_transport = dataclasses.replace(transport, candidate_digest="")
        result = fb.strict_validate(req, bad_transport)
        assert result.transport_status == TransportStatus.AMBIGUOUS.value


class TestFileBackendAuthorityBoundary:
    def test_constructor_no_ledger(self):
        """FileBackend constructor must not accept Ledger."""
        import inspect
        sig = inspect.signature(FileBackend.__init__)
        params = list(sig.parameters.keys())
        assert "ledger" not in params

    def test_methods_no_ledger_parameter(self):
        """No FileBackend method must accept Ledger as parameter."""
        import inspect
        for method_name in ("probe", "prepare", "invoke", "collect", "strict_validate"):
            method = getattr(FileBackend, method_name)
            sig = inspect.signature(method)
            params = list(sig.parameters.keys())
            assert "ledger" not in params, f"{method_name} accepts ledger"

    def test_no_ledger_import_in_module(self):
        """file_backend.py must not import ledger module."""
        import ast
        import furina_code.backend.file_backend as fb_module
        tree = ast.parse(open(fb_module.__file__, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "ledger" not in alias.name.lower(), f"Imports ledger: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module and "ledger" in node.module.lower():
                    assert False, f"Imports from ledger: {node.module}"
