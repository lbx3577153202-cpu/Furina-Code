"""Furina Code backend — FileBackend shadow adapter.

Implements the BackendPort protocol for file-based candidate exchange.
Does NOT create CandidateEnvelope, write Ledger, or transition TaskRun.
Does NOT import ledger, formal objects factories, or orchestration modules.

Runtime root is injected via constructor (瞬时, non-serialized).
All DTOs use relative/logical refs only.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from ..contracts.errors import ContractInvalid
from .port import (
    BackendInvocationPlan,
    BackendInvocationRequest,
    BackendProbeRequest,
    BackendProbeResult,
    BackendTransportResult,
    TransportStatus,
    compute_empty_args_digest,
    verify_backend_request_digest,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


# --- Path validation ---

def _validate_sandbox_ref(sandbox_path_ref: str) -> None:
    """Reject absolute, traversal, empty, or dot refs before any resolution."""
    if not sandbox_path_ref:
        raise ContractInvalid("Sandbox ref must not be empty")
    ref_path = Path(sandbox_path_ref)
    if ref_path.is_absolute():
        raise ContractInvalid("Sandbox ref must be relative")
    if ".." in ref_path.parts:
        raise ContractInvalid("Sandbox ref contains traversal")
    if ref_path == Path("."):
        raise ContractInvalid("Sandbox ref must not be '.'")


def _resolve_sandbox_ref(runtime_root: Path, sandbox_path_ref: str) -> Path:
    """Resolve sandbox_path_ref against runtime_root. Rejects traversal and escapes."""
    _validate_sandbox_ref(sandbox_path_ref)

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
            raise ContractInvalid("Sandbox path component is symlink")
        current = current.parent

    return resolved


# --- Safe file reading ---

def _read_regular_file_once_no_follow(path: Path, max_bytes: int) -> bytes:
    """Read a file using O_NOFOLLOW where possible, bounded read, identity check."""
    fd = -1
    try:
        # Use os.open with O_NOFOLLOW on Unix; on Windows O_NOFOLLOW is ignored
        # but we already check is_symlink() before calling this
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(path), flags)
        # fstat to verify identity after open
        stat = os.fstat(fd)
        # Verify it's a regular file (S_IFREG)
        import stat as stat_module
        if not stat_module.S_ISREG(stat.st_mode):
            raise ContractInvalid("Path is not a regular file")
        # Read bounded
        if stat.st_size > max_bytes:
            raise ContractInvalid(f"File too large: {stat.st_size} bytes")
        raw = os.read(fd, stat.st_size)
        return raw
    finally:
        if fd >= 0:
            os.close(fd)


# --- Safe output directory ---

def _ensure_output_dir(sandbox: Path) -> Path:
    """Create output directory safely — no symlink following."""
    output = sandbox / "output"
    if output.exists():
        if output.is_symlink():
            raise ContractInvalid("Output directory is a symlink")
        if not output.is_dir():
            raise ContractInvalid("Output path is not a directory")
    else:
        output.mkdir(parents=True, exist_ok=True)
    return output


# --- Stable error messages (no paths) ---

_ERROR_MESSAGES = {
    "candidate_missing": "Candidate file not found in sandbox.",
    "candidate_path_rejected": "Candidate path was rejected by sandbox policy.",
    "candidate_symlink_rejected": "Candidate file is a symlink.",
    "candidate_invalid_utf8": "Candidate content is not valid UTF-8.",
    "candidate_too_large": "Candidate exceeds size limit.",
    "candidate_protocol_error": "Candidate content is not valid JSON.",
    "candidate_binding_rejected": "Candidate context/profile binding rejected.",
    "candidate_evidence_mismatch": "Candidate evidence digest changed after collection.",
    "candidate_changed_before_collection": "Candidate changed between invoke and collect.",
    "sandbox_escape": "Sandbox resolved outside allowed boundary.",
    "sandbox_ref_rejected": "Sandbox reference was rejected.",
    "invalid_request_digest": "Request digest verification failed.",
    "runtime_root_invalid": "Runtime root is not a valid directory.",
    "runtime_root_unwritable": "Runtime root is not writable.",
    "runtime_root_link_rejected": "Runtime root is a symlink or junction.",
    "runtime_root_forbidden": "Runtime root is in a forbidden directory.",
}


# --- FileBackend ---

class FileBackend:
    """Shadow adapter implementing BackendPort for file-based candidate exchange.

    No external executable dependency. No process launch. No Ledger access.
    runtime_root and forbidden_roots are瞬时 and never serialized into DTOs.
    """

    def __init__(
        self,
        runtime_root: Path,
        forbidden_roots: tuple[Path, ...] = (),
    ) -> None:
        self._runtime_root = runtime_root.resolve()
        self._forbidden_roots = tuple(r.resolve() for r in forbidden_roots)

    def probe(self, request: BackendProbeRequest) -> BackendProbeResult:
        """Probe file backend availability."""
        errors: list[str] = []

        # Check runtime root exists and is a directory
        if not self._runtime_root.exists():
            errors.append("runtime_root_invalid")
        elif not self._runtime_root.is_dir():
            errors.append("runtime_root_invalid")

        # Check runtime root is not a symlink
        if self._runtime_root.is_symlink():
            errors.append("runtime_root_link_rejected")

        # Check runtime root is writable
        if self._runtime_root.exists() and not os.access(str(self._runtime_root), os.W_OK):
            errors.append("runtime_root_unwritable")

        # Check runtime root is not inside any forbidden root
        for forbidden in self._forbidden_roots:
            try:
                self._runtime_root.relative_to(forbidden)
                errors.append("runtime_root_forbidden")
                break
            except ValueError:
                pass
            # Also check if forbidden is inside runtime_root
            try:
                forbidden.relative_to(self._runtime_root)
                # forbidden is inside runtime_root — that's ok for now
            except ValueError:
                pass

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
        verify_backend_request_digest(request)
        _resolve_sandbox_ref(self._runtime_root, request.sandbox_path_ref)

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
        """Check if candidate entry exists and is a safe path type. Does NOT read content."""
        request = plan.request
        sandbox = _resolve_sandbox_ref(self._runtime_root, request.sandbox_path_ref)
        candidate_path = sandbox / "candidate.json"

        # Check link type first (before exists), to catch dangling symlinks
        if candidate_path.is_symlink():
            return self._error_result(
                request, TransportStatus.SANDBOX_VIOLATION,
                "candidate_symlink_rejected",
            )

        # Check if it's a junction/reparse point
        if hasattr(os, "FILE_ATTRIBUTE_REPARSE_POINT") and candidate_path.exists():
            try:
                attrs = ctypes.windll.kernel32.GetFileAttributesW(str(candidate_path))
                if attrs & os.FILE_ATTRIBUTE_REPARSE_POINT:
                    return self._error_result(
                        request, TransportStatus.SANDBOX_VIOLATION,
                        "candidate_symlink_rejected",
                    )
            except Exception:
                pass  # Not Windows or ctypes unavailable

        if not candidate_path.exists():
            return self._make_result(request, TransportStatus.AWAITING_EXTERNAL)

        # Must be a regular file
        if not candidate_path.is_file():
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
        """Read external candidate once, form canonical artifact. Protocol-neutral."""
        if transport.transport_status != TransportStatus.SUCCEEDED.value:
            return transport

        request = plan.request
        sandbox = _resolve_sandbox_ref(self._runtime_root, request.sandbox_path_ref)
        external_candidate = sandbox / "candidate.json"
        output_dir = _ensure_output_dir(sandbox)

        # Compute relative candidate_ref from sandbox_path_ref
        sandbox_ref = request.sandbox_path_ref
        candidate_ref = f"{sandbox_ref}/output/collected_candidate.json"

        # Check effective size limit
        effective_limit = min(request.max_stdout_bytes, 10 * 1024 * 1024)  # 10 MB
        if effective_limit <= 0:
            result = self._error_result(
                request, TransportStatus.OUTPUT_TOO_LARGE,
                "candidate_too_large",
            )
            return result

        # Safe single read — no-follow, bounded, identity check
        try:
            raw_bytes = _read_regular_file_once_no_follow(external_candidate, effective_limit)
        except ContractInvalid as exc:
            msg = str(exc).lower()
            if "not a regular file" in msg or "symlink" in msg:
                return self._error_result(
                    request, TransportStatus.SANDBOX_VIOLATION,
                    "candidate_symlink_rejected",
                )
            if "too large" in msg:
                return self._error_result(
                    request, TransportStatus.OUTPUT_TOO_LARGE,
                    "candidate_too_large",
                )
            return self._error_result(
                request, TransportStatus.CANDIDATE_REJECTED,
                "candidate_missing",
            )
        except FileNotFoundError:
            # Candidate disappeared between invoke and collect
            return self._error_result(
                request, TransportStatus.AMBIGUOUS,
                "candidate_changed_before_collection",
            )
        except OSError:
            return self._error_result(
                request, TransportStatus.CANDIDATE_REJECTED,
                "candidate_missing",
            )

        # Compute digest from raw bytes (protocol-neutral — no UTF-8/JSON here)
        candidate_digest = _sha256_bytes(raw_bytes)

        # Write canonical artifact with exclusive create
        canonical_path = output_dir / "collected_candidate.json"
        try:
            # O_CREAT | O_EXCL — fails if file already exists
            fd = os.open(str(canonical_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            os.write(fd, raw_bytes)
            os.close(fd)
        except FileExistsError:
            # Artifact already exists — verify it's the same evidence
            existing_bytes = _read_regular_file_once_no_follow(canonical_path, effective_limit)
            existing_digest = _sha256_bytes(existing_bytes)
            if existing_digest != candidate_digest:
                return self._error_result(
                    request, TransportStatus.AMBIGUOUS,
                    "candidate_evidence_mismatch",
                )
            # Same digest — idempotent reuse, continue

        # Verify canonical artifact digest
        canonical_bytes = _read_regular_file_once_no_follow(canonical_path, effective_limit)
        canonical_digest = _sha256_bytes(canonical_bytes)
        if canonical_digest != candidate_digest:
            return self._error_result(
                request, TransportStatus.AMBIGUOUS,
                "candidate_evidence_mismatch",
            )

        return dataclasses.replace(
            transport,
            candidate_ref=candidate_ref,
            candidate_digest=candidate_digest,
            finished_at=_now_iso(),
            transport_status=TransportStatus.SUCCEEDED.value,
            error_code=None,
            error_detail=None,
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
        canonical_path = sandbox / "output" / "collected_candidate.json"

        if not canonical_path.exists():
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.AMBIGUOUS.value,
                error_code="candidate_evidence_mismatch",
                error_detail=_ERROR_MESSAGES["candidate_evidence_mismatch"],
                finished_at=_now_iso(),
            )

        # Read canonical artifact (frozen evidence)
        try:
            raw_bytes = _read_regular_file_once_no_follow(canonical_path, 10 * 1024 * 1024)
        except Exception:
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.AMBIGUOUS.value,
                error_code="candidate_evidence_mismatch",
                error_detail=_ERROR_MESSAGES["candidate_evidence_mismatch"],
                finished_at=_now_iso(),
            )

        # Verify canonical digest matches transport
        canonical_digest = _sha256_bytes(raw_bytes)
        if canonical_digest != transport.candidate_digest:
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.AMBIGUOUS.value,
                error_code="candidate_evidence_mismatch",
                error_detail=_ERROR_MESSAGES["candidate_evidence_mismatch"],
                finished_at=_now_iso(),
            )

        # Strict UTF-8 decode
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.INVALID_UTF8.value,
                error_code="candidate_invalid_utf8",
                error_detail=_ERROR_MESSAGES["candidate_invalid_utf8"],
                finished_at=_now_iso(),
            )

        # Validate content against request bindings
        from .candidate import validate_candidate_content
        try:
            validate_candidate_content(
                text,
                expected_context_ref=request.context_ref,
                expected_context_digest=request.context_digest,
                expected_backend_profile_ref=request.backend_profile_ref,
            )
        except ContractInvalid as exc:
            status = _map_candidate_error(exc)
            return dataclasses.replace(
                transport,
                transport_status=status.value,
                error_code=_map_error_code(exc),
                error_detail=_ERROR_MESSAGES.get(_map_error_code(exc), "Validation failed."),
                finished_at=_now_iso(),
            )

        return transport

    def _make_result(
        self,
        request: BackendInvocationRequest,
        status: TransportStatus,
    ) -> BackendTransportResult:
        sandbox_ref = request.sandbox_path_ref
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
        sandbox_ref = request.sandbox_path_ref
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


# Conditional import for Windows reparse point detection
try:
    import ctypes
except ImportError:
    ctypes = None  # type: ignore[assignment]
