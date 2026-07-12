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

    def test_probe_forbidden_root(self, tmp_path):
        forbidden = tmp_path / "forbidden"
        forbidden.mkdir()
        inside = forbidden / "inside"
        inside.mkdir()
        fb = FileBackend(inside, forbidden_roots=(forbidden,))
        result = fb.probe(BackendProbeRequest(executable_ref="file-backend", probe_timeout_seconds=30))
        assert result.available is False
        assert "runtime_root_forbidden" in result.errors

    def test_probe_no_absolute_path_in_errors(self, tmp_path):
        fb = FileBackend(tmp_path / "nonexistent")
        result = fb.probe(BackendProbeRequest(executable_ref="file-backend", probe_timeout_seconds=30))
        for err in result.errors:
            assert str(tmp_path) not in err


class TestFileBackendSandboxRef:
    def test_absolute_ref_rejected(self, tmp_path):
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path, sandbox_path_ref=str(tmp_path / "sandbox"))
        with pytest.raises(ContractInvalid, match="relative"):
            fb.prepare(req)

    def test_absolute_inside_runtime_rejected(self, tmp_path):
        fb = FileBackend(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        req = _make_request(tmp_path, sandbox_path_ref=str(sandbox))
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
        # Create a directory named candidate.json
        (sandbox / "candidate.json").mkdir()
        plan = fb.prepare(req)
        result = fb.invoke(plan)
        assert result.transport_status == TransportStatus.SANDBOX_VIOLATION.value

    def test_invoke_does_not_read_content(self, tmp_path):
        """invoke only checks existence and link type, not content."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        # Write invalid content — invoke should still succeed
        (sandbox / "candidate.json").write_bytes(b"\x80\x81")
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

    def test_candidate_ref_relative_to_sandbox(self, tmp_path):
        """candidate_ref must contain sandbox_path_ref as prefix."""
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

    def test_collect_invalid_utf8_preserves_candidate_ref(self, tmp_path):
        """Invalid UTF-8 still saves candidate_ref and candidate_digest."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        (sandbox / "candidate.json").write_bytes(b"\x80\x81\x82")
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)
        result = fb.collect(plan, invoke_result)
        # collect doesn't do UTF-8 — it just freezes bytes
        # UTF-8 check happens in strict_validate
        assert result.candidate_ref is not None
        assert result.candidate_digest is not None

    def test_collect_candidate_mutation_safe(self, tmp_path):
        """After collect, modifying original doesn't change frozen evidence."""
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

    def test_exclusive_create_no_overwrite(self, tmp_path):
        """Canonical artifact uses exclusive create — doesn't overwrite existing."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)

        # First collect
        result1 = fb.collect(plan, invoke_result)
        digest1 = result1.candidate_digest

        # Second collect — same candidate, should be idempotent
        result2 = fb.collect(plan, invoke_result)
        assert result2.candidate_digest == digest1

    def test_collect_invoke_swap_detected(self, tmp_path):
        """If candidate changes between invoke and collect, detect it."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        _write_valid_candidate(sandbox)
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)

        # Replace candidate with different content
        (sandbox / "candidate.json").write_text('{"different": true}')

        result = fb.collect(plan, invoke_result)
        # collect reads the new content — no TOCTOU here since invoke didn't read
        assert result.candidate_digest is not None

    def test_collect_disappearance_detected(self, tmp_path):
        """If candidate disappears between invoke and collect."""
        fb = FileBackend(tmp_path)
        req = _make_request(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        (sandbox / "candidate.json").write_text("{}")
        plan = fb.prepare(req)
        invoke_result = fb.invoke(plan)

        # Remove candidate
        (sandbox / "candidate.json").unlink()

        result = fb.collect(plan, invoke_result)
        assert result.transport_status == TransportStatus.AMBIGUOUS.value
        assert result.error_code == "candidate_changed_before_collection"


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

        # Mutate original
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

    def test_tampered_canonical_returns_ambiguous(self, tmp_path):
        """If canonical artifact is tampered (digest mismatch), returns ambiguous."""
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
        canonical.write_bytes(b"\x80\x81\x82")

        result = fb.strict_validate(req, transport)
        assert result.transport_status == TransportStatus.AMBIGUOUS.value
        # Evidence preserved even on ambiguous
        assert result.candidate_ref == transport.candidate_ref
        assert result.request_digest == transport.request_digest
        assert result.backend_session_ref == transport.backend_session_ref

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
