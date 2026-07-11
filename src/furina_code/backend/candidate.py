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

# Required top-level fields and their expected types
_REQUIRED_FIELDS = {
    "schema_version": str,
    "candidate_type": str,
    "backend_profile_ref": str,
    "backend_session_ref": str,
    "context_ref": str,
    "context_digest": str,
    "content": dict,
    "claimed_assumptions": list,
    "requested_actions": list,
}

# Required content fields and their expected types
_CONTENT_FIELDS = {
    "repository_head": str,
    "branch": str,
    "working_tree": str,
    "tracked_file_count": int,
    "untracked_file_count": int,
    "python_requires": (str, type(None)),
    "runtime_dependencies": list,
    "dev_dependencies": list,
    "pytest_testpaths": list,
    "ci_config": dict,
    "blind_spots": list,
}


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
    """Validate that a candidate file exists and is readable."""
    text, _, sha256_hex = read_candidate_once(candidate_path)
    return text, sha256_hex


def validate_candidate_content(
    content_text: str,
    expected_context_ref: str,
    expected_context_digest: str,
    expected_backend_profile_ref: str,
) -> dict[str, Any]:
    """Parse and validate candidate JSON content with strict schema checks."""
    try:
        data = json.loads(content_text)
    except json.JSONDecodeError as exc:
        raise ContractInvalid(f"Candidate is not valid JSON: {exc}", {"error": str(exc)})

    if not isinstance(data, dict):
        raise ContractInvalid("Candidate must be a JSON object")

    # Check required fields and types
    for field, expected_type in _REQUIRED_FIELDS.items():
        if field not in data:
            raise ContractInvalid(f"Candidate missing required field: {field}")
        if not isinstance(data[field], expected_type):
            raise ContractInvalid(
                f"Candidate field '{field}' has wrong type: expected {expected_type.__name__}, got {type(data[field]).__name__}",
                {"field": field, "expected": expected_type.__name__, "got": type(data[field]).__name__},
            )

    # Schema version
    if data["schema_version"] != "1.0":
        raise ContractInvalid(f"Unsupported schema_version: {data['schema_version']}")

    # Candidate type
    allowed_types = {"repository_baseline_report"}
    if data["candidate_type"] not in allowed_types:
        raise ContractInvalid(f"Unsupported candidate_type: {data['candidate_type']}")

    # Backend session ref must be non-empty
    if not data["backend_session_ref"]:
        raise ContractInvalid("backend_session_ref must be non-empty")

    # Context ref
    if data["context_ref"] != expected_context_ref:
        raise ContractInvalid(
            "Candidate context_ref does not match ContextEnvelope",
            {"expected": expected_context_ref, "got": data["context_ref"]},
        )

    # Context digest — strict match
    if data["context_digest"] != expected_context_digest:
        raise ContractInvalid(
            "Candidate context_digest does not match ContextEnvelope",
            {"expected": expected_context_digest, "got": data["context_digest"]},
        )

    # Backend profile ref
    if data["backend_profile_ref"] != expected_backend_profile_ref:
        raise ContractInvalid(
            "Candidate backend_profile_ref does not match BackendProfile",
            {"expected": expected_backend_profile_ref, "got": data["backend_profile_ref"]},
        )

    # requested_actions must be empty list
    if data["requested_actions"]:
        raise ContractInvalid(
            "Candidate requested_actions must be empty",
            {"requested_actions": data["requested_actions"]},
        )

    # claimed_assumptions must be list of strings
    for i, item in enumerate(data["claimed_assumptions"]):
        if not isinstance(item, str):
            raise ContractInvalid(
                f"claimed_assumptions[{i}] must be string, got {type(item).__name__}",
            )

    # Content must be a dict
    content = data["content"]
    if not isinstance(content, dict):
        raise ContractInvalid("Candidate 'content' must be a JSON object")

    # Validate content fields
    for field, expected_type in _CONTENT_FIELDS.items():
        if field not in content:
            raise ContractInvalid(f"Candidate content missing required field: {field}")
        if isinstance(expected_type, tuple):
            if not isinstance(content[field], expected_type):
                raise ContractInvalid(
                    f"Content field '{field}' has wrong type",
                    {"field": field},
                )
        else:
            if not isinstance(content[field], expected_type):
                raise ContractInvalid(
                    f"Content field '{field}' has wrong type: expected {expected_type.__name__}",
                    {"field": field},
                )

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
