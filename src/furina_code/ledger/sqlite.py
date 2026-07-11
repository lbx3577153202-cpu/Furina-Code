"""Furina Code ledger — SQLite append-only ledger."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ..contracts.errors import (
    ContractInvalid,
    AuthorityViolation,
    BindingMismatch,
    RevisionConflict,
    IntegrityCheckFailed,
    LedgerWriteFailed,
)
from ..contracts.meta import CanonicalMeta, compute_integrity_ref, SCHEMA_VERSION, now_utc
from ..contracts.objects import OWNER_MAP, check_owner

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS object_revisions (
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    meta_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    integrity_ref TEXT NOT NULL UNIQUE,
    PRIMARY KEY (object_type, object_id, revision)
);

CREATE TABLE IF NOT EXISTS object_heads (
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    current_revision INTEGER NOT NULL,
    PRIMARY KEY (object_type, object_id)
);

CREATE TABLE IF NOT EXISTS event_envelopes (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    aggregate_ref TEXT NOT NULL,
    aggregate_revision INTEGER NOT NULL,
    producer_organ TEXT NOT NULL,
    run_binding_id TEXT NOT NULL,
    task_run_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    causation_ref TEXT,
    occurred_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    payload_ref TEXT,
    integrity_ref TEXT NOT NULL
);
"""


