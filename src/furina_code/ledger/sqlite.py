"""Furina Code ledger — SQLite append-only ledger."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ..contracts.errors import (
    FurinaContractError,
    ContractInvalid,
    AuthorityViolation,
    BindingMismatch,
    RevisionConflict,
    IntegrityCheckFailed,
    LedgerWriteFailed,
)
from ..contracts.meta import (
    CanonicalMeta,
    compute_integrity_ref,
    canonical_json_dumps,
    SCHEMA_VERSION,
    now_utc,
)
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

# Stable identity fields that must not change across revisions.
_STABLE_FIELDS = (
    "schema_version",
    "object_type",
    "object_id",
    "owner_organ",
    "run_binding_id",
    "task_id",
    "task_run_id",
    "project_ref",
)


class Ledger:
    """SQLite-backed append-only ledger for formal objects and events."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._atomic_fail_after: int = -1  # -1 = no injection; >=0 = fail after N objects

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

    # ------------------------------------------------------------------ read

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

    def get_revision(self, object_type: str, object_id: str, revision: int) -> tuple[CanonicalMeta, dict]:
        cur = self.conn.execute(
            "SELECT object_type, object_id, revision, meta_json, payload_json, integrity_ref "
            "FROM object_revisions WHERE object_type=? AND object_id=? AND revision=?",
            (object_type, object_id, revision),
        )
        row = cur.fetchone()
        if row is None:
            raise IntegrityCheckFailed(
                f"Revision {revision} not found for {object_type}:{object_id}",
                {"object_type": object_type, "object_id": object_id, "revision": revision},
            )

        row_object_type = row[0]
        row_object_id = row[1]
        row_revision = row[2]
        stored_integrity_ref = row[5]
        meta = self._load_meta((row[0], row[1], row[3]))
        payload = json.loads(row[4])

        # Cross-check: requested values vs column values
        if row_object_type != object_type:
            raise IntegrityCheckFailed(
                "Column object_type does not match requested object_type",
                {"requested": object_type, "column": row_object_type},
            )
        if row_object_id != object_id:
            raise IntegrityCheckFailed(
                "Column object_id does not match requested object_id",
                {"requested": object_id, "column": row_object_id},
            )
        if row_revision != revision:
            raise IntegrityCheckFailed(
                "Column revision does not match requested revision",
                {"requested": revision, "column": row_revision},
            )

        # Cross-check: column values vs meta JSON values
        if row_object_type != meta.object_type:
            raise IntegrityCheckFailed(
                "Column object_type mismatch with meta_json",
                {"column": row_object_type, "meta": meta.object_type},
            )
        if row_object_id != meta.object_id:
            raise IntegrityCheckFailed(
                "Column object_id mismatch with meta_json",
                {"column": row_object_id, "meta": meta.object_id},
            )
        if row_revision != meta.revision:
            raise IntegrityCheckFailed(
                "Column revision mismatch with meta_json",
                {"column": row_revision, "meta": meta.revision},
            )

        # Cross-check: stored integrity_ref in column vs in meta_json
        if stored_integrity_ref != meta.integrity_ref:
            raise IntegrityCheckFailed(
                "integrity_ref column differs from meta_json integrity_ref",
                {"column": stored_integrity_ref, "meta_json": meta.integrity_ref},
            )

        # Recompute and verify integrity
        meta_fields = meta.meta_fields_for_integrity()
        expected_ref = compute_integrity_ref(meta_fields, payload)
        if stored_integrity_ref != expected_ref:
            raise IntegrityCheckFailed(
                f"Integrity mismatch for {object_type}:{object_id}:rev{revision}",
                {"stored": stored_integrity_ref, "computed": expected_ref},
            )

        return meta, payload

    def get_latest(self, object_type: str, object_id: str) -> tuple[CanonicalMeta, dict] | None:
        rev = self.get_head_revision(object_type, object_id)
        if rev == 0:
            return None
        # Fail-closed: if head points to a revision that doesn't exist or
        # fails integrity, propagate the error instead of returning None.
        return self.get_revision(object_type, object_id, rev)

    def get_latest_for_binding(self, run_binding_id: str) -> tuple[tuple[CanonicalMeta, dict], ...]:
        """Return every current formal object belonging to one local binding.

        The query deliberately returns only object heads, then reuses
        :meth:`get_revision` for every row.  A continuity rebuild must never
        trust a convenience query without re-checking the persisted integrity
        reference of each object it exposes as local authority.
        """
        cur = self.conn.execute(
            "SELECT revisions.object_type, revisions.object_id, heads.current_revision "
            "FROM object_revisions AS revisions "
            "JOIN object_heads AS heads "
            "  ON heads.object_type=revisions.object_type "
            " AND heads.object_id=revisions.object_id "
            " AND heads.current_revision=revisions.revision "
            "WHERE json_extract(revisions.meta_json, '$.run_binding_id')=? "
            "ORDER BY revisions.object_type, revisions.object_id",
            (run_binding_id,),
        )
        return tuple(
            self.get_revision(object_type, object_id, revision)
            for object_type, object_id, revision in cur.fetchall()
        )

    # --------------------------------------------------------------- write

    def _new_event_id(self, meta: CanonicalMeta) -> str:
        """Generate event ID. Overridable in tests for failure injection."""
        now = now_utc()
        return f"evt:{meta.object_type}:{meta.object_id}:rev{meta.revision}:{now.timestamp()}"

    def write_object(
        self,
        meta: CanonicalMeta,
        payload: dict[str, Any],
        caller_organ: str,
        expected_revision: int,
    ) -> None:
        """Write a new object revision with atomic event append.

        All checks and writes occur inside a single BEGIN IMMEDIATE transaction.
        """
        check_owner(meta.object_type, caller_organ, meta.owner_organ)

        try:
            cur = self.conn.cursor()
            cur.execute("BEGIN IMMEDIATE")

            # ---- read current head INSIDE transaction ----
            cur.execute(
                "SELECT current_revision FROM object_heads WHERE object_type=? AND object_id=?",
                (meta.object_type, meta.object_id),
            )
            head_row = cur.fetchone()
            current_rev = head_row[0] if head_row else 0

            # ---- revision check ----
            if expected_revision != current_rev:
                raise RevisionConflict(
                    f"expected_revision={expected_revision} but current={current_rev} "
                    f"for {meta.object_type}:{meta.object_id}",
                    {"expected": expected_revision, "current": current_rev},
                )

            # ---- exact next revision ----
            if meta.revision != current_rev + 1:
                raise RevisionConflict(
                    f"revision must be {current_rev + 1}, got {meta.revision}",
                    {"expected": current_rev + 1, "got": meta.revision},
                )

            # ---- supersedes_ref ----
            if current_rev == 0:
                if meta.supersedes_ref is not None:
                    raise ContractInvalid(
                        "supersedes_ref must be None for initial creation",
                        {"supersedes_ref": meta.supersedes_ref},
                    )
            else:
                expected_supersedes = f"{meta.object_type}:{meta.object_id}:rev{current_rev}"
                if meta.supersedes_ref != expected_supersedes:
                    raise ContractInvalid(
                        f"supersedes_ref must be {expected_supersedes}",
                        {"expected": expected_supersedes, "got": meta.supersedes_ref},
                    )

            # ---- binding stability (revision > 1) ----
            if current_rev > 0:
                cur.execute(
                    "SELECT meta_json FROM object_revisions "
                    "WHERE object_type=? AND object_id=? AND revision=?",
                    (meta.object_type, meta.object_id, current_rev),
                )
                prev_row = cur.fetchone()
                if prev_row is None:
                    raise LedgerWriteFailed(
                        f"Previous revision {current_rev} not found for "
                        f"{meta.object_type}:{meta.object_id}",
                    )
                prev_meta = json.loads(prev_row[0])
                new_meta = meta.to_dict()
                for field in _STABLE_FIELDS:
                    if prev_meta.get(field) != new_meta.get(field):
                        raise BindingMismatch(
                            f"Stable field '{field}' changed between revisions",
                            {
                                "field": field,
                                "previous": prev_meta.get(field),
                                "new": new_meta.get(field),
                            },
                        )

            # ---- integrity ----
            meta_fields = meta.meta_fields_for_integrity()
            expected_ref = compute_integrity_ref(meta_fields, payload)
            if meta.integrity_ref != expected_ref:
                raise IntegrityCheckFailed(
                    "integrity_ref does not match computed hash",
                    {"provided": meta.integrity_ref, "computed": expected_ref},
                )

            # ---- canonical JSON ----
            meta_json = canonical_json_dumps(meta.to_dict())
            payload_json = canonical_json_dumps(payload)

            # ---- insert object revision ----
            cur.execute(
                "INSERT INTO object_revisions "
                "(object_type, object_id, revision, meta_json, payload_json, integrity_ref) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (meta.object_type, meta.object_id, meta.revision,
                 meta_json, payload_json, meta.integrity_ref),
            )

            # ---- update head ----
            cur.execute(
                "INSERT INTO object_heads (object_type, object_id, current_revision) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(object_type, object_id) "
                "DO UPDATE SET current_revision=excluded.current_revision",
                (meta.object_type, meta.object_id, meta.revision),
            )

            # ---- sequence inside transaction (single source of truth) ----
            cur.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM event_envelopes")
            next_seq = cur.fetchone()[0]

            # ---- build event ----
            now = now_utc()
            event_id = self._new_event_id(meta)
            event_type = f"{meta.object_type}.{'created' if meta.revision == 1 else 'revised'}"
            payload_ref = f"sha256:{__import__('hashlib').sha256(canonical_json_dumps(payload).encode('utf-8')).hexdigest()}"

            event_integrity_fields = {
                "event_id": event_id,
                "event_type": event_type,
                "sequence": next_seq,
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

            cur.execute(
                "INSERT INTO event_envelopes "
                "(sequence, event_id, event_type, aggregate_ref, aggregate_revision, "
                "producer_organ, run_binding_id, task_run_id, correlation_id, "
                "causation_ref, occurred_at, recorded_at, payload_ref, integrity_ref) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    next_seq,
                    event_id, event_type,
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

        except sqlite3.IntegrityError as exc:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise LedgerWriteFailed(
                "SQLite integrity constraint violated during write",
                {"sqlite_error": str(exc)},
            ) from exc
        except FurinaContractError:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        except Exception as exc:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise LedgerWriteFailed(
                f"Unexpected error during ledger write: {type(exc).__name__}",
                {"error": str(exc)},
            ) from exc

    def write_objects_atomic(
        self,
        objects: list[tuple[CanonicalMeta, dict[str, Any], str, int]],
    ) -> None:
        """Write multiple objects in a single transaction.

        Each tuple is (meta, payload, caller_organ, expected_revision).
        If any write fails, all writes in this batch are rolled back.
        """
        if not objects:
            return

        try:
            cur = self.conn.cursor()
            cur.execute("BEGIN IMMEDIATE")

            for i, (meta, payload, caller_organ, expected_revision) in enumerate(objects):
                # Test-only fault injection: fail after N objects written
                if self._atomic_fail_after >= 0 and i >= self._atomic_fail_after:
                    raise LedgerWriteFailed(
                        f"test injection: atomic failure after {i} objects",
                        {"injected": True, "failed_at": i},
                    )

                check_owner(meta.object_type, caller_organ, meta.owner_organ)

                # Read current head
                cur.execute(
                    "SELECT current_revision FROM object_heads WHERE object_type=? AND object_id=?",
                    (meta.object_type, meta.object_id),
                )
                head_row = cur.fetchone()
                current_rev = head_row[0] if head_row else 0

                if expected_revision != current_rev:
                    raise RevisionConflict(
                        f"expected_revision={expected_revision} but current={current_rev} "
                        f"for {meta.object_type}:{meta.object_id}",
                        {"expected": expected_revision, "current": current_rev},
                    )

                if meta.revision != current_rev + 1:
                    raise RevisionConflict(
                        f"revision must be {current_rev + 1}, got {meta.revision}",
                        {"expected": current_rev + 1, "got": meta.revision},
                    )

                if current_rev == 0:
                    if meta.supersedes_ref is not None:
                        raise ContractInvalid(
                            "supersedes_ref must be None for initial creation",
                        )
                else:
                    expected_supersedes = f"{meta.object_type}:{meta.object_id}:rev{current_rev}"
                    if meta.supersedes_ref != expected_supersedes:
                        raise ContractInvalid(
                            f"supersedes_ref must be {expected_supersedes}",
                        )

                if current_rev > 0:
                    cur.execute(
                        "SELECT meta_json FROM object_revisions "
                        "WHERE object_type=? AND object_id=? AND revision=?",
                        (meta.object_type, meta.object_id, current_rev),
                    )
                    prev_row = cur.fetchone()
                    if prev_row is None:
                        raise LedgerWriteFailed(
                            f"Previous revision {current_rev} not found",
                        )
                    prev_meta = json.loads(prev_row[0])
                    new_meta = meta.to_dict()
                    for field in _STABLE_FIELDS:
                        if prev_meta.get(field) != new_meta.get(field):
                            raise BindingMismatch(
                                f"Stable field '{field}' changed between revisions",
                            )

                meta_fields = meta.meta_fields_for_integrity()
                expected_ref = compute_integrity_ref(meta_fields, payload)
                if meta.integrity_ref != expected_ref:
                    raise IntegrityCheckFailed(
                        "integrity_ref does not match computed hash",
                    )

                meta_json = canonical_json_dumps(meta.to_dict())
                payload_json = canonical_json_dumps(payload)

                cur.execute(
                    "INSERT INTO object_revisions "
                    "(object_type, object_id, revision, meta_json, payload_json, integrity_ref) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (meta.object_type, meta.object_id, meta.revision,
                     meta_json, payload_json, meta.integrity_ref),
                )
                cur.execute(
                    "INSERT INTO object_heads (object_type, object_id, current_revision) "
                    "VALUES (?, ?, ?) "
                    "ON CONFLICT(object_type, object_id) "
                    "DO UPDATE SET current_revision=excluded.current_revision",
                    (meta.object_type, meta.object_id, meta.revision),
                )

                # Event
                cur.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM event_envelopes")
                next_seq = cur.fetchone()[0]
                now = now_utc()
                event_id = f"evt:{meta.object_type}:{meta.object_id}:rev{meta.revision}:{now.timestamp()}"
                event_type = f"{meta.object_type}.{'created' if meta.revision == 1 else 'revised'}"
                payload_ref = f"sha256:{__import__('hashlib').sha256(canonical_json_dumps(payload).encode('utf-8')).hexdigest()}"
                event_integrity_fields = {
                    "event_id": event_id, "event_type": event_type, "sequence": next_seq,
                    "aggregate_ref": f"{meta.object_type}:{meta.object_id}",
                    "aggregate_revision": meta.revision, "producer_organ": meta.owner_organ,
                    "run_binding_id": meta.run_binding_id, "task_run_id": meta.task_run_id,
                    "correlation_id": meta.correlation_id, "causation_ref": meta.causation_ref,
                    "occurred_at": meta.created_at.isoformat(), "recorded_at": now.isoformat(),
                    "payload_ref": payload_ref,
                }
                event_integrity = compute_integrity_ref(event_integrity_fields, {})
                cur.execute(
                    "INSERT INTO event_envelopes "
                    "(sequence, event_id, event_type, aggregate_ref, aggregate_revision, "
                    "producer_organ, run_binding_id, task_run_id, correlation_id, "
                    "causation_ref, occurred_at, recorded_at, payload_ref, integrity_ref) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (next_seq, event_id, event_type,
                     f"{meta.object_type}:{meta.object_id}", meta.revision,
                     meta.owner_organ, meta.run_binding_id, meta.task_run_id,
                     meta.correlation_id, meta.causation_ref,
                     meta.created_at.isoformat(), now.isoformat(),
                     payload_ref, event_integrity),
                )

            cur.execute("COMMIT")

        except sqlite3.IntegrityError as exc:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise LedgerWriteFailed(
                "SQLite integrity constraint violated during atomic write",
                {"sqlite_error": str(exc)},
            ) from exc
        except FurinaContractError:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        except Exception as exc:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise LedgerWriteFailed(
                f"Unexpected error during atomic write: {type(exc).__name__}",
                {"error": str(exc)},
            ) from exc

    # --------------------------------------------------------------- events

    def get_events(self, run_binding_id: str) -> list[dict[str, Any]]:
        """Internal diagnostic: raw event read without integrity verification.

        NOT for use by ContinuityView or formal business paths.
        Use get_verified_events() for all integrity-checked reads.
        """
        cur = self.conn.execute(
            "SELECT * FROM event_envelopes WHERE run_binding_id=? ORDER BY sequence",
            (run_binding_id,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_verified_events(self, run_binding_id: str) -> list[dict[str, Any]]:
        """Read events for a RunBinding and recompute integrity for each."""
        events = self.get_events(run_binding_id)
        for evt in events:
            integrity_fields = {
                "event_id": evt["event_id"],
                "event_type": evt["event_type"],
                "sequence": evt["sequence"],
                "aggregate_ref": evt["aggregate_ref"],
                "aggregate_revision": evt["aggregate_revision"],
                "producer_organ": evt["producer_organ"],
                "run_binding_id": evt["run_binding_id"],
                "task_run_id": evt["task_run_id"],
                "correlation_id": evt["correlation_id"],
                "causation_ref": evt["causation_ref"],
                "occurred_at": evt["occurred_at"],
                "recorded_at": evt["recorded_at"],
                "payload_ref": evt["payload_ref"],
            }
            expected_ref = compute_integrity_ref(integrity_fields, {})
            if evt["integrity_ref"] != expected_ref:
                raise IntegrityCheckFailed(
                    "Event integrity check failed",
                    {
                        "event_id": evt["event_id"],
                        "stored": evt["integrity_ref"],
                        "computed": expected_ref,
                    },
                )
        return events

    def get_last_sequence(self, run_binding_id: str | None = None) -> int:
        if run_binding_id is not None:
            cur = self.conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM event_envelopes WHERE run_binding_id=?",
                (run_binding_id,),
            )
        else:
            cur = self.conn.execute("SELECT COALESCE(MAX(sequence), 0) FROM event_envelopes")
        return cur.fetchone()[0]
