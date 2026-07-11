"""Furina Code readonly — ContextEnvelope creation and context packet writing."""

from __future__ import annotations

import hashlib
import json
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
    envelope_id: str | None = None,
) -> ContextEnvelope:
    """Build a ContextEnvelope from a ProjectSnapshot and TaskDossier."""
    context_payload = {
        "structured_goal": dossier.structured_goal,
        "scope": list(dossier.scope),
        "exclusions": list(dossier.exclusions),
        "unknowns": list(dossier.unknowns),
        "success_criteria": list(dossier.success_criteria),
        "snapshot_summary": {
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
        },
        "instruction_profile": {
            "id": "e4-repository-baseline-v1",
            "version": "1.0",
        },
    }
    return ContextEnvelope.create(
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref=project_ref,
        correlation_id=correlation_id,
        snapshot_ref=snapshot.meta.integrity_ref,
        task_dossier_ref=dossier.meta.integrity_ref,
        context_payload=context_payload,
        envelope_id=envelope_id,
    )


def write_context_packet(envelope: ContextEnvelope, output_path: str) -> str:
    """Write context packet to disk and return its SHA-256 digest."""
    packet = {
        "schema_version": "1.0",
        "context_envelope_ref": envelope.meta.integrity_ref,
        "snapshot_ref": envelope.snapshot_ref,
        "task_dossier_ref": envelope.task_dossier_ref,
        "context_payload": envelope.context_payload,
        "instruction_profile": {
            "id": envelope.instruction_profile_id,
            "version": envelope.instruction_profile_version,
        },
    }
    content = canonical_json_dumps(packet)
    digest = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    Path(output_path).write_text(content, encoding="utf-8")
    return digest
