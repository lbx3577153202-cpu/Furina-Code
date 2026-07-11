"""Furina Code backend — BackendPort protocol, DTOs, and transport status."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from ..contracts.meta import canonical_json_dumps, compute_integrity_ref


# --- Transport Status (14 values, no more) ---

class TransportStatus(str, Enum):
    SUCCEEDED = "succeeded"
    AWAITING_EXTERNAL = "awaiting_external"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    LAUNCH_FAILED = "launch_failed"
    AUTHENTICATION_FAILED = "authentication_failed"
    NONZERO_EXIT = "nonzero_exit"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    OUTPUT_TOO_LARGE = "output_too_large"
    INVALID_UTF8 = "invalid_utf8"
    PROTOCOL_ERROR = "protocol_error"
    CANDIDATE_REJECTED = "candidate_rejected"
    SANDBOX_VIOLATION = "sandbox_violation"
    AMBIGUOUS = "ambiguous"


# --- DTOs (non-authoritative, frozen) ---

@dataclass(frozen=True)
class BackendProbeRequest:
    executable_ref: str  # logical name, config ref — never absolute path
    probe_timeout_seconds: int


@dataclass(frozen=True)
class BackendProbeResult:
    available: bool
    version: str | None
    executable_ref: str  # logical name, config ref — never absolute path
    supported_flags: tuple[str, ...]
    model_ids: tuple[str, ...]
    errors: tuple[str, ...]  # sanitized, no user paths


@dataclass(frozen=True)
class BackendInvocationRequest:
    run_binding_id: str
    invocation_id: str
    backend_session_ref: str
    backend_profile_ref: str
    context_ref: str
    context_digest: str
    instruction_text: str
    instruction_profile_ref: str
    config_ref: str
    sandbox_policy_ref: str
    request_digest: str
    model_ref: str | None
    timeout_seconds: int
    max_stdout_bytes: int
    max_stderr_bytes: int
    fresh_session: bool
    sandbox_path_ref: str  # relative or logical ref, not absolute


@dataclass(frozen=True)
class BackendInvocationPlan:
    request: BackendInvocationRequest
    executable_args: tuple[str, ...]
    cwd_ref: str  # relative or logical ref, not absolute
    env_policy_ref: str  # reference to environment policy, not actual values
    env_key_allowlist: tuple[str, ...]  # key names only, no values
    credential_mode: str
    provider_state_policy_ref: str


@dataclass(frozen=True)
class BackendTransportResult:
    invocation_id: str
    request_digest: str
    backend_session_ref: str
    provider_session_ref: str | None
    provider_ref: str
    executable_version: str
    started_at: str  # ISO 8601
    finished_at: str  # ISO 8601
    command_args_digest: str

    stdout_ref: str | None  # relative ref
    stdout_digest: str | None
    stdout_bytes: int
    stdout_truncated: bool

    stderr_ref: str | None  # relative ref
    stderr_digest: str | None
    stderr_bytes: int
    stderr_truncated: bool

    candidate_ref: str | None  # relative ref
    candidate_digest: str | None

    manifest_before_ref: str | None  # relative ref
    manifest_before_digest: str | None
    manifest_after_ref: str | None  # relative ref
    manifest_after_digest: str | None

    transport_status: str  # TransportStatus value
    error_code: str | None
    error_detail: str | None


# --- Request Digest ---

# Fields included in the request digest (no credentials, no env values, no absolute paths)
_DIGEST_FIELDS = (
    "backend_profile_ref",
    "context_ref",
    "context_digest",
    "instruction_profile_ref",
    "config_ref",
    "sandbox_policy_ref",
    "model_ref",
    "timeout_seconds",
    "max_stdout_bytes",
    "max_stderr_bytes",
    "fresh_session",
)


def compute_backend_request_digest(request: BackendInvocationRequest) -> str:
    """Compute SHA-256 digest of request fields. No credential or env values included."""
    digest_payload = {}
    for field in _DIGEST_FIELDS:
        digest_payload[field] = getattr(request, field)
    raw = canonical_json_dumps(digest_payload).encode("utf-8")
    import hashlib
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def verify_backend_request_digest(request: BackendInvocationRequest) -> None:
    """Verify that request.request_digest matches recomputed digest. Fail-closed."""
    from ..contracts.errors import ContractInvalid
    expected = compute_backend_request_digest(request)
    if request.request_digest != expected:
        raise ContractInvalid(
            "Request digest mismatch",
            {"expected": expected, "got": request.request_digest},
        )


# --- BackendPort Protocol ---

@runtime_checkable
class BackendPort(Protocol):
    """Protocol for backend adapters. Adapters do NOT own Ledger, TaskRun, or formal objects."""

    def probe(self, request: BackendProbeRequest) -> BackendProbeResult: ...

    def prepare(self, request: BackendInvocationRequest) -> BackendInvocationPlan: ...

    def invoke(self, plan: BackendInvocationPlan) -> BackendTransportResult: ...

    def collect(
        self,
        plan: BackendInvocationPlan,
        transport: BackendTransportResult,
    ) -> BackendTransportResult: ...

    def strict_validate(
        self,
        request: BackendInvocationRequest,
        transport: BackendTransportResult,
    ) -> BackendTransportResult: ...
