# MC1 Backend Port and Sandbox Contract V0.1

**Date:** 2026-07-12
**Stage:** MC1.0
**Status:** Design draft

---

## 1. Purpose

This document freezes the contract design for BackendPort, its adapters, the invocation sandbox, and the strict output protocol. It does not implement product code or invoke MiMo against the real repository.

---

## 2. Core Authority Freeze

### 2.1 Ownership

| Object | OWNER | Cannot Be Created By |
|---|---|---|
| BackendProfile | I2-B | BackendPort, Adapter |
| CandidateEnvelope | I2-D | BackendPort, Adapter |
| TaskRun | I2-D | BackendPort, Adapter |
| CompletionVerdict | I4-E | BackendPort, Adapter |

### 2.2 Authority Chain

```
I2-B  → creates BackendProfile from verified probe results
Adapter → executes non-authoritative transport
I2-D  → strictly validates transport result → creates CandidateEnvelope
I4    → independently verifies candidate → forms evidence → creates CompletionVerdict
```

### 2.3 Adapter Prohibitions

BackendPort and any Adapter must NOT:

- Write to Ledger
- Create or modify BackendProfile
- Create CandidateEnvelope
- Transition TaskRun
- Execute Gates
- Create CompletionVerdict
- Decide task completion

---

## 3. MC1 Formal Objects (Non-Authoritative DTOs)

These are plain, immutable DTOs. They are NOT added to OWNER_MAP.

```python
@dataclass(frozen=True)
class BackendProbeRequest:
    executable_path: str
    probe_timeout_seconds: int

@dataclass(frozen=True)
class BackendProbeResult:
    available: bool
    version: str | None
    executable_path: str
    supported_flags: tuple[str, ...]
    model_ids: tuple[str, ...]
    errors: tuple[str, ...]

@dataclass(frozen=True)
class BackendInvocationRequest:
    run_binding_id: str
    invocation_id: str
    backend_profile_ref: str
    context_ref: str
    context_digest: str
    instruction_text: str
    model_ref: str | None
    timeout_seconds: int
    max_stdout_bytes: int
    max_stderr_bytes: int
    fresh_session: bool
    sandbox_path: str

@dataclass(frozen=True)
class BackendInvocationPlan:
    request: BackendInvocationRequest
    executable_args: tuple[str, ...]
    cwd: str
    env_allowlist: dict[str, str]

@dataclass(frozen=True)
class BackendTransportResult:
    invocation_id: str
    transport_status: str  # see Section 10
    stdout_bytes: int | None
    stderr_bytes: int | None
    exit_code: int | None
    duration_ms: int
    provider_session_ref: str | None
    error_detail: str | None

@dataclass(frozen=True)
class SandboxManifest:
    invocation_id: str
    sandbox_path: str
    files_before: tuple[str, ...]
    files_after: tuple[str, ...]
    cwd_resolved: str
    symlinks_resolved: tuple[tuple[str, str], ...]
```

---

## 4. BackendPort Lifecycle

Minimum protocol covering all adapter types:

```
probe → prepare → invoke → collect → strict_validate → accepted | failed | ambiguous
```

### 4.1 FileBackend Mapping

| Phase | FileBackend |
|---|---|
| probe | Always available (no executable needed) |
| prepare | Generate Context Packet in runtime directory |
| invoke | No-op — await external candidate file |
| collect | Read candidate file from specified path |
| strict_validate | E4 candidate validator (exact JSON, schema, digest binding) |

### 4.2 MiMoCodeCLIAdapter Mapping

| Phase | MiMoCodeCLIAdapter |
|---|---|
| probe | Confirm executable, version, flags, models |
| prepare | Create sandbox outside repository; write instruction + context packet |
| invoke | Run `mimo run -- "<prompt>"` with new session, cwd=sandbox |
| collect | Capture bounded stdout/stderr; compute invocation summary |
| strict_validate | Output must be exact JSON matching candidate schema |

### 4.3 FileBackend Preservation

FileBackend must NOT be deleted or degraded because of MiMo integration.

FileBackend must:
- Continue to work when MiMo is not installed
- Maintain E4 prepare/finalize behavior exactly
- Keep all 270 existing tests passing
- Share the same BackendPort lifecycle phases

---

