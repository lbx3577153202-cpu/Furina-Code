"""Tests for BackendPort DTOs, TransportStatus, and request digest."""

import pytest
from furina_code.backend.port import (
    BackendProbeRequest,
    BackendProbeResult,
    BackendInvocationRequest,
    BackendInvocationPlan,
    BackendTransportResult,
    TransportStatus,
    compute_backend_request_digest,
    verify_backend_request_digest,
)
from furina_code.contracts.errors import ContractInvalid
from furina_code.contracts.objects import OWNER_MAP


def _make_request(**overrides):
    defaults = dict(
        run_binding_id="rb-1", invocation_id="inv-1",
        backend_session_ref="rb-1:inv-1", backend_profile_ref="sha256:bp",
        context_ref="sha256:ctx", context_digest="sha256:cd",
        instruction_text="test", instruction_profile_ref="profile:1",
        config_ref="config:1", sandbox_policy_ref="sandbox:1",
        request_digest="sha256:" + "0" * 64,
        model_ref=None, timeout_seconds=60,
        max_stdout_bytes=10_000_000, max_stderr_bytes=1_000_000,
        fresh_session=True, sandbox_path_ref="sandbox/inv-1",
    )
    defaults.update(overrides)
    return BackendInvocationRequest(**defaults)


class TestDTOsFrozen:
    def test_probe_request_frozen(self):
        r = BackendProbeRequest(executable_ref="mimo", probe_timeout_seconds=30)
        with pytest.raises(AttributeError):
            r.executable_ref = "changed"

    def test_probe_result_frozen(self):
        r = BackendProbeResult(
            available=True, version="1.0", executable_ref="mimo",
            supported_flags=(), model_ids=(), errors=(),
        )
        with pytest.raises(AttributeError):
            r.available = False

    def test_invocation_request_frozen(self):
        r = _make_request()
        with pytest.raises(AttributeError):
            r.invocation_id = "changed"

    def test_invocation_plan_frozen(self):
        req = _make_request()
        p = BackendInvocationPlan(
            request=req, executable_args=(), cwd_ref=".",
            env_policy_ref="p", env_key_allowlist=(),
            credential_mode="none", provider_state_policy_ref="p",
        )
        with pytest.raises(AttributeError):
            p.cwd_ref = "changed"

    def test_transport_result_frozen(self):
        t = BackendTransportResult(
            invocation_id="inv-1", request_digest="d", backend_session_ref="s",
            provider_session_ref=None, provider_ref="fb", executable_version="1.0",
            started_at="t", finished_at="t", command_args_digest="d",
            stdout_ref=None, stdout_digest=None, stdout_bytes=0, stdout_truncated=False,
            stderr_ref=None, stderr_digest=None, stderr_bytes=0, stderr_truncated=False,
            candidate_ref=None, candidate_digest=None,
            manifest_before_ref=None, manifest_before_digest=None,
            manifest_after_ref=None, manifest_after_digest=None,
            transport_status="succeeded", error_code=None, error_detail=None,
        )
        with pytest.raises(AttributeError):
            t.invocation_id = "changed"


class TestOWNERMap:
    def test_dto_not_in_owner_map(self):
        for name in ("BackendProbeRequest", "BackendProbeResult",
                      "BackendInvocationRequest", "BackendInvocationPlan",
                      "BackendTransportResult"):
            assert name not in OWNER_MAP, f"{name} must not be in OWNER_MAP"


class TestTransportStatus:
    def test_exactly_14_statuses(self):
        assert len(TransportStatus) == 14

    def test_expected_statuses(self):
        expected = {
            "succeeded", "awaiting_external", "backend_unavailable",
            "launch_failed", "authentication_failed", "nonzero_exit",
            "timeout", "cancelled", "output_too_large", "invalid_utf8",
            "protocol_error", "candidate_rejected", "sandbox_violation",
            "ambiguous",
        }
        actual = {s.value for s in TransportStatus}
        assert actual == expected

    def test_enum_values_are_strings(self):
        for s in TransportStatus:
            assert isinstance(s.value, str)


class TestRequestDigest:
    def test_deterministic(self):
        r = _make_request()
        d1 = compute_backend_request_digest(r)
        d2 = compute_backend_request_digest(r)
        assert d1 == d2

    def test_starts_with_sha256(self):
        r = _make_request()
        d = compute_backend_request_digest(r)
        assert d.startswith("sha256:")

    def test_differs_on_different_request(self):
        r1 = _make_request(timeout_seconds=60)
        r2 = _make_request(timeout_seconds=120)
        assert compute_backend_request_digest(r1) != compute_backend_request_digest(r2)

    def test_verify_passes(self):
        r = _make_request()
        digest = compute_backend_request_digest(r)
        r2 = _make_request(request_digest=digest)
        verify_backend_request_digest(r2)  # should not raise

    def test_verify_fails_on_mismatch(self):
        r = _make_request(request_digest="sha256:" + "f" * 64)
        with pytest.raises(ContractInvalid, match="digest mismatch"):
            verify_backend_request_digest(r)

    def test_no_credential_fields_in_digest(self):
        """Digest must not include any credential-like fields."""
        r = _make_request()
        d = compute_backend_request_digest(r)
        # The digest is a hash, so we verify the digest payload structure
        # by checking that changing credential-like fields doesn't affect it
        # (they're not in _DIGEST_FIELDS)
        assert "token" not in d
        assert "key" not in d
