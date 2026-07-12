"""Furina Code backend — FileBackend shadow adapter.

Implements the BackendPort protocol for file-based candidate exchange.
Does NOT create CandidateEnvelope, write Ledger, or transition TaskRun.
Does NOT import ledger, formal objects factories, or orchestration modules.

Runtime root is injected via constructor (瞬时, non-serialized).
All DTOs use relative/logical refs only.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from ..contracts.errors import ContractInvalid
from ..contracts.meta import canonical_json_dumps
from .candidate import MAX_CANDIDATE_BYTES, read_candidate_once, validate_candidate_content
from .port import (
    BackendInvocationPlan,
    BackendInvocationRequest,
    BackendProbeRequest,
    BackendProbeResult,
    BackendTransportResult,
    TransportStatus,
    compute_backend_request_digest,
    compute_empty_args_digest,
    verify_backend_request_digest,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _resolve_sandbox_ref(runtime_root: Path, sandbox_path_ref: str) -> Path:
    """Resolve sandbox_path_ref against runtime_root. Rejects traversal and escapes."""
    if ".." in Path(sandbox_path_ref).parts:
        raise ContractInvalid("Sandbox ref contains traversal")

    resolved = (runtime_root / sandbox_path_ref).resolve()

    # Must stay within runtime_root
    try:
        resolved.relative_to(runtime_root.resolve())
    except ValueError:
        raise ContractInvalid("Sandbox escapes runtime root")

    # Check for symlink/junction escape at each parent level
    current = resolved
    while current != current.parent:
        if current.is_symlink():
            raise ContractInvalid(f"Path component is symlink: {current.name}")
        current = current.parent

    return resolved


# Stable error messages (no paths)
_ERROR_MESSAGES = {
    "candidate_missing": "Candidate file not found in sandbox.",
    "candidate_path_rejected": "Candidate path was rejected by sandbox policy.",
    "candidate_symlink_rejected": "Candidate file is a symlink.",
    "candidate_invalid_utf8": "Candidate content is not valid UTF-8.",
    "candidate_too_large": "Candidate exceeds size limit.",
    "candidate_protocol_error": "Candidate content is not valid JSON.",
    "candidate_binding_rejected": "Candidate context/profile binding rejected.",
    "candidate_evidence_mismatch": "Candidate evidence digest changed after collection.",
    "sandbox_escape": "Sandbox resolved outside allowed boundary.",
    "sandbox_ref_rejected": "Sandbox reference was rejected.",
    "invalid_request_digest": "Request digest verification failed.",
    "instruction_digest_mismatch": "Instruction text changed after digest computation.",
}


class FileBackend:
    """Shadow adapter implementing BackendPort for file-based candidate exchange.

    No external executable dependency. No process launch. No Ledger access.
    runtime_root is瞬时 and never serialized into DTOs.
    """

    def __init__(self, runtime_root: Path) -> None:
        self._runtime_root = runtime_root.resolve()

    def probe(self, request: BackendProbeRequest) -> BackendProbeResult:
        """Probe file backend availability."""
        errors: list[str] = []

        # Check runtime root
        if not self._runtime_root.exists():
            errors.append("runtime_root_invalid")
        elif not self._runtime_root.is_dir():
            errors.append("runtime_root_invalid")

        # Check sandbox ref is relative
        # (We can't fully validate without a request, but we check runtime root basics)

        return BackendProbeResult(
            available=len(errors) == 0,
            version="file-backend-1.0",
            executable_ref=request.executable_ref,
            supported_flags=(),
            model_ids=(),
            errors=tuple(errors),
        )

    def prepare(self, request: BackendInvocationRequest) -> BackendInvocationPlan:
        """Verify request digest, validate sandbox ref, generate plan."""
        # Verify request digest first (fail-closed)
        verify_backend_request_digest(request)

        # Validate sandbox ref resolution
        try:
            _resolve_sandbox_ref(self._runtime_root, request.sandbox_path_ref)
        except ContractInvalid:
            raise

        return BackendInvocationPlan(
            request=request,
            executable_args=(),
            cwd_ref=request.sandbox_path_ref,
            env_policy_ref="file-backend:no-env",
            env_key_allowlist=(),
            credential_mode="none",
            provider_state_policy_ref="file-backend:no-provider-state",
        )

    def invoke(self, plan: BackendInvocationPlan) -> BackendTransportResult:
        """Check if candidate file exists. Does NOT read content."""
        request = plan.request
        sandbox = _resolve_sandbox_ref(self._runtime_root, request.sandbox_path_ref)
        candidate_path = sandbox / "candidate.json"

        # Check existence and basic safety — no content read
        if not candidate_path.exists():
            return self._make_result(
                request, TransportStatus.AWAITING_EXTERNAL,
            )

        # Reject symlinks at existence check
        if candidate_path.is_symlink():
            return self._error_result(
                request, TransportStatus.SANDBOX_VIOLATION,
                "candidate_symlink_rejected",
            )

        return self._make_result(request, TransportStatus.SUCCEEDED)

    def collect(
        self,
        plan: BackendInvocationPlan,
        transport: BackendTransportResult,
    ) -> BackendTransportResult:
        """Read external candidate once and form canonical collected artifact."""
        if transport.transport_status != TransportStatus.SUCCEEDED.value:
            return transport

        request = plan.request
        sandbox = _resolve_sandbox_ref(self._runtime_root, request.sandbox_path_ref)
        external_candidate = sandbox / "candidate.json"
        output_dir = sandbox / "output"
        output_dir.mkdir(exist_ok=True)
        canonical_candidate = output_dir / "collected_candidate.json"

        # Check effective size limit
        effective_limit = min(request.max_stdout_bytes, MAX_CANDIDATE_BYTES)
        if effective_limit <= 0:
            return self._error_result(
                request, TransportStatus.OUTPUT_TOO_LARGE,
                "candidate_too_large",
            )

        # Single read of external candidate
        try:
            raw_bytes = external_candidate.read_bytes()
        except OSError:
            return self._error_result(
                request, TransportStatus.CANDIDATE_REJECTED,
                "candidate_missing",
            )

        # Size check
        if len(raw_bytes) > effective_limit:
            return self._error_result(
                request, TransportStatus.OUTPUT_TOO_LARGE,
                "candidate_too_large",
            )

        # UTF-8 decode (strict)
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return self._error_result(
                request, TransportStatus.INVALID_UTF8,
                "candidate_invalid_utf8",
            )

        # JSON parse
        import json
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return self._error_result(
                request, TransportStatus.PROTOCOL_ERROR,
                "candidate_protocol_error",
            )

        if not isinstance(parsed, dict):
            return self._error_result(
                request, TransportStatus.PROTOCOL_ERROR,
                "candidate_protocol_error",
            )

        # Compute digest from the exact bytes we read
        candidate_digest = _sha256_bytes(raw_bytes)

        # Write canonical collected artifact (atomic-ish: exclusive create)
        if canonical_candidate.exists():
            # If artifact already exists from a different invocation, this is a problem
            existing_bytes = canonical_candidate.read_bytes()
            if _sha256_bytes(existing_bytes) != candidate_digest:
                return self._error_result(
                    request, TransportStatus.AMBIGUOUS,
                    "candidate_evidence_mismatch",
                )
        else:
            canonical_candidate.write_bytes(raw_bytes)

        # Verify canonical artifact matches what we just wrote
        canonical_bytes = canonical_candidate.read_bytes()
        canonical_digest = _sha256_bytes(canonical_bytes)
        if canonical_digest != candidate_digest:
            return self._error_result(
                request, TransportStatus.AMBIGUOUS,
                "candidate_evidence_mismatch",
            )

        return BackendTransportResult(
            invocation_id=transport.invocation_id,
            request_digest=transport.request_digest,
            backend_session_ref=transport.backend_session_ref,
            provider_session_ref=None,
            provider_ref="file-backend",
            executable_version="file-backend-1.0",
            started_at=transport.started_at,
            finished_at=_now_iso(),
            command_args_digest=compute_empty_args_digest(),
            stdout_ref=None, stdout_digest=None, stdout_bytes=0, stdout_truncated=False,
            stderr_ref=None, stderr_digest=None, stderr_bytes=0, stderr_truncated=False,
            candidate_ref="output/collected_candidate.json",
            candidate_digest=candidate_digest,
            manifest_before_ref=None, manifest_before_digest=None,
            manifest_after_ref=None, manifest_after_digest=None,
            transport_status=TransportStatus.SUCCEEDED.value,
            error_code=None, error_detail=None,
        )

    def strict_validate(
        self,
        request: BackendInvocationRequest,
        transport: BackendTransportResult,
    ) -> BackendTransportResult:
        """Validate canonical collected artifact against request bindings."""
        if transport.transport_status != TransportStatus.SUCCEEDED.value:
            return transport

        sandbox = _resolve_sandbox_ref(self._runtime_root, request.sandbox_path_ref)
        canonical_candidate = sandbox / "output" / "collected_candidate.json"

        if not canonical_candidate.exists():
            return self._error_result(
                request, TransportStatus.AMBIGUOUS,
                "candidate_evidence_mismatch",
            )

        # Read canonical artifact (the frozen evidence)
        try:
            raw_bytes = canonical_candidate.read_bytes()
        except OSError:
            return self._error_result(
                request, TransportStatus.AMBIGUOUS,
                "candidate_evidence_mismatch",
            )

        # Verify digest matches transport
        canonical_digest = _sha256_bytes(raw_bytes)
        if canonical_digest != transport.candidate_digest:
            return self._error_result(
                request, TransportStatus.AMBIGUOUS,
                "candidate_evidence_mismatch",
            )

        # Strict UTF-8 decode
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return self._error_result(
                request, TransportStatus.INVALID_UTF8,
                "candidate_invalid_utf8",
            )

        # Validate content against request bindings
        try:
            validate_candidate_content(
                text,
                expected_context_ref=request.context_ref,
                expected_context_digest=request.context_digest,
                expected_backend_profile_ref=request.backend_profile_ref,
            )
        except ContractInvalid as exc:
            status = _map_candidate_error(exc)
            return BackendTransportResult(
                invocation_id=transport.invocation_id,
                request_digest=transport.request_digest,
                backend_session_ref=transport.backend_session_ref,
                provider_session_ref=transport.provider_session_ref,
                provider_ref=transport.provider_ref,
                executable_version=transport.executable_version,
                started_at=transport.started_at,
                finished_at=_now_iso(),
                command_args_digest=transport.command_args_digest,
                stdout_ref=None, stdout_digest=None, stdout_bytes=0, stdout_truncated=False,
                stderr_ref=None, stderr_digest=None, stderr_bytes=0, stderr_truncated=False,
                candidate_ref=transport.candidate_ref,
                candidate_digest=transport.candidate_digest,
                manifest_before_ref=None, manifest_before_digest=None,
                manifest_after_ref=None, manifest_after_digest=None,
                transport_status=status.value,
                error_code=_map_error_code(exc),
                error_detail=_ERROR_MESSAGES.get(_map_error_code(exc), "Validation failed."),
            )

        return transport

    def _make_result(
        self,
        request: BackendInvocationRequest,
        status: TransportStatus,
    ) -> BackendTransportResult:
        return BackendTransportResult(
            invocation_id=request.invocation_id,
            request_digest=request.request_digest,
            backend_session_ref=request.backend_session_ref,
            provider_session_ref=None,
            provider_ref="file-backend",
            executable_version="file-backend-1.0",
            started_at=_now_iso(),
            finished_at=_now_iso(),
            command_args_digest=compute_empty_args_digest(),
            stdout_ref=None, stdout_digest=None, stdout_bytes=0, stdout_truncated=False,
            stderr_ref=None, stderr_digest=None, stderr_bytes=0, stderr_truncated=False,
            candidate_ref=None, candidate_digest=None,
            manifest_before_ref=None, manifest_before_digest=None,
            manifest_after_ref=None, manifest_after_digest=None,
            transport_status=status.value,
            error_code=None, error_detail=None,
        )

    def _error_result(
        self,
        request: BackendInvocationRequest,
        status: TransportStatus,
        error_code: str,
    ) -> BackendTransportResult:
        return BackendTransportResult(
            invocation_id=request.invocation_id,
            request_digest=request.request_digest,
            backend_session_ref=request.backend_session_ref,
            provider_session_ref=None,
            provider_ref="file-backend",
            executable_version="file-backend-1.0",
            started_at=_now_iso(),
            finished_at=_now_iso(),
            command_args_digest=compute_empty_args_digest(),
            stdout_ref=None, stdout_digest=None, stdout_bytes=0, stdout_truncated=False,
            stderr_ref=None, stderr_digest=None, stderr_bytes=0, stderr_truncated=False,
            candidate_ref=None, candidate_digest=None,
            manifest_before_ref=None, manifest_before_digest=None,
            manifest_after_ref=None, manifest_after_digest=None,
            transport_status=status.value,
            error_code=error_code,
            error_detail=_ERROR_MESSAGES.get(error_code, "Unknown error."),
        )


def _map_candidate_error(exc: ContractInvalid) -> TransportStatus:
    """Map candidate validation errors to transport status."""
    msg = exc.message.lower()
    if "not valid json" in msg or "json object" in msg or "missing required field" in msg or "wrong type" in msg:
        return TransportStatus.PROTOCOL_ERROR
    if "context_ref" in msg or "context_digest" in msg or "backend_profile_ref" in msg or "requested_actions" in msg:
        return TransportStatus.CANDIDATE_REJECTED
    if "not valid utf-8" in msg or "utf-8" in msg:
        return TransportStatus.INVALID_UTF8
    if "too large" in msg or "size" in msg:
        return TransportStatus.OUTPUT_TOO_LARGE
    if "symlink" in msg or "traversal" in msg or "escape" in msg:
        return TransportStatus.SANDBOX_VIOLATION
    return TransportStatus.PROTOCOL_ERROR


def _map_error_code(exc: ContractInvalid) -> str:
    """Map ContractInvalid to stable error code."""
    msg = exc.message.lower()
    if "not valid json" in msg or "json object" in msg:
        return "candidate_protocol_error"
    if "missing required field" in msg or "wrong type" in msg:
        return "candidate_protocol_error"
    if "context_ref" in msg:
        return "candidate_binding_rejected"
    if "context_digest" in msg:
        return "candidate_binding_rejected"
    if "backend_profile_ref" in msg:
        return "candidate_binding_rejected"
    if "requested_actions" in msg:
        return "candidate_binding_rejected"
    if "not valid utf-8" in msg:
        return "candidate_invalid_utf8"
    if "too large" in msg:
        return "candidate_too_large"
    if "symlink" in msg:
        return "candidate_symlink_rejected"
    if "traversal" in msg or "escape" in msg:
        return "sandbox_escape"
    if "empty" in msg:
        return "candidate_missing"
    return "candidate_protocol_error"