## 5. Strict Output Protocol

### 5.1 Exact JSON Only

The entire stdout output from the adapter MUST be a single valid JSON object.

### 5.2 Rejected Outputs

All of the following are protocol failures:

| Condition | Result |
|---|---|
| Explanatory text before JSON | `protocol_error` |
| Explanatory text after JSON | `protocol_error` |
| Markdown code fence (` ```json ```) | `protocol_error` |
| Multiple JSON objects | `protocol_error` |
| Heuristic extraction from long text | `protocol_error` — prohibited |
| Non-UTF-8 bytes | `invalid_utf8` |
| Output exceeds size limit | `output_too_large` |
| Missing required fields | `protocol_error` |
| Wrong field types | `protocol_error` |
| context_ref mismatch | `candidate_rejected` |
| context_digest mismatch | `candidate_rejected` |
| backend_profile_ref mismatch | `candidate_rejected` |
| requested_actions non-empty | `candidate_rejected` |

### 5.3 Heuristic Extraction Prohibition

The adapter must NOT implement:

```python
# PROHIBITED
json_match = re.search(r'\{.*\}', output, re.DOTALL)
```

The output is either valid JSON or it is a protocol error. No middle ground in MC1.

### 5.4 Future Correction

A controlled correction request may be designed in a future stage, but MC1 must not silently sanitize model output.

---

## 6. Session and Provider References

### 6.1 Local Backend Session Reference

Furina Code generates a stable local reference before each call:

```
backend_session_ref: <run-binding-id>:<invocation-id>
```

This is the authoritative session reference in CandidateEnvelope.

### 6.2 Provider Session Reference

If the CLI returns a session ID that can be reliably attributed to this invocation:

```
provider_session_ref: <mimo-session-id>
```

Otherwise:

```
provider_session_ref: null
```

### 6.3 Prohibited Session Practices

- Do NOT use `-c` (continue last session)
- Do NOT use `-s` with an existing session ID
- Do NOT use old sessions as long-term memory
- Do NOT guess which session belongs to the current invocation
- Every invocation creates a new session

---

## 7. Invocation Sandbox Contract

### 7.1 Layout

```
<external-runtime-root>/
└─ backend/
   └─ <run-binding-id>/
      └─ <invocation-id>/
         ├─ request/
         │  ├─ context_packet.json
         │  └─ instruction.txt
         ├─ output/
         │  ├─ stdout.bin
         │  ├─ stderr.bin
         │  └─ candidate.json
         └─ evidence/
            ├─ manifest_before.json
            ├─ manifest_after.json
            └─ invocation_summary.json
```

### 7.2 Hard Requirements

| Requirement | Rule |
|---|---|
| Outside repository root | sandbox must resolve outside canonical repo root |
| Explicit cwd | cwd must be set to sandbox directory |
| No default cwd | must not inherit MiMo default working directory |
| No legacy access | must not access old FurinaOS repository |
| No real main workspace | must not use real main working directory |
| Symlink/junction boundary | resolved paths must stay within sandbox |
| No repo runtime | runtime must not be placed inside repository |
| Before/after manifest | capture file list before and after invocation |

### 7.3 Manifest Schema

```json
{
  "invocation_id": "...",
  "sandbox_path": "...",
  "files_before": ["context_packet.json", "instruction.txt"],
  "files_after": ["context_packet.json", "instruction.txt", "stdout.bin", "stderr.bin"],
  "cwd_resolved": "...",
  "symlinks_resolved": [["link", "target"], ...]
}
```

---

## 8. Command and Process Safety

### 8.1 Execution Rules

| Rule | Value |
|---|---|
| shell | false |
| Argument passing | array, no string concatenation |
| Executable | confirmed by probe |
| Model | not permanently hardcoded |
| `--dangerously-skip-permissions` | permanently prohibited |
| `--trust` / `--pure` | not safety-guaranteed until proven |

### 8.2 Environment Variables

Strategy: explicit allowlist only.

```python
ENV_ALLOWLIST = {
    "HOME": "...",
    "PATH": "...",
    "TMPDIR": "...",
}
```

Must NOT read, copy, or record:

- API key
- auth.json contents
- cookie
- token
- full environment variables
- credential path user-identity portion

May record:

- credential_mode
- provider_ref
- config existence
- authentication failure category

### 8.3 Bounded I/O

| Resource | Limit |
|---|---|
| stdout | configurable, default 10 MB |
| stderr | configurable, default 1 MB |
| Total runtime | configurable timeout |

### 8.4 Process Tree Termination

On timeout:

- Kill the entire child process tree
- Do NOT assume no side effects
- Do NOT automatically reuse the same session
- Record timeout in TransportResult

---

## 9. Idempotency and Replay

### 9.1 Request Digest

At minimum, the request digest covers:

```
backend_profile_ref
context_ref
context_digest
instruction_profile
model/config ref
sandbox policy
timeout
output size limits
fresh-session policy
```

### 9.2 Replay Rules

| Scenario | Allowed |
|---|---|
| Same request digest + succeeded immutable result | Can reuse |
| Same request digest + timeout | Must NOT silently replay |
| Same request digest + ambiguous | Must NOT silently replay |
| Any new call | New invocation_id + new local backend_session_ref |

### 9.3 Prohibited

- Continue old MiMo session
- Reuse session after timeout
- Guess session ownership

---

## 10. TransportResult Status Collection

| Status | Retry | New invocation_id | Reuse session | TaskRun disposition | Allow completed |
|---|---|---|---|---|---|
| `succeeded` | no | no | yes | N/A | yes |
| `awaiting_external` | N/A | no | N/A | external_blocked | no |
| `backend_unavailable` | yes | yes | no | paused | no |
| `launch_failed` | yes | yes | no | paused | no |
| `authentication_failed` | no | yes | no | manual_intervention | no |
| `nonzero_exit` | yes | yes | no | paused | no |
| `timeout` | controlled | yes | no | paused | no |
| `cancelled` | yes | yes | no | paused | no |
| `output_too_large` | yes | yes | no | paused | no |
| `invalid_utf8` | yes | yes | no | paused | no |
| `protocol_error` | yes | yes | no | paused | no |
| `candidate_rejected` | controlled | yes | no | paused | no |
| `ambiguous` | no | yes | no | paused | no |

### 10.1 Minimum Rules

- Authentication failure: no automatic retry
- Protocol error: no silent sanitization in MC1
- Timeout: must not assume no side effects; must not reuse session
- Ambiguous: pause and preserve evidence; must not declare completion
- Any transport failure: Adapter must NOT directly modify TaskRun

---

## 11. FileBackend Equivalence

MC1 implementation must prove:

- Existing `inspect prepare` / `inspect finalize` behavior unchanged
- Existing Candidate schema unchanged
- All 270 existing tests preserved
- FileBackend and MiMoBackend share the neutral lifecycle
- FileBackend does not depend on MiMo installation
- FileBackend works when MiMo is unavailable

---

## 12. Future Implementation Acceptance Matrix

MC1 implementation must pass at minimum:

| Test | Expected |
|---|---|
| BackendPort unknown provider fail-closed | raises error |
| BackendProfile only created by I2-B | adapter write rejected |
| Adapter cannot write Ledger | Ledger write rejected |
| Real repository as cwd rejected | ContractInvalid |
| Runtime inside repository rejected | ContractInvalid |
| Legacy repository path rejected | ContractInvalid |
| Symlink/junction escape rejected | ContractInvalid |
| `-c` and `-s` rejected | Not used |
| `--dangerously-skip-permissions` rejected | Not used |
| Unknown flags not hardcoded | BackendProbe detects |
| New session every invocation | verified |
| stdout exceeds limit | output_too_large |
| stderr exceeds limit | truncated, recorded |
| Timeout enforced | process tree killed |
| Process tree terminated | no zombie processes |
| Non-zero exit recorded | nonzero_exit status |
| Invalid UTF-8 detected | invalid_utf8 status |
| Extra explanatory text rejected | protocol_error |
| Markdown code fence rejected | protocol_error |
| Multiple JSON objects rejected | protocol_error |
| context digest mismatch rejected | candidate_rejected |
| BackendProfile ref mismatch rejected | candidate_rejected |
| requested_actions non-empty rejected | candidate_rejected |
| FileBackend regression equivalence | all 270 tests pass |
| Real repository unchanged before/after | git status clean |
| Credentials not in logs, Ledger, or Git | verified |
