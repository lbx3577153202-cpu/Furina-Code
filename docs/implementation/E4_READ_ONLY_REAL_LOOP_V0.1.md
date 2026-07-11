# E4 Read-Only Real Loop

**任务编号:** E4
**状态:** E4 实施证据，待 PR 审查
**日期:** 2026-07-11

---

## 1. 模块结构

```
src/furina_code/
├─ __main__.py              — python -m furina_code entry point
├─ cli.py                   — argparse CLI with inspect prepare/finalize
├─ contracts/
│  ├─ objects.py            — 8 E4 objects + TaskRun.transition() extension
│  └─ __init__.py           — exports all 12 object types
├─ world/
│  ├─ __init__.py
│  ├─ git.py                — observe_git() with shell=False, GIT_OPTIONAL_LOCKS=0
│  ├─ observe.py            — observe_project() reads pyproject.toml, deps, CI
│  └─ snapshot.py           — create_project_snapshot()
├─ backend/
│  ├─ __init__.py
│  └─ candidate.py          — validate_candidate_file() + validate_candidate_content()
├─ readonly/
│  ├─ __init__.py
│  ├─ context.py            — create_context_envelope() + write_context_packet()
│  ├─ verification.py       — 10 verification steps + execute_verification()
│  └─ completion.py         — create_completion_verdict()

tests/e4/
├─ test_objects.py                  — 22 tests (new object types + owner enforcement)
├─ test_task_run_transition_extension.py — 9 tests (current_refs, open_requests, terminal_reason)
├─ test_git_observation.py          — 8 tests (real repo, clean, dirty, untracked, detached, locks)
├─ test_snapshot.py                 — 4 tests (real repo, deterministic sha, no pyproject)
├─ test_context_envelope.py         — 3 tests (creation, filtering, write)
├─ test_candidate_validation.py     — 13 tests (valid, missing, empty, large, JSON validation)
├─ test_verification.py             — 19 tests (all 10 steps pass/fail, execute_verification)
├─ test_completion.py               — 3 tests (pass, fail, user_effect)
├─ test_cli_prepare.py              — 5 tests (JSON output, ledger creation, invalid workspace)
├─ test_cli_finalize.py             — 6 tests (pass, missing ledger, missing candidate, terminal)
├─ test_full_loop.py                — 5 tests (pass, fail, unchanged workspace, event count, continuity)
├─ test_security.py                 — 5 tests (runtime, context no secrets, too large, non-JSON)
└─ test_idempotency.py              — 2 tests (replay conflict, restart)
```

---

## 2. New Formal Objects (8 types)

| Object Type | OWNER | Purpose |
|-------------|-------|---------|
| BackendProfile | I2-B | External backend identity and capabilities |
| ContextEnvelope | I2-C | Context packet sent to backend |
| CandidateEnvelope | I2-D | Candidate file received from backend |
| ProjectSnapshot | I3-A | Git/project observation snapshot |
| EvidenceEnvelope | I4-C | Verification evidence |
| VerificationPlan | I4-D | Verification step plan |
| VerificationVerdict | I4-D | Per-step verification result |
| CompletionVerdict | I4-E | Final task completion assessment |

All use CanonicalMeta, Ledger writes, EventEnvelope production, expected_revision, OWNER_MAP, binding stability, integrity verification.

---

## 3. TaskRun.transition() Extension

Optional kwargs: `current_refs`, `open_requests`, `terminal_reason`.
- `None` → preserve existing (backward compatible with E3)
- Explicit value → replace in new revision

---

## 4. Two-Stage CLI

### prepare
```
python -m furina_code inspect prepare --workspace <repo> --runtime-dir <dir>
```
Outputs JSON: run_binding_id, task_id, task_run_id, snapshot refs, context packet path, context digest.

### finalize
```
python -m furina_code inspect finalize --runtime-dir <dir> --run-binding-id <id> --candidate-file <file>
```
Outputs JSON: verdicts, completion outcome, evidence count.

---

## 5. TaskRun Path

- **prepare**: intake/active → observe/active → deliberate/active → deliberate/external_blocked
- **finalize**: deliberate/external_blocked → deliberate/active → verify/active → adjudicate/active → terminal/terminal

No authorize/act/reconcile in E4.

---

## 6. Verification Steps (10)

| Step | Compares |
|------|----------|
| snapshot_head_match | candidate.repository_head vs snapshot.head_sha |
| snapshot_branch_match | candidate.branch vs snapshot.branch |
| snapshot_clean_match | candidate.working_tree vs snapshot.is_clean |
| snapshot_file_count_match | tracked/untracked counts |
| snapshot_python_requires_match | python_requires string |
| snapshot_runtime_deps_match | runtime dependencies list |
| snapshot_dev_deps_match | dev dependencies list |
| snapshot_pytest_testpaths_match | pytest testpaths |
| snapshot_ci_config_match | CI config presence and sha256 |
| snapshot_blind_spots_match | blind spots list |

---

## 7. Security Boundaries

- subprocess shell=False, GIT_OPTIONAL_LOCKS=0
- Path traversal rejected
- No secrets in context packet
- Candidate size limit (10MB)
- requested_actions must be empty
- Non-JSON candidate rejected

---

## 8. Test Results

```
182/182 passed (78 E3 + 104 E4)
pip check: No broken requirements found
```

---

## 9. Real Repository Run

```
prepare: rb-f82ceeadb19a
finalize: outcome=completed
10/10 verification steps passed
workspace unchanged
```

---

## 10. Proven Capabilities

- Real Git and file observation (shell=False, GIT_OPTIONAL_LOCKS=0)
- Bounded external candidate ingestion (file-based, size limit, schema validation)
- Deterministic read-only verification (10 snapshot comparison steps)
- Evidence-backed read-only completion (EvidenceEnvelope + VerificationVerdict + CompletionVerdict)
- Restartable two-stage read-only flow (prepare → finalize with ledger persistence)
- Context packet disclosure filtering (no absolute paths, no secrets)
- TaskRun identity inheritance extended with current_refs/open_requests/terminal_reason

---

## 11. Not Proven

- Authorization Gate
- Project write
- Action receipt and reconciliation
- RecoveryVerdict
- Experience growth
- Full initial loop

---

## 12. Entering E5 Still Requires

- Gate logic implementation
- Controlled write action
- Action receipt
- Reality reconciliation
- RecoveryVerdict
- Experience candidate
