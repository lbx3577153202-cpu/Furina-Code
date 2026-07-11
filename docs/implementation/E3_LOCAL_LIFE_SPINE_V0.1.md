# E3 本地持续生命脊柱

**任务编号:** E3
**状态:** E3.2 实施证据，待 PR 审查
**日期:** 2026-07-11

---

## 1. 模块结构

```
src/furina_code/
├─ contracts/
│  ├─ __init__.py
│  ├─ errors.py      — FurinaContractError + 7 structured error types
│  ├─ meta.py         — CanonicalMeta + canonical_json_dumps + UTC validation + integrity
│  ├─ objects.py      — RunBinding, TaskDossier, TaskRun, Checkpoint + OWNER enforcement
│  └─ states.py       — Phase, Disposition enums + ALLOWED_TRANSITIONS + P4 back edges
├─ ledger/
│  ├─ __init__.py
│  └─ sqlite.py       — Ledger: transaction-protected writes, binding stability, verified events
├─ continuity/
│  ├─ __init__.py
│  └─ rebuild.py      — ContinuityView + rebuild_continuity() (verified events only)

tests/e3/
├─ test_owner_and_revision.py        — 5 tests
├─ test_task_run_state_machine.py    — 21 tests (original 9 + P4 back edges + recovery_review rejection)
├─ test_object_event_atomicity.py    — 3 tests (event failure rollback, success, revision conflict)
├─ test_integrity_detection.py       — 2 tests
├─ test_restart_continuity.py        — 2 tests (rebuild + verified events check)
├─ test_runtime_git_boundary.py      — 1 test
├─ test_normal_life_spine.py         — 1 test
├─ test_binding_invariants.py        — 9 tests (NEW: stable identity enforcement)
├─ test_concurrent_revision.py       — 1 test (NEW: concurrent stale write)
├─ test_event_integrity.py           — 7 tests (NEW: event tamper detection)
└─ test_multi_binding_continuity.py  — 3 tests (NEW: multi-binding isolation)
```

---

## 2. SQLite Schema

4 tables:
- `schema_metadata` — stores schema version
- `object_revisions` — immutable revisions with PRIMARY KEY (object_type, object_id, revision) and UNIQUE integrity_ref
- `object_heads` — current revision per object
- `event_envelopes` — append-only with INTEGER PRIMARY KEY AUTOINCREMENT sequence and UNIQUE event_id

---

## 3. OWNER Mapping

| Object Type | OWNER |
|-------------|-------|
| RunBinding | I1-A |
| TaskDossier | I2-A |
| TaskRun | I2-D |
| Checkpoint | I1-C |

Three-way validation: declared owner_organ, caller_organ, and frozen OWNER_MAP must all match.

---

## 4. Revision Rules

- Create: expected_revision=0, new revision=1, supersedes_ref=null
- Revise: expected_revision=current, new revision=current+1, supersedes_ref=previous
- Revision conflict → REVISION_CONFLICT, no write occurs
- All checks occur inside BEGIN IMMEDIATE transaction (E3.1)

---

## 5. Binding Stability Invariants (E3.1)

The following fields are frozen across revisions:
- schema_version, object_type, object_id, owner_organ
- run_binding_id, task_id, task_run_id, project_ref

Any change to these fields on revision > 1 is rejected with BINDING_MISMATCH.
`object_type` and `owner_organ` drift may also be caught by check_owner as AUTHORITY_VIOLATION.

TaskRun.transition() now inherits identity from self.meta — callers cannot pass binding fields.

---

## 6. TaskRun Structural State Constraints

9 phases: intake → observe → deliberate → authorize → act → reconcile → verify → adjudicate → terminal

7 dispositions: active, waiting_user, external_blocked, paused, recovery_review, manual_intervention, terminal

Implemented rejections:
- intake → act (skip)
- act → verify (skip reconcile)
- verify → terminal (skip adjudicate)
- observe → authorize (skip deliberate)
- reconcile → act (backwards)
- act → deliberate (backwards)
- paused disposition cannot advance phase
- manual_intervention cannot auto-return to active

P4 back edges added (E3.1):
- deliberate → observe
- deliberate → verify
- authorize → deliberate
- reconcile → deliberate
- verify → deliberate
- adjudicate → deliberate

Recovery_review transitions: removed (E3 has no RecoveryVerdict; E6 will re-add).

---

## 7. Object-Event Transaction Order (E3.1)

```
BEGIN IMMEDIATE
→ Read current head (inside transaction)
→ Validate expected_revision (inside transaction)
→ Validate exact next revision
→ Validate supersedes_ref
→ Read previous revision and check binding stability (if revision > 1)
→ Validate integrity_ref
→ Canonical JSON serialization
→ Insert object revision
→ Update object_heads
→ Compute next sequence (SELECT MAX+1, inside transaction)
→ Build event with sequence in integrity
→ Insert EventEnvelope
→ COMMIT
```

