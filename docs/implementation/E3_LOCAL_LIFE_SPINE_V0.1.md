# E3 本地持续生命脊柱

**任务编号:** E3
**状态:** E3 实施证据，待 PR 审查
**日期:** 2026-07-11

---

## 1. 模块结构

```
src/furina_code/
├─ contracts/
│  ├─ __init__.py
│  ├─ errors.py      — FurinaContractError + 7 structured error types
│  ├─ meta.py         — CanonicalMeta frozen dataclass + integrity computation
│  ├─ objects.py      — RunBinding, TaskDossier, TaskRun, Checkpoint + OWNER enforcement
│  └─ states.py       — Phase, Disposition enums + ALLOWED_TRANSITIONS table
├─ ledger/
│  ├─ __init__.py
│  └─ sqlite.py       — Ledger class: append-only SQLite with atomic writes
├─ continuity/
│  ├─ __init__.py
│  └─ rebuild.py      — ContinuityView + rebuild_continuity()

tests/e3/
├─ test_owner_and_revision.py       — 5 tests
├─ test_task_run_state_machine.py   — 9 tests
├─ test_object_event_atomicity.py   — 2 tests
├─ test_integrity_detection.py      — 2 tests
├─ test_restart_continuity.py       — 1 test
├─ test_runtime_git_boundary.py     — 1 test
└─ test_normal_life_spine.py        — 1 test (full 5-event scenario)
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

---

## 5. TaskRun Structural State Constraints

9 phases: intake → observe → deliberate → authorize → act → reconcile → verify → adjudicate → terminal

7 dispositions: active, waiting_user, external_blocked, paused, recovery_review, manual_intervention, terminal

Implemented rejections:
- intake → act (skip)
- act → verify (skip reconcile)
- verify → terminal (skip adjudicate)
- paused disposition cannot advance phase
- manual_intervention cannot auto-return to active

---

## 6. Object-Event Transaction Order

```
BEGIN IMMEDIATE
→ Read current head
→ Validate expected_revision
→ Validate OWNER / binding / schema
→ Insert object revision
→ Update object_heads
→ Insert EventEnvelope
→ COMMIT
```

Any failure → ROLLBACK. No partial writes possible.

---

## 7. Integrity Algorithm

- Canonical JSON: UTF-8, sort_keys=True, stable separators, no NaN/Infinity
- Hash: sha256 over (CanonicalMeta fields minus integrity_ref + payload)
- Format: sha256:<64 hex chars>
- Read-time verification: recompute and compare

---

## 8. ContinuityView Rebuild

Based on:
- Validated events from ledger
- Latest TaskRun revision
- Latest Checkpoint
- Event sequence ordering (not timestamp)

---

## 9. Test Results

```
34/34 passed (21 E3 + 13 E2 baseline)
pip check: No broken requirements found
```

---

## 10. Proven Capabilities

- Formal objects with unique OWNER
- Non-OWNER write rejection
- Revision conflict rejection
- Immutable history
- Object-event atomic transaction
- TaskRun structural state transition constraints
- Integrity tamper detection
- Restart continuity rebuild
- Runtime data git-ignored

---

## 11. Not Proven

- Real project observation
- External candidate bridge
- Gate authorization
- Controlled file write action
- Verification runner
- Completion verdict
- Recovery mechanism
- Experience candidate
- CLI business commands

---

## 12. Entering E4 Still Requires

- GitObservationPort implementation
- CandidateInputPort implementation
- ControlledActionPort implementation
- VerificationRunnerPort implementation
- Gate logic
- First real closed-loop scenario
