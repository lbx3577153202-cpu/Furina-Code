# MiMo Code Interface Reality Report V0.1

**Date:** 2026-07-12
**Stage:** MC0
**Repository:** [redacted]

---

## 1. MiMo Code Version

- **Product:** MiMo Code (mimocode)
- **Version:** 0.1.5
- **Package:** `@mimo-ai/cli` (npm global)
- **Executable:** installed via npm global, accessible via `mimo.cmd`
- **CLI wrapper:** npm global bin directory

---

## 2. Installation and Process Facts

- Installed via npm globally
- Running as process during MC0 investigation
- Process executable located in npm global node_modules
- Credentials stored at user-level config directory (auth.json)
- Config at user-level config directory (mimocode.jsonc)
- Database at user-level data directory (mimocode.db)
- Trusted workspaces list exists; legacy project paths currently trusted
- Default working directory points to legacy project (must be overridden)

---

## 3. CLI Capability Matrix

| Capability | Status | Evidence |
|---|---|---|
| Command line entry | Available | `mimo.cmd`, `mimo.exe` |
| `--help` | Works | Shows full help with all commands |
| `--version` | Works | Returns `0.1.5` |
| Non-interactive input | Available | `mimo run -- "message"` |
| stdin input | unknown | Not tested separately |
| Working directory | Shell-based | Must change directory before running; `--dir` flag exists but behavior unclear |
| Output to stdout | Available | Response printed to stdout |
| Output to file | unknown | No `--output` flag observed |
| Exit codes | Stable | Returns 0 on success |
| Session ID | Available | `ses_*` format, visible in `mimo session list` |
| New session | Default | Each `mimo run` creates new session |
| Resume session | Available | `-c` (continue last) or `-s <session_id>` |
| Fork session | Available | `--fork` flag |
| Cancel/timeout | External | Process can be killed; no built-in timeout flag; semantics unproven |
| Tool permissions | `--dangerously-skip-permissions` exists | Permanently prohibited for production use |
| Directory restriction | unknown | Not explicitly tested |
| Read-only tool restriction | unknown | Not tested |
| Extra files created | None observed | No side effects in probe tests |

---

## 4. Available Commands

```
mimo run [message..]     — non-interactive execution
mimo serve               — headless server mode
mimo acp                 — Agent Client Protocol server
mimo session list/delete — session management
mimo export [sessionID]  — export session as JSON
mimo import <file>       — import session from JSON
mimo providers list      — list configured providers
mimo providers whoami    — show current user
mimo models [provider]   — list available models
mimo upgrade             — upgrade mimocode
mimo plugin <module>     — install plugins
mimo mcp                 — MCP server management
mimo pr <number>         — fetch and checkout PR
mimo github              — GitHub agent management
mimo db                  — database tools
mimo stats               — token usage statistics
```

---

## 5. API Capability Matrix

| Capability | Status |
|---|---|
| API access | CLI provider credential observed; direct API untested |
| Provider | Xiaomi |
| Visible models | mimo/mimo-auto, xiaomi/mimo-v2.5, xiaomi/mimo-v2.5-pro, xiaomi/mimo-v2.5-pro-ultraspeed |
| OpenAI compatible | untested |
| Anthropic compatible | untested |
| Non-streaming | Available (via CLI) |
| Streaming | unknown |
| Structured output | `--format json` flag exists but reliability unproven |
| Tool calls | Supported (file read/write observed in probe) |
| Timeout semantics | No CLI flag; external process kill; semantics unproven |
| Error shapes | Exit code + stderr |
| Request ID | unknown |
| Token usage | `mimo stats` command available |

---

## 6. Minimal Probe Results

| Item | Result |
|---|---|
| Performed | Yes |
| Location | Temporary directory outside repository |
| Input | "Read the file probe.txt in the current directory and return its content" |
| Expected output | MIMO_PROBE_OK |
| Actual output | MIMO_PROBE_OK |
| Exit code | 0 |
| Files modified | None |
| Unexpected files | None |
| Duration | ~10 seconds |
| Secrets exposed | No |

---

## 7. Security and Privacy Observations

- Probe test ran outside repository, no repo files touched
- No API keys, tokens, or cookies were read or displayed
- Auth credentials exist but were not inspected
- Working directory default points to legacy project — must be overridden
- `--dangerously-skip-permissions` exists but permanently prohibited for production
- `--trust` flag exists; safety unproven
- `--pure` flag exists; isolation unproven

---

## 8. E4 File Bridge Compatibility

| Check | Assessment |
|---|---|
| Can MiMo read context_packet.json | Yes — file read tool observed working |
| Can MiMo produce candidate JSON | Possible — but may add extra text before/after |
| Can preserve context_envelope_ref | Possible — requires precise instruction |
| Can preserve context_digest | Possible — requires precise instruction |
| Can preserve backend_profile_ref | Possible — requires precise instruction |
| Can guarantee requested_actions=[] | Possible — requires precise instruction |
| Will MiMo add extra text before/after JSON | High risk — model tends to explain |
| Will MiMo use Markdown code fences | High risk — common model behavior |
| Is a dedicated output template needed | Yes — required for reliable parsing |
| Structured JSON reliability | unproven |

---

## 9. Unknown Items

- Exact `--dir` flag behavior for local run mode: **unknown**
- Whether `--format json` produces structured JSON events: **unproven**
- Whether `mimo serve` exposes a REST API: **untested**
- Whether `mimo acp` implements Agent Client Protocol fully: **untested**
- Exact timeout behavior when process is killed mid-execution: **unproven**
- Whether tool permissions can be restricted to read-only: **unknown**
- Whether MiMo can be configured to never write files: **unknown**
- Exact token usage per request: **unknown**
- Direct API access: **untested**
- OpenAI compatibility: **untested**
- Anthropic compatibility: **untested**

---

## 10. Risks

1. **Extra text in output**: MiMo may prepend/append explanations to JSON output
2. **Markdown code fences**: Model may wrap JSON in ```json fences
3. **Working directory default**: Defaults to legacy project, must override
4. **No built-in timeout**: Must implement external timeout via process kill
5. **Tool permission model**: No read-only restriction observed
6. **Session isolation**: Each `mimo run` creates a new session; clean slate unproven
7. **Model behavior**: mimo-auto may vary across requests
8. **Legacy workspace contamination**: Default cwd points to old project
9. **`--trust` and `--pure` safety**: Isolation properties unverified

---

## 11. Evidence Sources

- Direct CLI execution: `mimo --version`, `mimo --help`, `mimo run -- "message"`
- Process inspection: OS process list
- File system: npm package structure, config file locations
- Provider check: `mimo providers list`, `mimo providers whoami`, `mimo models`
- Session list: `mimo session list`
- Probe test: `mimo run -- "Read probe.txt"` in temp directory
