# ADR-0002: MiMo Integration Mode

**Date:** 2026-07-12
**Stage:** MC0
**Status:** Candidate — activates only after PR merge

---

## 1. Decision

**Selected Mode: A — Stable CLI Transport Candidate**

MiMo Code CLI is the selected integration transport candidate.

It is not yet approved to run against the real repository.
It is not yet proven read-only.
It is not yet proven directory-contained.

---

## 2. Context

Furina Code needs to determine how MiMo Code can serve as an external backend for the read-only inspection loop. The investigation tested the real MiMo Code CLI and performed a minimal file-based probe.

CLI provider credentials and visible models were observed.
Direct MiMo API access and protocol compatibility were not tested.

---

## 3. Evidence

### CLI Availability
- `mimo run -- "message"` executes non-interactively
- Produces stable exit code (0 on success)
- Supports session management (`-c`, `-s`, `--fork`)
- Supports model selection (`-m provider/model`)
- Supports trust mode (`--trust`) and pure mode (`--pure`)
- Working directory: shell-based; `--dir` flag exists but behavior unclear

### Probe Test
- Read a file and returned exact expected text: `MIMO_PROBE_OK`
- No files modified, no extra files created
- Duration: ~10 seconds
- Probe ran outside repository

### CLI Provider Observation
- Xiaomi API credential configured via CLI provider
- Models visible: mimo-auto, mimo-v2.5, mimo-v2.5-pro, mimo-v2.5-pro-ultraspeed
- Direct API access: **untested**
- Protocol compatibility: **untested**

---

## 4. Mode A Meaning

Mode A allows only:

- Stable non-interactive CLI entry exists
- Can produce stdout and exit codes
- Can create and manage sessions
- Can proceed to MC1 contract design

Mode A does NOT mean:

- Safe to automatically operate on real repository
- Production-grade directory isolation
- Read-only tool restriction
- Reliable pure JSON output

---

## 5. Alternative Modes Considered

### Mode B — Direct API Adapter
Deferred, not rejected.

Direct API access, base URL, protocol compatibility, error semantics, and credential handling were not tested in MC0.
It may be reconsidered after the CLI route is evaluated.

### Mode C — Manual File Bridge Only
Rejected because CLI provides non-interactive execution.
Manual bridge is unnecessary when CLI can run autonomously.

### Mode D — Connection Blocked
Rejected because the non-interactive MiMo Code CLI transport was successfully executed in an external temporary directory.

This decision does not rely on direct API availability.

---

## 6. Furina Code / MiMo Responsibility Boundary

| Responsibility | Owner |
|---|---|
| Task continuity | Furina Code |
| Project reality (Git, files) | Furina Code |
| Gate evaluation | Furina Code |
| Completion verdict | Furina Code |
| Read-only observation | Furina Code |
| Candidate generation | MiMo Code (via CLI) |
| Code analysis | MiMo Code (via CLI) |
| Repository write | Neither (read-only in E4) |
| Long-term memory | Furina Code (not MiMo session) |

---

## 7. MC1 Scope (Not E5)

MC1 will design:

1. **BackendPort** contract
2. **FileBackend** adaptation
3. **MiMoCodeCLIAdapter** contract and sandbox boundary design
4. **Output template** for reliable JSON candidate generation
5. **Timeout wrapper** for process management
6. **Output parser** to extract JSON from potential extra text

MC1 does NOT implement E5 features:
- Project-action Authorization Gate
- Controlled project write
- ActionReceipt
- RealityReconciliation

---

## 8. MC1 Sandbox Requirements

MC1 does NOT allow MiMo CLI to use real repository root as writable working directory.

First automated invocation must use:

```
runtime_root/
└─ mimo-invocation/
   ├─ context_packet.json
   ├─ instruction.txt
   └─ output/
```

This directory must be outside the real repository root.

Before the following capabilities are proven:
- Directory restriction
- Read-only permission
- Write prohibition
- Session isolation
- Structured output
- Timeout with process tree termination

MiMo CLI must NOT directly open the real repository.

When code context is needed, use:
- Controlled file copies
- Or detached disposable worktrees

Never use the real main working directory.

---

## 9. Legacy Contamination Isolation

MC1 must enforce:

- Do NOT inherit MiMo default working directory
- Do NOT continue old sessions
- Do NOT use `-c` or existing `-s` sessions
- Do NOT let MC1 probe access legacy FurinaOS repository
- Every invocation must create a new session
- cwd must be explicitly set to runtime/sandbox
- Context must only come from current ContextEnvelope

Legacy trusted workspaces may remain in MiMo local config, but Furina Code must not depend on or access them.

---

## 10. Command Design Not Frozen

The following are NOT yet verified and must NOT be hardcoded:

- `--dir` always works: **unverified**
- `--trust` always safe: **unverified**
- `--pure` provides required isolation: **unverified**
- `-m mimo/mimo-auto` is permanent model: **not fixed**
- Direct use of real repository root: **prohibited**

MC1 must detect actual flags and capabilities via BackendProbe at runtime.

Model selection via BackendProfile/config, not permanently hardcoded.

Unknown flag behavior must fail-closed.

`--dangerously-skip-permissions` permanently prohibited.

---

## 11. Constraints

- MiMo is an external backend, not part of Furina Code core
- MiMo sessions are not long-term memory
- MiMo cannot write to the real repository
- Furina Code owns all Gates and completion decisions
- No FurinaOS-agent-spike code imported
- No old session/prompt/memory migrated

---

## 12. Things Not to Implement

- Direct MiMo API adapter (use CLI instead)
- MiMo session as persistent memory
- MiMo file write permissions
- MiMo Gateway or router
- MiMo plugin system integration
- MiMo MCP server integration
- Any E5 features in MC1
