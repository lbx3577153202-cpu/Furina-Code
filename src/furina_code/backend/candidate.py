"""Furina Code backend — candidate file validation and envelope creation."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..contracts.errors import ContractInvalid
from ..contracts.meta import canonical_json_dumps
from ..contracts.objects import CandidateEnvelope

MAX_CANDIDATE_BYTES = 10 * 1024 * 1024  # 10 MB


def validate_candidate_file(candidate_path: str) -> tuple[str, str]:
    """Validate that a candidate file exists and is readable.

    Returns (content_text, sha256_hex).
    """
    p = Path(candidate_path)
    if not p.is_file():
        raise ContractInvalid(f"Candidate file not found: {candidate_path}")
    size = p.stat().st_size
    if size == 0:
        raise ContractInvalid(f"Candidate file is empty: {candidate_path}")
    if size > MAX_CANDIDATE_BYTES:
        raise ContractInvalid(
            f"Candidate file too large: {size} bytes (max {MAX_CANDIDATE_BYTES})",
            {"size": size, "max": MAX_CANDIDATE_BYTES},
        )
    raw = p.read_bytes()
    content = raw.decode("utf-8")
    sha256_hex = hashlib.sha256(raw).hexdigest()
    return content, sha256_hex


def validate_candidate_content(content: str, context_ref: str, backend_ref: str) -> dict[str, Any]:
    """Parse and validate candidate JSON content.

    Returns parsed dict. Raises ContractInvalid on violations.
    """
    import json
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ContractInvalid(f"Candidate is not valid JSON: {exc}", {"error": str(exc)})

    if not isinstance(data, dict):
        raise ContractInvalid("Candidate must be a JSON object")

    # Schema version
    if data.get("schema_version") != "1.0":
        raise ContractInvalid(
            f"Unsupported candidate schema_version: {data.get('schema_version')}",
            {"schema_version": data.get("schema_version")},
        )

    # Candidate type
    allowed_types = {"repository_baseline_report"}
    if data.get("candidate_type") not in allowed_types:
        raise ContractInvalid(
            f"Unsupported candidate_type: {data.get('candidate_type')}",
            {"candidate_type": data.get("candidate_type")},
        )

    # Context ref consistency
    if data.get("context_ref") != context_ref:
        raise ContractInvalid(
            "Candidate context_ref does not match ContextEnvelope",
            {"expected": context_ref, "got": data.get("context_ref")},
        )

    # Backend ref consistency
    if data.get("backend_profile_ref") != backend_ref:
        raise ContractInvalid(
            "Candidate backend_profile_ref does not match BackendProfile",
            {"expected": backend_ref, "got": data.get("backend_profile_ref")},
        )

    # requested_actions must be empty
    ra = data.get("requested_actions", [])
    if ra:
        raise ContractInvalid(
            "Candidate requested_actions must be empty",
            {"requested_actions": ra},
        )

    # Content section required
    if "content" not in data:
        raise ContractInvalid("Candidate missing 'content' section")

    return data


def create_candidate_envelope(
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    context_envelope_ref: str,
    candidate_path: str,
    backend_id: str,
    envelope_id: str | None = None,
) -> CandidateEnvelope:
    """Validate candidate file and create a CandidateEnvelope."""
    _, sha256_hex = validate_candidate_file(candidate_path)
    return CandidateEnvelope.create(
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref=project_ref,
        correlation_id=correlation_id,
        context_envelope_ref=context_envelope_ref,
        candidate_path=candidate_path,
        candidate_sha256=sha256_hex,
        backend_id=backend_id,
        envelope_id=envelope_id,
    )
