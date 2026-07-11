# MC1 Backend Port and Sandbox Contract V0.1

**Date:** 2026-07-12
**Stage:** MC1.2
**Status:** Candidate — activates after merge

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

### 2.4 Dependency Boundary

- Adapter does NOT receive Ledger instance
- Adapter package must NOT import ledger module
- Adapter package must NOT import formal object factories (CandidateEnvelope, BackendProfile, etc.)
- Adapter constructor must NOT accept Ledger as parameter
- Adapter method signatures must NOT include Ledger
- Only orchestrator / I2-D may write Ledger and create CandidateEnvelope

---

## 3. MC1 Formal Objects (Non-Authoritative DTOs)

These are plain, immutable DTOs. They are NOT added to OWNER_MAP.

### 3.1 Probe DTOs

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
```

### 3.2 Invocation Request

```python
@dataclass(frozen=True)
class BackendInvocationRequest:
    run_binding_id: str
    invocation_id: str
    backend_session_ref: str
    backend_profile_ref: str
    context_ref: str
    context_digest: str
    instruction_text: str
    instruction_profile_ref: str
    config_ref: str
    sandbox_policy_ref: str
    request_digest: str
    model_ref: str | None
    timeout_seconds: int
    max_stdout_bytes: int
    max_stderr_bytes: int
    fresh_session: bool
    sandbox_path_ref: str  # relative or logical ref, not absolute
```

### 3.3 Invocation Plan

```python
@dataclass(frozen=True)
class BackendInvocationPlan:
    request: BackendInvocationRequest
    executable_args: tuple[str, ...]
    cwd_ref: str  # relative or logical ref, not absolute
    env_policy_ref: str  # reference to environment policy, not actual values
    env_key_allowlist: tuple[str, ...]  # key names only, no values
    credential_mode: str
    provider_state_policy_ref: str
```

Actual environment values are resolved only at the final step of process launch:

- Values are NOT serialized
- Values are NOT recorded in DTOs, logs, Ledger, or invocation summary
- Values are NOT included in command_args_digest or request_digest
- Values are NOT included in exception messages

### 3.4 Transport Result

```python
@dataclass(frozen=True)
class BackendTransportResult:
    invocation_id: str
    request_digest: str
    backend_session_ref: str
    provider_session_ref: str | None
    provider_ref: str
    executable_version: str
    started_at: str  # ISO 8601
    finished_at: str  # ISO 8601
    command_args_digest: str

    stdout_ref: str | None  # relative ref to stdout.bin
    stdout_digest: str | None
    stdout_bytes: int
    stdout_truncated: bool

    stderr_ref: str | None  # relative ref to stderr.bin
    stderr_digest: str | None
    stderr_bytes: int
    stderr_truncated: bool

    candidate_ref: str | None  # relative ref to candidate.json
    candidate_digest: str | None

    manifest_before_ref: str | None  # relative ref to manifest_before.json
    manifest_before_digest: str | None
    manifest_after_ref: str | None  # relative ref to manifest_after.json
    manifest_after_digest: str | None

    transport_status: str  # see Section 10
    error_code: str | None
    error_detail: str | None
```

All `_ref` fields are relative to the external runtime root or logical URIs. They must NOT contain user-identity paths.

### 3.5 Sandbox Manifest (Single Observation Point)

```python
@dataclass(frozen=True)
class SandboxFileEntry:
    relative_path: str
    entry_type: str  # "file" | "symlink" | "junction_or_reparse" | "directory"
    size_bytes: int | None
    sha256: str | None
    is_symlink: bool
    is_junction_or_reparse_point: bool
    resolved_target: str | None  # must stay within sandbox

@dataclass(frozen=True)
class SandboxManifest:
    invocation_id: str
    observation_point: str  # "before" | "after"
    sandbox_path_ref: str  # relative ref, not absolute
    cwd_resolved_ref: str  # relative ref, not absolute
    entries: tuple[SandboxFileEntry, ...]
    manifest_digest: str  # canonical SHA-256 of sorted entries
