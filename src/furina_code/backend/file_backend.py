"""Furina Code backend — FileBackend shadow adapter.

Implements the BackendPort protocol for file-based candidate exchange.
Does NOT create CandidateEnvelope, write Ledger, or transition TaskRun.
Does NOT import ledger, formal objects factories, or orchestration modules.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..contracts.errors import ContractInvalid
from ..contracts.meta import canonical_json_dumps
from .candidate import read_candidate_once, validate_candidate_content, MAX_CANDIDATE_BYTES
from .port import (
    BackendInvocationPlan,
    BackendInvocationRequest,
    BackendProbeRequest,
    BackendProbeResult,
    BackendTransportResult,
    TransportStatus,
    compute_backend_request_digest,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class FileBackend:
    """Shadow adapter implementing BackendPort for file-based candidate exchange.

    No external executable dependency. No process launch. No Ledger access.
    """

    def probe(self, request: BackendProbeRequest) -> BackendProbeResult:
        """Probe file backend availability.

        Checks that the sandbox reference can be resolved and candidate path state.
        """
        errors: list[str] = []
        # FileBackend has no external executable
        # Availability depends on whether sandbox/candidate path is usable
        return BackendProbeResult(
            available=True,
            version="file-backend-1.0",
            executable_ref=request.executable_ref,
            supported_flags=(),
            model_ids=(),
            errors=tuple(errors),
        )

    def prepare(self, request: BackendInvocationRequest) -> BackendInvocationPlan:
        """Create invocation plan. No process args needed for file backend."""
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
        """Check if candidate file exists. No process launch."""
        request = plan.request
        candidate_path = Path(request.sandbox_path_ref) / "candidate.json"

        if not candidate_path.exists():
            return BackendTransportResult(
                invocation_id=request.invocation_id,
                request_digest=request.request_digest,
                backend_session_ref=request.backend_session_ref,
                provider_session_ref=None,
                provider_ref="file-backend",
                executable_version="file-backend-1.0",
                started_at=_now_iso(),
                finished_at=_now_iso(),
                command_args_digest="sha256:" + "0" * 64,
                stdout_ref=None, stdout_digest=None, stdout_bytes=0, stdout_truncated=False,
                stderr_ref=None, stderr_digest=None, stderr_bytes=0, stderr_truncated=False,
                candidate_ref=None, candidate_digest=None,
                manifest_before_ref=None, manifest_before_digest=None,
                manifest_after_ref=None, manifest_after_digest=None,
                transport_status=TransportStatus.AWAITING_EXTERNAL.value,
                error_code=None, error_detail=None,
            )

        # Candidate exists — read it (reuse existing safe reader)
        try:
            candidate_path_resolved = candidate_path.resolve()
            if candidate_path_resolved.is_symlink():
                return self._error_result(
                    request, TransportStatus.SANDBOX_VIOLATION,
                    "SYMLINK_REJECTED", f"Candidate file is a symlink: {candidate_path}",
                )
            text, parsed, digest = read_candidate_once(str(candidate_path))
        except ContractInvalid as exc:
            status = _map_candidate_error(exc)
            return self._error_result(request, status, exc.code, exc.message)
        except UnicodeDecodeError as exc:
            return self._error_result(
                request, TransportStatus.INVALID_UTF8,
                "INVALID_UTF8", f"UTF-8 decode failed: {exc}",
            )

        return BackendTransportResult(
            invocation_id=request.invocation_id,
            request_digest=request.request_digest,
            backend_session_ref=request.backend_session_ref,
            provider_session_ref=None,
            provider_ref="file-backend",
            executable_version="file-backend-1.0",
            started_at=_now_iso(),
            finished_at=_now_iso(),
            command_args_digest="sha256:" + "0" * 64,
            stdout_ref="candidate.json",
            stdout_digest="sha256:" + digest,
            stdout_bytes=len(text.encode("utf-8")),
            stdout_truncated=False,
            stderr_ref=None, stderr_digest=None, stderr_bytes=0, stderr_truncated=False,
            candidate_ref="candidate.json",
            candidate_digest="sha256:" + digest,
            manifest_before_ref=None, manifest_before_digest=None,
            manifest_after_ref=None, manifest_after_digest=None,
            transport_status=TransportStatus.SUCCEEDED.value,
            error_code=None, error_detail=None,
        )

    def collect(
        self,
        plan: BackendInvocationPlan,
        transport: BackendTransportResult,
    ) -> BackendTransportResult:
        """Collect is a no-op for FileBackend — invoke already read the candidate."""
        return transport

    def strict_validate(
        self,
        request: BackendInvocationRequest,
        transport: BackendTransportResult,
    ) -> BackendTransportResult:
        """Validate candidate content against request bindings."""
        if transport.transport_status != TransportStatus.SUCCEEDED.value:
            return transport

        candidate_path = Path(request.sandbox_path_ref) / "candidate.json"
        try:
            text, _, _ = read_candidate_once(str(candidate_path))
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
                stdout_ref=transport.stdout_ref,
                stdout_digest=transport.stdout_digest,
                stdout_bytes=transport.stdout_bytes,
                stdout_truncated=transport.stdout_truncated,
                stderr_ref=transport.stderr_ref,
                stderr_digest=transport.stderr_digest,
                stderr_bytes=transport.stderr_bytes,
                stderr_truncated=transport.stderr_truncated,
                candidate_ref=transport.candidate_ref,
                candidate_digest=transport.candidate_digest,
                manifest_before_ref=transport.manifest_before_ref,
                manifest_before_digest=transport.manifest_before_digest,
                manifest_after_ref=transport.manifest_after_ref,
                manifest_after_digest=transport.manifest_after_digest,
                transport_status=status.value,
                error_code=exc.code,
                error_detail=exc.message,
            )

        return transport

    def _error_result(
        self,
        request: BackendInvocationRequest,
        status: TransportStatus,
        error_code: str,
        error_detail: str,
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
            command_args_digest="sha256:" + "0" * 64,
            stdout_ref=None, stdout_digest=None, stdout_bytes=0, stdout_truncated=False,
            stderr_ref=None, stderr_digest=None, stderr_bytes=0, stderr_truncated=False,
            candidate_ref=None, candidate_digest=None,
            manifest_before_ref=None, manifest_before_digest=None,
            manifest_after_ref=None, manifest_after_digest=None,
            transport_status=status.value,
            error_code=error_code,
            error_detail=error_detail,
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
