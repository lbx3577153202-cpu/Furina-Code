"""Furina Code readonly — E4 FileBackend bridge.

Pure orchestration helpers for wiring E4 prepare and finalize to FileBackend.
Does NOT write Ledger, create formal objects, or transition TaskRun.
"""

from __future__ import annotations

import hashlib
import json as _json
from dataclasses import replace
from pathlib import Path

from ..backend.file_backend import FileBackend
from ..backend.port import (
    BackendInvocationRequest,
    BackendInvocationPlan,
    BackendProbeRequest,
    BackendTransportResult,
    TransportStatus,
    compute_backend_request_digest,
)
from ..contracts.errors import ContractInvalid
from ..contracts.meta import canonical_json_dumps


def _instruction_profile_ref(instruction_profile: dict) -> str:
    """Compute a deterministic ref from the instruction profile dict."""
    raw = canonical_json_dumps(instruction_profile).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def build_e4_file_backend_request(
    *,
    run_binding_id: str,
    task_run_id: str,
    backend_profile_ref: str,
    context_ref: str,
    context_digest: str,
    instruction_profile: dict,
    max_candidate_bytes: int = 10_000_000,
) -> BackendInvocationRequest:
    """Build a BackendInvocationRequest for E4 file-based candidate delivery.

    All refs are relative or logical. No absolute paths, no credentials,
    no environment variable values.
    """
    sandbox_path_ref = f"backend/{run_binding_id}/{task_run_id}"
    invocation_id = f"file-{task_run_id}"
    backend_session_ref = f"{run_binding_id}:file:{task_run_id}"
    instruction_profile_ref = _instruction_profile_ref(instruction_profile)

    request = BackendInvocationRequest(
        run_binding_id=run_binding_id,
        invocation_id=invocation_id,
        backend_session_ref=backend_session_ref,
        backend_profile_ref=backend_profile_ref,
        context_ref=context_ref,
        context_digest=context_digest,
        instruction_text="e4-repository-baseline-observation",
        instruction_profile_ref=instruction_profile_ref,
        config_ref="e4:file-backend:v1",
        sandbox_policy_ref="trusted-runtime-only:v1",
        request_digest="",  # placeholder, recomputed below
        model_ref=None,
        timeout_seconds=0,
        max_stdout_bytes=max_candidate_bytes,
        max_stderr_bytes=1_000_000,
        fresh_session=True,
        sandbox_path_ref=sandbox_path_ref,
    )

    digest = compute_backend_request_digest(request)
    return replace(request, request_digest=digest)


def prepare_e4_file_transport(
    *,
    runtime_dir: Path,
    repository_root: Path,
    run_binding_id: str,
    task_run_id: str,
    backend_profile_ref: str,
    context_ref: str,
    context_digest: str,
    instruction_profile: dict,
    max_candidate_bytes: int = 10_000_000,
) -> tuple[BackendTransportResult, str]:
    """Run FileBackend probe → prepare → invoke. Returns (transport, candidate_drop_path).

    Raises ContractInvalid if probe fails or invoke returns unexpected status.

    candidate_drop_path is an absolute path suitable for CLI output only —
    it must NOT be written into any DTO, Ledger, or formal object.
    """
    request = build_e4_file_backend_request(
        run_binding_id=run_binding_id,
        task_run_id=task_run_id,
        backend_profile_ref=backend_profile_ref,
        context_ref=context_ref,
        context_digest=context_digest,
        instruction_profile=instruction_profile,
        max_candidate_bytes=max_candidate_bytes,
    )

    backend = FileBackend(
        runtime_root=runtime_dir,
        forbidden_roots=(repository_root,),
    )

    # Probe
    probe = backend.probe(BackendProbeRequest(
        executable_ref="file-backend",
        probe_timeout_seconds=5,
    ))
    if not probe.available:
        raise ContractInvalid(
            "FILE_BACKEND_UNAVAILABLE",
            {"errors": list(probe.errors)},
        )

    # Prepare (verifies digest, resolves sandbox ref)
    plan = backend.prepare(request)

    # Create sandbox directory for external candidate delivery
    sandbox_dir = runtime_dir / request.sandbox_path_ref
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    # Invoke (checks if candidate.json exists — should be awaiting_external)
    transport = backend.invoke(plan)

    if transport.transport_status != TransportStatus.AWAITING_EXTERNAL.value:
        raise ContractInvalid(
            "FILE_BACKEND_UNEXPECTED_STATUS",
            {"status": transport.transport_status},
        )

    # Candidate drop path — absolute, for CLI output only
    candidate_drop_path = str(
        runtime_dir / request.sandbox_path_ref / "candidate.json"
    )

    return transport, candidate_drop_path


def finalize_e4_file_transport(
    *,
    runtime_dir: Path,
    repository_root: Path | None = None,
    run_binding_id: str,
    task_run_id: str,
    candidate_file: str,
    backend_profile_ref: str,
    context_ref: str,
    context_digest: str,
    instruction_profile: dict,
    max_candidate_bytes: int = 10_000_000,
) -> BackendTransportResult:
    """Run FileBackend prepare → invoke → collect → strict_validate for finalize.

    Verifies that candidate_file matches the deterministic candidate path.
    Returns the validated transport result with canonical digest.

    Raises ContractInvalid on path mismatch, probe failure, or validation failure.
    """
    request = build_e4_file_backend_request(
        run_binding_id=run_binding_id,
        task_run_id=task_run_id,
        backend_profile_ref=backend_profile_ref,
        context_ref=context_ref,
        context_digest=context_digest,
        instruction_profile=instruction_profile,
        max_candidate_bytes=max_candidate_bytes,
    )

    # Verify candidate path matches deterministic path
    expected_candidate = str(
        runtime_dir / request.sandbox_path_ref / "candidate.json"
    )
    resolved_candidate = str(Path(candidate_file).resolve())
    if resolved_candidate != expected_candidate:
        raise ContractInvalid(
            "CANDIDATE_PATH_MISMATCH",
            {"expected": expected_candidate, "got": resolved_candidate},
        )

    backend = FileBackend(
        runtime_root=runtime_dir,
        forbidden_roots=(repository_root,) if repository_root else (),
    )

    # Prepare (verifies digest, resolves sandbox ref)
    plan = backend.prepare(request)

    # Invoke (should return succeeded since candidate exists)
    transport = backend.invoke(plan)

    if transport.transport_status == TransportStatus.AWAITING_EXTERNAL.value:
        raise ContractInvalid(
            "CANDIDATE_NOT_FOUND",
            {"status": "awaiting_external"},
        )
    if transport.transport_status != TransportStatus.SUCCEEDED.value:
        raise ContractInvalid(
            "FILE_BACKEND_INVOKE_FAILED",
            {"status": transport.transport_status, "error": transport.error_code},
        )

    # Collect (reads candidate once, writes canonical artifact)
    transport = backend.collect(plan, transport)

    if transport.transport_status != TransportStatus.SUCCEEDED.value:
        raise ContractInvalid(
            "FILE_BACKEND_COLLECT_FAILED",
            {"status": transport.transport_status, "error": transport.error_code},
        )

    # Strict validate (verifies canonical artifact digest + bindings)
    transport = backend.strict_validate(request, transport)

    if transport.transport_status != TransportStatus.SUCCEEDED.value:
        raise ContractInvalid(
            "FILE_BACKEND_VALIDATION_FAILED",
            {"status": transport.transport_status, "error": transport.error_code},
        )

    return transport
