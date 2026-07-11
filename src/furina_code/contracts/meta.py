"""Furina Code contracts — CanonicalMeta for formal object revisions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

CLASSIFICATION_PUBLIC = "public"
CLASSIFICATION_PROJECT_INTERNAL = "project_internal"
CLASSIFICATION_SENSITIVE = "sensitive"
CLASSIFICATION_SECRET = "secret"
VALID_CLASSIFICATIONS = frozenset({
    CLASSIFICATION_PUBLIC,
    CLASSIFICATION_PROJECT_INTERNAL,
    CLASSIFICATION_SENSITIVE,
    CLASSIFICATION_SECRET,
})

SCHEMA_VERSION = "1.0"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def compute_integrity_ref(meta_fields: dict[str, Any], payload: dict[str, Any]) -> str:
    """Compute sha256:<hex> over CanonicalMeta fields (excluding integrity_ref) + payload."""
    combined = {"meta": meta_fields, "payload": payload}
    raw = json.dumps(combined, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


@dataclass(frozen=True)
class CanonicalMeta:
    schema_version: str
    object_type: str
    object_id: str
    revision: int
    owner_organ: str
    run_binding_id: str
    task_id: str
    task_run_id: str
    project_ref: str
    correlation_id: str
    causation_ref: str | None
    created_at: datetime
    recorded_at: datetime
    classification: str
    integrity_ref: str
    supersedes_ref: str | None

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unknown schema_version: {self.schema_version}")
        if self.revision < 1:
            raise ValueError(f"revision must be >= 1, got {self.revision}")
        if self.classification not in VALID_CLASSIFICATIONS:
            raise ValueError(f"Invalid classification: {self.classification}")
        if self.revision > 1 and not self.supersedes_ref:
            raise ValueError("supersedes_ref required when revision > 1")
        if self.revision == 1 and self.supersedes_ref is not None:
            raise ValueError("supersedes_ref must be None when revision == 1")
        if not self.integrity_ref.startswith("sha256:") or len(self.integrity_ref) != 71:
            raise ValueError(f"Invalid integrity_ref format: {self.integrity_ref}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict (timestamps as ISO strings)."""
        d = {
            "schema_version": self.schema_version,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "revision": self.revision,
            "owner_organ": self.owner_organ,
            "run_binding_id": self.run_binding_id,
            "task_id": self.task_id,
            "task_run_id": self.task_run_id,
            "project_ref": self.project_ref,
            "correlation_id": self.correlation_id,
            "causation_ref": self.causation_ref,
            "created_at": self.created_at.isoformat(),
            "recorded_at": self.recorded_at.isoformat(),
            "classification": self.classification,
            "integrity_ref": self.integrity_ref,
            "supersedes_ref": self.supersedes_ref,
        }
        return d

    def meta_fields_for_integrity(self) -> dict[str, Any]:
        """Return all meta fields except integrity_ref, for hash computation."""
        d = self.to_dict()
        d.pop("integrity_ref")
        return d