class Ledger:
    """SQLite-backed append-only ledger for formal objects and events."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA_SQL)
        self._conn.execute(
            "INSERT OR IGNORE INTO schema_metadata (key, value) VALUES (?, ?)",
            ("schema_version", SCHEMA_VERSION),
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise LedgerWriteFailed("Ledger is not open")
        return self._conn

    def _load_meta(self, row: tuple) -> CanonicalMeta:
        d = json.loads(row[2])
        return CanonicalMeta(
            schema_version=d["schema_version"],
            object_type=d["object_type"],
            object_id=d["object_id"],
            revision=d["revision"],
            owner_organ=d["owner_organ"],
            run_binding_id=d["run_binding_id"],
            task_id=d["task_id"],
            task_run_id=d["task_run_id"],
            project_ref=d["project_ref"],
            correlation_id=d["correlation_id"],
            causation_ref=d.get("causation_ref"),
            created_at=datetime.fromisoformat(d["created_at"]),
            recorded_at=datetime.fromisoformat(d["recorded_at"]),
            classification=d["classification"],
            integrity_ref=d["integrity_ref"],
            supersedes_ref=d.get("supersedes_ref"),
        )

    def get_head_revision(self, object_type: str, object_id: str) -> int:
        cur = self.conn.execute(
            "SELECT current_revision FROM object_heads WHERE object_type=? AND object_id=?",
            (object_type, object_id),
        )
        row = cur.fetchone()
        return row[0] if row else 0

    def get_revision(self, object_type: str, object_id: str, revision: int) -> tuple[CanonicalMeta, dict] | None:
        cur = self.conn.execute(
            "SELECT object_type, object_id, meta_json, payload_json, integrity_ref FROM object_revisions "
            "WHERE object_type=? AND object_id=? AND revision=?",
            (object_type, object_id, revision),
        )
        row = cur.fetchone()
        if row is None:
            return None
        meta = self._load_meta((row[0], row[1], row[2]))
        payload = json.loads(row[3])
        stored_ref = row[4]
        # Verify integrity
        meta_fields = meta.meta_fields_for_integrity()
        expected_ref = compute_integrity_ref(meta_fields, payload)
        if stored_ref != expected_ref:
            raise IntegrityCheckFailed(
                f"Integrity mismatch for {object_type}:{object_id}:rev{revision}",
                {"stored": stored_ref, "computed": expected_ref},
            )
        return meta, payload

    def get_latest(self, object_type: str, object_id: str) -> tuple[CanonicalMeta, dict] | None:
        rev = self.get_head_revision(object_type, object_id)
        if rev == 0:
            return None
        return self.get_revision(object_type, object_id, rev)

    def write_object(
        self,
        meta: CanonicalMeta,
        payload: dict[str, Any],
        caller_organ: str,
        expected_revision: int,
    ) -> None:
        """Write a new object revision with atomic event append."""
        check_owner(meta.object_type, caller_organ, meta.owner_organ)

        current_rev = self.get_head_revision(meta.object_type, meta.object_id)

        if expected_revision != current_rev:
            raise RevisionConflict(
                f"expected_revision={expected_revision} but current={current_rev} "
                f"for {meta.object_type}:{meta.object_id}",
                {"expected": expected_revision, "current": current_rev},
            )

        # Verify integrity
        meta_fields = meta.meta_fields_for_integrity()
        expected_ref = compute_integrity_ref(meta_fields, payload)
        if meta.integrity_ref != expected_ref:
            raise IntegrityCheckFailed(
                "integrity_ref does not match computed hash",
                {"provided": meta.integrity_ref, "computed": expected_ref},
            )

        # Build event
        now = now_utc()
        event_id = f"evt:{meta.object_type}:{meta.object_id}:rev{meta.revision}:{now.timestamp()}"
        event_type = f"{meta.object_type}.{'created' if meta.revision == 1 else 'revised'}"
        payload_ref = f"sha256:{__import__('hashlib').sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()}"
        event_integrity_fields = {
            "event_id": event_id,
            "event_type": event_type,
            "aggregate_ref": f"{meta.object_type}:{meta.object_id}",
            "aggregate_revision": meta.revision,
            "producer_organ": meta.owner_organ,
            "run_binding_id": meta.run_binding_id,
            "task_run_id": meta.task_run_id,
            "correlation_id": meta.correlation_id,
            "causation_ref": meta.causation_ref,
            "occurred_at": meta.created_at.isoformat(),
            "recorded_at": now.isoformat(),
            "payload_ref": payload_ref,
        }
        event_integrity = compute_integrity_ref(event_integrity_fields, {})

        try:
            cur = self.conn.cursor()
            cur.execute("BEGIN IMMEDIATE")

            # Insert object revision
            cur.execute(
                "INSERT INTO object_revisions (object_type, object_id, revision, meta_json, payload_json, integrity_ref) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    meta.object_type,
                    meta.object_id,
                    meta.revision,
                    json.dumps(meta.to_dict(), sort_keys=True),
                    json.dumps(payload, sort_keys=True),
                    meta.integrity_ref,
                ),
            )

            # Update or insert head
            cur.execute(
                "INSERT INTO object_heads (object_type, object_id, current_revision) VALUES (?, ?, ?) "
                "ON CONFLICT(object_type, object_id) DO UPDATE SET current_revision=excluded.current_revision",
                (meta.object_type, meta.object_id, meta.revision),
            )

            # Insert event
            cur.execute(
                "INSERT INTO event_envelopes "
                "(event_id, event_type, aggregate_ref, aggregate_revision, producer_organ, "
                "run_binding_id, task_run_id, correlation_id, causation_ref, "
                "occurred_at, recorded_at, payload_ref, integrity_ref) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    event_type,
                    f"{meta.object_type}:{meta.object_id}",
                    meta.revision,
                    meta.owner_organ,
                    meta.run_binding_id,
                    meta.task_run_id,
                    meta.correlation_id,
                    meta.causation_ref,
                    meta.created_at.isoformat(),
                    now.isoformat(),
                    payload_ref,
                    event_integrity,
                ),
            )

            cur.execute("COMMIT")
        except Exception:
            self.conn.rollback()
            raise

    def get_events(self, run_binding_id: str) -> list[dict[str, Any]]:
        cur = self.conn.execute(
            "SELECT * FROM event_envelopes WHERE run_binding_id=? ORDER BY sequence",
            (run_binding_id,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_last_sequence(self) -> int:
        cur = self.conn.execute("SELECT COALESCE(MAX(sequence), 0) FROM event_envelopes")
        return cur.fetchone()[0]