Any failure → ROLLBACK. No partial writes possible.

---

## 8. Canonical JSON (E3.1)

Unified canonicalization function `canonical_json_dumps()`:
- UTF-8, sort_keys=True, ensure_ascii=False
- Compact separators: (",", ":")
- allow_nan=False: NaN/Infinity → CONTRACT_INVALID
- Non-serializable objects → CONTRACT_INVALID

Used for: object integrity, payload persistence, meta persistence, event payload_ref, event integrity.

---

## 9. UTC Time Constraints (E3.1)

CanonicalMeta validates:
- created_at is timezone-aware with UTC offset == 0
- recorded_at is timezone-aware with UTC offset == 0
- Schema/revision/classification/integrity format errors → ContractInvalid (not ValueError)

---

## 10. Event Integrity (E3.1)

EventEnvelope integrity covers:
- event_id, event_type, sequence, aggregate_ref, aggregate_revision
- producer_organ, run_binding_id, task_run_id
- correlation_id, causation_ref
- occurred_at, recorded_at, payload_ref

Sequence is assigned inside the transaction (SELECT MAX+1) to prevent duplicates.

`get_verified_events(run_binding_id)` recomputes integrity for every event on read.

---

## 11. ContinuityView Isolation (E3.1)

- Uses `get_verified_events()` (integrity-checked events only)
- `last_event_sequence` is scoped to the given `run_binding_id`
- Missing binding → BindingMismatch (fail-closed, no default fabrication)

---

## 12. Test Results

```
75/75 passed (62 E3 + 13 E2 baseline)
pip check: No broken requirements found
```

---

## 13. E3.1 Corrections Summary

Issues found during E3 initial review:
1. Revision checks were outside the transaction → moved inside BEGIN IMMEDIATE
2. No binding stability enforcement → 8 stable fields checked on revision > 1
3. TaskRun.transition() allowed callers to pass binding fields → now inherits from self.meta
4. Event sequence not in integrity → added to integrity computation
5. No verified event reading → added get_verified_events()
6. ContinuityView used global max sequence → now scoped to run_binding_id
7. CanonicalMeta raised ValueError → now raises ContractInvalid
8. No UTC validation → added timezone-aware + UTC offset check
9. No canonical JSON function → added canonical_json_dumps()
10. Missing P4 back edges → added 6 structural back edges
11. recovery_review transitions active → removed (E3 has no RecoveryVerdict)
12. Atomicity test used broad Exception → now uses specific LedgerWriteFailed

---

## 13b. E3.2 Corrections Summary

Issues found during E3.1 review:
1. `get_revision()` did not read/select the `revision` column → now selects all 6 columns and cross-checks column revision vs requested vs meta_json
2. `get_latest()` returned None when head > 0 but revision missing → now raises IntegrityCheckFailed (fail-closed)
3. `write_object()` had per-checkpoint manual rollback → unified try/except structure with `conn.in_transaction` guard
4. `canonical_json_dumps()` only caught ValueError → now catches both ValueError and TypeError
5. Event INSERT did not explicitly include `sequence` column → now uses explicit `(sequence, ...)` INSERT with same variable used for integrity
6. `get_events()` was used by formal paths → docstring marks it as internal diagnostic; ContinuityView uses `get_verified_events()` only

---

## 14. Proven Capabilities

- Formal objects with unique OWNER
- Non-OWNER write rejection
- Revision conflict rejection (inside transaction)
- Binding stability enforcement (8 frozen fields)
- TaskRun identity inheritance (transition cannot change binding)
- Concurrent stale write rejection (two-connection race test)
- Immutable history
- Object-event atomic transaction (event failure rollback tested)
- Canonical JSON (NaN/Infinity/non-serializable rejection)
- UTC time validation
- Event integrity verification (5 tamper scenarios)
- Multi-binding ContinuityView isolation
- Missing binding fail-closed
- P4 back edges (deliberate↔observe/verify, authorize/reconcile/verify/adjudicate→deliberate)
- recovery_review without RecoveryVerdict rejected
- Integrity tamper detection (object revision column, meta_json, head integrity)
- Revision column cross-check (requested vs column vs meta_json)
- Broken head fail-closed (get_latest raises, not returns None)
- Unified transaction rollback (conn.in_transaction guard)
- Canonical JSON catches ValueError and TypeError
- Event sequence explicit INSERT (single source of truth)
- Restart continuity rebuild
- Runtime data git-ignored

---

## 15. Not Proven

- Real project observation
- External candidate bridge
- Gate authorization
- Controlled file write action
- Verification runner
- Completion verdict
- Recovery mechanism (RecoveryVerdict)
- Experience candidate
- CLI business commands

---

## 16. Entering E4 Still Requires

- GitObservationPort implementation
- CandidateInputPort implementation
- ControlledActionPort implementation
- VerificationRunnerPort implementation
- Gate logic
- First real closed-loop scenario
