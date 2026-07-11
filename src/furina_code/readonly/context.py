"""Furina Code readonly — ContextEnvelope creation and context packet writing."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..contracts.meta import canonical_json_dumps
from ..contracts.objects import ContextEnvelope, ProjectSnapshot, TaskDossier


def create_context_envelope(
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    snapshot: ProjectSnapshot,
    dossier: TaskDossier,
    backend_ref: str = "",
    envelope_id: str | None = None,
    causation_ref: str | None = None,
) -> ContextEnvelope:
    """Build a ContextEnvelope from a ProjectSnapshot and TaskDossier."""
    snapshot_summary = {
        "head_sha": snapshot.head_sha,
        "branch": snapshot.branch,
        "tracked_file_count": snapshot.tracked_count,
        "untracked_file_count": snapshot.untracked_count,
        "is_clean": snapshot.is_clean,
        "pyproject_exists": snapshot.pyproject_exists,
        "requires_python": snapshot.requires_python,
        "runtime_deps": list(snapshot.runtime_deps),
        "dev_deps": list(snapshot.dev_deps),
        "pytest_testpaths": list(snapshot.pytest_testpaths),
        "ci_config_exists": snapshot.ci_config_exists,
        "ci_config_sha256": snapshot.ci_config_sha256,
        "blind_spots": list(snapshot.blind_spots),
    }

    context_payload = {
        "structured_goal": dossier.structured_goal,
        "scope": list(dossier.scope),
        "exclusions": list(dossier.exclusions),
        "unknowns": list(dossier.unknowns),
        "success_criteria": list(dossier.success_criteria),
        "snapshot_summary": snapshot_summary,
        "instruction_profile": {
            "id": "e4-repository-baseline-v1",
            "version": "1.0",
        },
    }

    # Compute context digest over the canonical packet structure
    # (the same structure that write_context_packet will use, minus digest)
    packet_for_digest = {
        "schema_version": "1.0",
        "snapshot_ref": snapshot.meta.integrity_ref,
        "task_dossier_ref": dossier.meta.integrity_ref,
        "context_payload": context_payload,
        "instruction_profile": {"id": "e4-repository-baseline-v1", "version": "1.0"},
    }
    context_digest = "sha256:" + hashlib.sha256(
        canonical_json_dumps(packet_for_digest).encode("utf-8")
    ).hexdigest()

    included_refs = [
        snapshot.meta.integrity_ref,
        dossier.meta.integrity_ref,
    ]
    if backend_ref:
        included_refs.append(backend_ref)

    redactions = [
        "absolute_workspace_path",
        "environment_variables",
        "git_user_info",
        "credentials",
        "runtime_database_content",
        "repository_file_contents",
    ]

    return ContextEnvelope.create(
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref=project_ref,
        correlation_id=correlation_id,
        task_revision=dossier.meta.revision,
        purpose="repository-baseline-observation",
        snapshot_ref=snapshot.meta.integrity_ref,
        task_dossier_ref=dossier.meta.integrity_ref,
        included_refs=tuple(included_refs),
        redactions=tuple(redactions),
        classification_summary="project_internal — no secrets, no file contents, no env vars",
        disclosure_basis="allowlist — only structured metadata, no raw content",
        backend_ref=backend_ref,
        context_digest=context_digest,
        context_payload=context_payload,
        envelope_id=envelope_id,
        causation_ref=causation_ref,
    )


def write_context_packet(envelope: ContextEnvelope, output_path: str) -> str:
    """Write context packet to disk and return its SHA-256 digest.

    The digest is computed over the canonical packet (without context_envelope_ref
    and context_digest). This matches the structure used in create_context_envelope.
    """
    # Build the digest-input structure (same as create_context_envelope uses)
    digest_input = {
        "schema_version": "1.0",
        "snapshot_ref": envelope.snapshot_ref,
        "task_dossier_ref": envelope.task_dossier_ref,
        "context_payload": envelope.context_payload,
        "instruction_profile": envelope.instruction_profile,
    }
    digest = "sha256:" + hashlib.sha256(
        canonical_json_dumps(digest_input).encode("utf-8")
    ).hexdigest()

    # Write full packet including envelope_ref and digest
    full_packet = {
        "schema_version": "1.0",
        "context_envelope_ref": envelope.meta.integrity_ref,
        "snapshot_ref": envelope.snapshot_ref,
        "task_dossier_ref": envelope.task_dossier_ref,
        "context_payload": envelope.context_payload,
        "instruction_profile": envelope.instruction_profile,
        "context_digest": digest,
    }
    Path(output_path).write_text(canonical_json_dumps(full_packet), encoding="utf-8")
    return digest
