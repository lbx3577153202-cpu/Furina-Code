# ADR-0002: MiMo Integration Mode

**Date:** 2026-07-12
**Stage:** MC0
**Status:** Accepted

---

## 1. Decision

**Selected Mode: A — Stable CLI Available**

```
MIMO_CODE_CLI_AVAILABLE
```

---

## 2. Context

Furina Code needs to determine how MiMo Code can serve as an external backend for the read-only inspection loop. The investigation tested the real MiMo Code CLI, API, and file bridge compatibility.

---

## 3. Evidence

### CLI Availability
- `mimo run -- "message"` executes non-interactively
- Produces stable exit code (0 on success)
- Supports session management (`-c`, `-s`, `--fork`)
- Supports working directory override (via `Set-Location` or `--dir`)
- Supports model selection (`-m provider/model`)
- Supports trust mode (`--trust`) and pure mode (`--pure`)

### Probe Test
- Read a file and returned exact expected text: `MIMO_PROBE_OK`
- No files modified, no extra files created
- Duration: ~10 seconds

### API Availability
- Xiaomi API credential configured
- Models available: mimo-auto, mimo-v2.5, mimo-v2.5-pro, mimo-v2.5-pro-ultraspeed
- Direct API access not tested (CLI used instead)

---

## 4. Rejected Modes

### Mode B: API Available
- Not rejected, but CLI is preferred because:
  - CLI already provides file access and tool execution
  - CLI handles authentication automatically
  - CLI provides session management
  - API would require separate authentication setup

### Mode C: Manual File Bridge Only
- Rejected because CLI provides non-interactive execution
- Manual bridge is unnecessary when CLI can run autonomously

### Mode D: Connection Blocked
- Rejected — CLI works and API is accessible

---

## 5. Furina Code / MiMo Responsibility Boundary

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

## 6. Next Stage Scope

Design and implement:

1. **BackendPort** interface for MiMo Code CLI
2. **MiMoCodeCLIAdapter** implementing BackendPort
3. **Output template** for reliable JSON candidate generation
4. **Timeout wrapper** for process management
5. **Working directory override** for correct repository root
6. **Output parser** to extract JSON from potential extra text

---

## 7. Implementation Requirements

### For E5 (BackendPort + MiMoCodeCLIAdapter):
- Adapter calls `mimo run -- "<prompt>" -m "mimo/mimo-auto" --trust --pure`
- Working directory set to repository root (from `observe_git`)
- Timeout via process kill after configurable seconds
- Output parsing: extract JSON from stdout, handling potential extra text
- Error handling: non-zero exit code, stderr capture
- Session: new session per task (no `--continue`)

### For File Bridge:
- context_packet.json written by Furina Code
- MiMo Code reads context_packet.json and generates candidate.json
- Candidate must include exact context_envelope_ref, context_digest, backend_profile_ref
- requested_actions must be empty

---

## 8. Constraints

- MiMo is an external backend, not part of Furina Code core
- MiMo sessions are not long-term memory
- MiMo cannot write to the real repository
- Furina Code owns all Gates and completion decisions
- No FurinaOS-agent-spike code imported
- No old session/prompt/memory migrated

---

## 9. Things Not to Implement

- Direct MiMo API adapter (use CLI instead)
- MiMo session as persistent memory
- MiMo file write permissions
- MiMo Gateway or router
- MiMo plugin system integration
- MiMo MCP server integration
