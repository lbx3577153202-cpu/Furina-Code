"""Furina Code backend — candidate file validation and envelope creation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..contracts.errors import ContractInvalid
from ..contracts.meta import canonical_json_dumps
from ..contracts.objects import CandidateEnvelope

MAX_CANDIDATE_BYTES = 10 * 1024 * 1024  # 10 MB


def _check_candidate_path(candidate_path: str) -> Path:
    """Validate candidate file path (no symlinks, no traversal)."""
    p = Path(candidate_path)
    if ".." in p.parts:
        raise ContractInvalid(f"Path traversal rejected: {candidate_path}")
    if not p.exists():
        raise ContractInvalid(f"Candidate file not found: {candidate_path}")
    if p.is_symlink():
        raise ContractInvalid(f"Candidate file is a symlink: {candidate_path}")
    if not p.is_file():
        raise ContractInvalid(f"Candidate path is not a file: {candidate_path}")
    return p


def read_candidate_once(candidate_path: str) -> tuple[str, dict[str, Any], str]:
    """Read candidate file exactly once. Returns (text, parsed_dict, sha256_hex)."""
    p = _check_candidate_path(candidate_path)
    size = p.stat().st_size
    if size == 0:
        raise ContractInvalid(f"Candidate file is empty: {candidate_path}")
    if size > MAX_CANDIDATE_BYTES:
        raise ContractInvalid(
            f"Candidate file too large: {size} bytes (max {MAX_CANDIDATE_BYTES})",
            {"size": size, "max": MAX_CANDIDATE_BYTES},
        )
    raw = p.read_bytes()
    sha256_hex = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractInvalid(f"Candidate file is not valid UTF-8: {exc}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractInvalid(f"Candidate is not valid JSON: {exc}", {"error": str(exc)})
    if not isinstance(parsed, dict):
        raise ContractInvalid("Candidate must be a JSON object")
    return text, parsed, sha256_hex


def validate_candidate_file(candidate_path: str) -> tuple[str, str]:
    """Validate that a candidate file exists and is readable.
    Returns (content_text, sha256_hex).
    """
    text, _, sha256_hex = read_candidate_once(candidate_path)
    return text, sha256_hex


def validate_candidate_content(
    content_text: str,
    context_ref: str,
    backend_ref: str,
) -> dict[str, Any]:
    """Parse and validate candidate JSON content. Returns parsed dict."""
    try:
        data = json.loads(content_text)
    except json.JSONDecodeError as exc:
        raise ContractInvalid(f"Candidate is not valid JSON: {exc}", {"error": str(exc)})

    if data.get("schema_version") != "1.0":
        raise ContractInvalid(
            f"Unsupported candidate schema_version: {data.get('schema_version')}",
            {"schema_version": data.get("schema_version")},
        )

    allowed_types = {"repository_baseline_report"}
    if data.get("candidate_type") not in allowed_types:
        raise ContractInvalid(
            f"Unsupported candidate_type: {data.get('candidate_type')}",
            {"candidate_type": data.get("candidate_type")},
        )

    if data.get("context_ref") != context_ref:
        raise ContractInvalid(
            "Candidate context_ref does not match ContextEnvelope",
            {"expected": context_ref, "got": data.get("context_ref")},
        )

    if data.get("backend_profile_ref") != backend_ref:
        raise ContractInvalid(
            "Candidate backend_profile_ref does not match BackendProfile",
            {"expected": backend_ref, "got": data.get("backend_profile_ref")},
        )

    ra = data.get("requested_actions", [])
    if ra:
        raise ContractInvalid(
            "Candidate requested_actions must be empty",
            {"requested_actions": ra},
        )

    if "content" not in data:
        raise ContractInvalid("Candidate missing 'content' section")

    return data


def create_candidate_envelope(
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    candidate_type: str,
    backend_profile_ref: str,
    backend_session_ref: str,
    context_ref: str,
    content_ref: str,
    candidate_digest: str,
    claimed_assumptions: tuple[str, ...] = (),
    requested_actions: tuple[str, ...] = (),
    envelope_id: str | None = None,
    causation_ref: str | None = None,
) -> CandidateEnvelope:
    """Create a CandidateEnvelope from pre-validated candidate data."""
    return CandidateEnvelope.create(
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref=project_ref,
        correlation_id=correlation_id,
        candidate_type=candidate_type,
        backend_profile_ref=backend_profile_ref,
        backend_session_ref=backend_session_ref,
        context_ref=context_ref,
        content_ref=content_ref,
        candidate_digest=candidate_digest,
        claimed_assumptions=claimed_assumptions,
        requested_actions=requested_actions,
        envelope_id=envelope_id,
        causation_ref=causation_ref,
    )