```

Each manifest captures ONE observation point. Two separate instances are created:

```
manifest_before.json  (observation_point = "before")
manifest_after.json   (observation_point = "after")
```

Before/after diff is computed by Furina Code. Output:

```
added: [...]
deleted: [...]
content_changed: [...]
type_changed: [...]
link_target_changed: [...]
```

Each digest covers only its observation point's canonical manifest.

---

## 4. BackendPort Lifecycle

Minimum protocol covering all adapter types:

```
probe → prepare → invoke → collect → strict_validate → accepted | failed | ambiguous
```

### 4.1 FileBackend Mapping

| Phase | FileBackend |
|---|---|
| probe | No external executable dependency. Must probe: runtime root valid and outside repo, request directory creatable, context packet writable, candidate path valid, candidate file readable and not symlink. Result: available, unavailable, or awaiting_external |
| prepare | Generate Context Packet in runtime directory |
| invoke | No-op — await external candidate file |
| collect | Read candidate file from specified path |
| strict_validate | E4 candidate validator (exact JSON, schema, digest binding) |

FileBackend probe results:
- `available`: runtime root valid, directories creatable, context writable
- `unavailable`: runtime root invalid, inside repo, or write failure
- `awaiting_external`: runtime valid but no candidate file yet

### 4.2 MiMoCodeCLIAdapter Mapping

| Phase | MiMoCodeCLIAdapter |
|---|---|
| probe | Confirm executable, version, flags, models; probe provider state isolation |
| prepare | Create sandbox outside repository; write instruction + context packet |
| invoke | Run `mimo run -- "<prompt>"` with new session, cwd=sandbox |
| collect | Stream-bounded capture of stdout/stderr; save stdout.bin |
| strict_validate | stdout.bin must be exact JSON matching candidate schema |

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

### 5.2 Candidate Source Rule

Fixed flow:

```
MiMo stdout
→ save stdout.bin (raw transport evidence)
→ bounded capture
→ strict UTF-8 decode
→ parse entire output as single JSON object
→ existing Candidate contract validation
→ Furina Code writes canonical candidate.json
```

明确:

- MiMo does NOT directly write candidate.json
- stdout.bin is the raw transport evidence
- candidate.json is the Furina Code canonical copy generated after validation

### 5.3 Rejected Outputs

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

### 5.4 Heuristic Extraction Prohibition

The adapter must NOT implement:

```python
# PROHIBITED
json_match = re.search(r'\{.*\}', output, re.DOTALL)
```

The output is either valid JSON or it is a protocol error. No middle ground in MC1.

### 5.5 Future Correction

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

### 6.3 Session Rules

Every new invocation MUST use:
- New invocation_id
- New backend_session_ref
- New MiMo provider session (no `-c`, no `-s` with existing ID)

Provider session reuse is NEVER allowed under any circumstances.

What CAN be reused:
- `succeeded` + immutable `BackendTransportResult` (not the MiMo session, but the transport evidence)

### 6.4 Prohibited Session Practices

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
| Before/after manifest | two separate manifest objects for invocation evidence |

### 7.3 Manifest Requirements

Each file entry records:

```
relative_path
entry_type (file | symlink | junction_or_reparse | directory)
size_bytes
sha256
is_symlink
is_junction_or_reparse_point
resolved_target
```

All resolved targets must remain within sandbox.

Two manifests are generated independently. Furina Code computes diff:
added, deleted, content_changed, type_changed, link_target_changed.

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

Strategy: explicit key allowlist only. No actual values stored in DTOs.

```python
env_key_allowlist: ("HOME", "PATH", "TMPDIR", ...)
```

Actual values resolved only at process launch time:
- NOT serialized into DTOs
- NOT recorded in logs, Ledger, or invocation summary
- NOT included in command_args_digest or request_digest
- NOT included in exception messages

Must NOT pass raw `HOME` or `USERPROFILE` directly as safe environment.

Must distinguish:
- credential state
- config state
- session/database state
- trusted workspace state
- default working directory

MC1 implementation must separately probe whether the following can be isolated:
- config root
- data/session root
- workspace trust state
- credential source

If isolation is unavailable while preserving authentication:

```
MiMoCodeCLIAdapter automated invocation: BLOCKED
FileBackend: AVAILABLE
```

Explicit cwd does NOT substitute for user-level state isolation proof.

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

stdout and stderr must be stream-bounded captured.

If either stream exceeds hard limit:
- Terminate entire process tree
- status = `output_too_large`
- Record exceeded stream
- Save truncated evidence
- Prohibit further candidate parsing

### 8.4 Process Tree Termination

On timeout:
- Kill the entire child process tree
- Do NOT assume no side effects
- Do NOT automatically reuse the same session
- Record timeout in TransportResult

---

## 9. Idempotency and Replay

### 9.1 Request Digest

At minimum, the request digest covers (NO credential values):

```
backend_profile_ref
context_ref
context_digest
instruction_profile_ref
config_ref
sandbox_policy_ref
model/config ref
timeout
output size limits
fresh-session policy
```

`command_args_digest` and `request_digest` must NOT contain API key, token, cookie, or other credential values.

### 9.2 Replay Rules

| Scenario | Allowed |
|---|---|
| Same request digest + succeeded immutable result | Can reuse transport evidence |
| Same request digest + timeout | Must NOT silently replay |
| Same request digest + ambiguous | Must NOT silently replay |
| Any new call | New invocation_id + new backend_session_ref |

### 9.3 Prohibited

- Continue old MiMo session
- Reuse provider session after timeout
- Guess session ownership
- Reuse provider session under any circumstances

---

## 10. TransportResult Status Collection (14 statuses)

All retry columns renamed to `upper_layer_retry_eligible`.

**Adapter NEVER auto-retries. All retries are decided by the upper-layer orchestrator.**

Any retry MUST create new invocation_id and new provider session.

| Status | upper_layer_retry_eligible | New invocation_id | Provider session | TaskRun suggestion | Allow completed |
|---|---|---|---|---|---|
| `succeeded` | no | no | new | N/A | candidate processing only |
| `awaiting_external` | N/A | no | N/A | external_blocked | no |
| `backend_unavailable` | yes | yes | new | deliberate/paused | no |
| `launch_failed` | yes | yes | new | deliberate/paused | no |
| `authentication_failed` | no | yes | new | deliberate/paused | no |
| `nonzero_exit` | yes | yes | new | deliberate/paused | no |
| `timeout` | controlled | yes | new | deliberate/paused | no |
| `cancelled` | yes | yes | new | deliberate/paused | no |
| `output_too_large` | yes | yes | new | deliberate/paused | no |
| `invalid_utf8` | yes | yes | new | deliberate/paused | no |
| `protocol_error` | yes | yes | new | deliberate/paused | no |
| `candidate_rejected` | controlled | yes | new | deliberate/paused | no |
| `sandbox_violation` | no | yes | new | deliberate/paused | no |
| `ambiguous` | no | yes | new | deliberate/paused | no |

`sandbox_violation` covers:
- Real repository access attempted
- Legacy repository access attempted
- Sandbox path escape
- Symlink/junction/reparse point escape
- Disallowed file changes
- Manifest inconsistency

Adapter NEVER auto-retries on sandbox_violation.

For `authentication_failed`, `sandbox_violation`, `ambiguous`: default is `upper_layer_retry_eligible = no`. Retry only after user fixes auth, policy, or environment.

### 10.1 TaskRun Mapping

Adapter returns suggestions only. Adapter does NOT transition TaskRun.

Suggested mappings:
- `authentication_failed` → phase: deliberate, disposition: paused, open_request: "backend authentication required"
- All other failures → phase: deliberate, disposition: paused

### 10.2 Completion Semantics

`transport_status == succeeded` ONLY allows entry to candidate processing. It does NOT imply task completion.

Full completion chain required:

```
Transport succeeded
→ exact JSON validation
→ CandidateEnvelope
→ VerificationPlan
→ EvidenceEnvelope
→ VerificationVerdict
→ required Gates (G0/G1/G2/G4/G6/G7)
→ CompletionVerdict
```

### 10.3 Minimum Rules

- Authentication failure: no automatic retry
- Protocol error: no silent sanitization in MC1
- Timeout: must not assume no side effects; must not reuse session
- Sandbox violation: no automatic retry
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
| Adapter does not receive Ledger instance | structural: no Ledger import |
| backend/adapters import ledger module | fail at import time |
| backend/adapters import CandidateEnvelope factory | fail at import time |
| backend/adapters import BackendProfile factory | fail at import time |
| Adapter constructor receives Ledger | type error |
| Adapter method parameter contains Ledger | type error |
| Transport DTO contains env value field | structurally absent |
| Transport DTO contains absolute user path | structurally absent |
| Real repository as cwd rejected | sandbox_violation |
| Runtime inside repository rejected | sandbox_violation |
| Legacy repository path rejected | sandbox_violation |
| Symlink/junction escape rejected | sandbox_violation |
| `-c` and `-s` rejected | not used |
| `--dangerously-skip-permissions` rejected | not used |
| Unknown flags not hardcoded | BackendProbe detects |
| New session every invocation | verified |
| Provider session never reused | verified |
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
| Sandbox manifest captures changes | verified |
| stdout.bin saved as raw evidence | verified |
| candidate.json written by Furina Code | verified |
| Heuristic JSON extraction absent | verified |
| HOME/USERPROFILE not passed raw | verified |
| Provider state isolation probed | verified |
| Environment values not stored in DTOs | verified |
| FileBackend regression equivalence | all 270 tests pass |
| Real repository unchanged before/after | git status clean |
| Credentials not in logs, Ledger, or Git | verified |
