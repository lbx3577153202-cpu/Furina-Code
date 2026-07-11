# MiMo Code Interface Reality Report V0.1

**Date:** 2026-07-12
**Stage:** MC0
**Repository:** E:\Furina-Code

---

## 1. MiMo Code Version

- **Product:** MiMo Code (mimocode)
- **Version:** 0.1.5
- **Package:** `@mimo-ai/cli` (npm)
- **Executable:** `C:\Users\35771\AppData\Roaming\npm\node_modules\@mimo-ai\cli\node_modules\@mimo-ai\mimocode-windows-x64\bin\mimo.exe`
- **CLI wrapper:** `C:\Users\35771\AppData\Roaming\npm\mimo.cmd`

---

## 2. Installation and Process Facts

- Installed via npm globally
- Running as process (PID 50532) during this session
- Process path: `mimocode-windows-x64\bin\mimo.exe`
- Credentials stored at: `~\.local\share\mimocode\auth.json`
- Config at: `~\.config\mimocode\mimocode.jsonc`
- Database at: `~\.local\share\mimocode\mimocode.db`
- Trusted workspaces: `E:\FurinaOS-m1-clean`, `E:\FurinaOS`, `C:\WINDOWS\System32`

---

## 3. CLI Capability Matrix

| Capability | Status | Evidence |
|---|---|---|
| Command line entry | Available | `mimo.cmd`, `mimo.exe` |
| `--help` | Works | Shows full help with all commands |
| `--version` | Works | Returns `0.1.5` |
| Non-interactive input | Available | `mimo run -- "message"` |
| stdin input | unknown | Not tested separately |
| Working directory | Shell-based | Must `Set-Location` before running; `--dir` flag exists but behavior unclear |
| Output to stdout | Available | Response printed to stdout |
| Output to file | unknown | No `--output` flag observed |
| Exit codes | Stable | Returns 0 on success |
| Session ID | Available | `ses_*` format, visible in `mimo session list` |
| New session | Default | Each `mimo run` creates new session |
| Resume session | Available | `-c` (continue last) or `-s <session_id>` |
| Fork session | Available | `--fork` flag |
| Cancel/timeout | External | Process can be killed; no built-in timeout flag |
| Tool permissions | Available | `--dangerously-skip-permissions` flag |
| Directory restriction | unknown | Not explicitly tested |
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
| API access | Available (Xiaomi API) |
| Provider | Xiaomi |
| User ID | 3172838200 |
| Visible models | mimo/mimo-auto, xiaomi/mimo-v2.5, xiaomi/mimo-v2.5-pro, xiaomi/mimo-v2.5-pro-ultraspeed |
| OpenAI compatible | unknown (not directly tested) |
| Anthropic compatible | unknown (not directly tested) |
| Non-streaming | Available (via CLI) |
| Streaming | unknown (CLI output appears buffered) |
| Structured output | `--format json` flag exists but behavior inconsistent |
| Tool calls | Supported (file read/write observed in probe) |
| Timeout semantics | No CLI flag; external process kill |
| Error shapes | Exit code + stderr |
| Request ID | unknown |
| Token usage | `mimo stats` command available |
| Credentials recorded | No (auth.json path noted, contents not read) |

---

## 6. Minimal Probe Results

| Item | Result |
|---|---|
| Performed | Yes |
| Location | `%TEMP%\furina-code-mc0-probe\` (outside repository) |
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
- Auth credentials stored at `~\.local\share\mimocode\auth.json` — not inspected
- Working directory default is `E:\FurinaOS-m1-clean` (old repo) — must be overridden
- `--dangerously-skip-permissions` exists but should not be used for production
- `--trust` flag skips workspace trust prompt

---

## 8. E4 File Bridge Compatibility

| Check | Assessment |
|---|---|
| Can MiMo read context_packet.json | Yes — file read tool observed working |
| Can MiMo produce candidate JSON | Yes — but may add explanatory text before/after |
| Can preserve context_envelope_ref | Yes — if instructed precisely |
| Can preserve context_digest | Yes — if instructed precisely |
| Can preserve backend_profile_ref | Yes — if instructed precisely |
| Can guarantee requested_actions=[] | Yes — if instructed precisely |
| Will MiMo add extra text before/after JSON | High risk — model tends to explain |
| Will MiMo use Markdown code fences | High risk — common model behavior |
| Is a dedicated output template needed | Yes — required for reliable parsing |

---

## 9. Unknown Items

- Exact `--dir` flag behavior for local run mode
- Whether `--format json` produces structured JSON events
- Whether `mimo serve` exposes a REST API compatible with OpenAI format
- Whether `mimo acp` implements Agent Client Protocol fully
- Exact timeout behavior when process is killed mid-execution
- Whether tool permissions can be restricted to read-only
- Whether MiMo can be configured to never write files
- Exact token usage per request

---

## 10. Risks

1. **Extra text in output**: MiMo may prepend/append explanations to JSON output
2. **Markdown code fences**: Model may wrap JSON in ```json fences
3. **Working directory default**: Defaults to old FurinaOS repo, must override
4. **No built-in timeout**: Must implement external timeout via process kill
5. **Tool permission model**: `--dangerously-skip-permissions` is all-or-nothing
6. **Session isolation**: Each `mimo run` creates a new session; no guaranteed clean slate
7. **Model behavior**: mimo-auto may vary across requests

---

## 11. Evidence Sources

- Direct CLI execution: `mimo --version`, `mimo --help`, `mimo run -- "message"`
- Process inspection: `Get-Process mimo`
- File system: npm package path, auth.json location, config files
- Provider check: `mimo providers list`, `mimo providers whoami`, `mimo models`
- Session list: `mimo session list` (48 sessions observed)
- Probe test: `mimo run -- "Read probe.txt"` in temp directory
