# rlm-mcp-server

> **Recursive Language Models over MCP** — stateful Python REPL + programmatic
> sub-LLM recursion for long-context workflows, exposed to any MCP client.
>
> - **Paper:** [*Recursive Language Models*](https://arxiv.org/abs/2512.24601) — Zhang, Kraska, Khattab (MIT CSAIL, 2026)
> - **Reference impl:** https://github.com/alexzhang13/rlm
> - **Install:** `pipx install git+https://github.com/OCWC22/rlm-mcp-server`

Simple Recursive Language Model (RLM) style **persistent text REPL** exposed over
MCP. Free, local, no API keys. Load huge text files once, then let any MCP
client (Claude Desktop, Codex CLI, Gemini CLI, Claude Code, Cursor, etc.)
peek / grep / chunk / annotate them without re-paying context tokens per turn.

> Inspired by [Recursive Language Models](https://arxiv.org/abs/2512.24601)
> (Zhang, Kraska, Khattab — MIT CSAIL). The paper’s key idea: externalise long
> prompts into a REPL and let the LM call itself recursively over snippets.

## What it gives you

14 MCP tools:

| Tool | Purpose |
|---|---|
| `rlm_init(path, session_id?, max_bytes?)` | Load a text file into a named session |
| `rlm_status(session_id?)` | Char count, buffer count, etc. |
| `rlm_peek(start, end, session_id?)` | Slice the loaded text (≤ 50k chars) |
| `rlm_grep(pattern, ...)` | Regex search with snippets |
| `rlm_chunk_indices(size, overlap, ...)` | Plan chunk spans |
| `rlm_write_chunks(out_dir, ...)` | Materialise chunks as files |
| `rlm_add_buffer(text, ...)` | Append an intermediate note |
| `rlm_get_buffers` / `rlm_clear_buffers` | Read/clear notes |
| `rlm_exec(code, session_id?)` | Stateful Python `exec()` with persisted globals + helpers |
| `rlm_sub_query(prompt, max_tokens?, session_id?)` | Recursive LLM sub-call (Sampling first, callback fallback) |
| `rlm_sub_query_result(request_id, result, session_id?)` | Submit callback fallback answer for queued sub-queries |
| `rlm_reset(session_id?)` | Delete a session |
| `rlm_list_sessions()` | List all active sessions |

State pickles live at `$RLM_STATE_DIR` (fallback `$RLM_DATA_DIR`, default `~/.cache/rlm-mcp/`).

## What's new

See [CHANGELOG.md](./CHANGELOG.md) for release-by-release notes.

### Client compatibility note

Claude Desktop and Claude Code typically support MCP Sampling and use the
primary path. Codex CLI and Gemini CLI can hit callback fallback behavior,
which is supported via `rlm_sub_query_result`.

### Security note (`rlm_exec`)

`rlm_exec` executes arbitrary Python code and persists state via pickle. This
is **not sandboxed** and should only be used with trusted code and trusted
local sessions.

## Install

### Option 1 — Smithery (recommended)

```bash
smithery install rlm-mcp-server
```

### Option 2 — pipx / uv from GitHub

```bash
pipx install git+https://github.com/OCWC22/rlm-mcp-server
# or
uv tool install git+https://github.com/OCWC22/rlm-mcp-server

# Then point any MCP client at the `rlm-mcp` command.
```

### Option 3 — clone & run (zero deps beyond Python 3.10+)

```bash
git clone https://github.com/OCWC22/rlm-mcp-server
cd rlm-mcp-server && chmod +x run_server.sh
./run_server.sh       # first run creates .venv and installs mcp
```

## Register in MCP clients

Point the client at either the `rlm-mcp` entry point (after `pipx`/`uv`) or at
`run_server.sh` (clone mode).

### Claude Desktop — `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "rlm": { "command": "rlm-mcp" }
  }
}
```

### Codex CLI — `~/.codex/config.toml`

```toml
[mcp_servers.rlm]
command = "rlm-mcp"
```

### Gemini CLI — `~/.gemini/settings.json`

```json
{
  "mcpServers": {
    "rlm": { "command": "rlm-mcp" }
  }
}
```

### Claude Code

Use MCP registration for persistent multi-turn workflows. The bundled skill at
[OCWC22/claude_code_RLM](https://github.com/OCWC22/claude_code_RLM) remains a
useful fallback for one-shot sessions. See [Coexistence with the Claude Code skill](#coexistence-with-the-claude-code-skill).

## Coexistence with the Claude Code skill

The installed Claude Code skill at `~/.claude/skills/rlm/` is a **parallel**
integration path that shells out through `scripts/rlm_repl.py` and the
`rlm-subcall` subagent.

- MCP server path: `~/.claude/mcp-servers/rlm/` (14 tools + 3 prompts,
  client-agnostic, state persists across turns and clients).
- Skill path: `~/.claude/skills/rlm/` (Claude Code one-shot orchestration,
  separate pickle state).
- State is **not shared** between these paths because they write to different
  storage locations.

Prefer MCP for multi-turn analysis and cross-client portability. Prefer the
skill when MCP is unavailable and you need a one-shot Claude Code run.

Skill repo: https://github.com/OCWC22/claude_code_RLM

## Install all detected clients (fresh machine)

After cloning this repo on a machine with local MCP clients installed:

```bash
python3 scripts/install_clients.py
python3 scripts/verify_clients.py
```

- `install_clients.py` idempotently configures any detected client configs
  (Claude Desktop, Claude Code, Codex CLI, Gemini CLI) to use this checkout's
  `run_server.sh`.
- `verify_clients.py` runs MCP stdio handshake checks and expects 14 tools.
- `verify_end_to_end.py` runs per-client end-to-end checks (config, cache writeability,
  optional live CLI invocation, and trace assertions for `rlm_init` + `rlm_grep` + `rlm_exec`).

## Running end-to-end in each CLI

Known-good command shapes from investigation runs:

- Claude Code
  ```bash
  claude -p --permission-mode bypassPermissions "<prompt>"
  ```
  Uses user-scope MCP registration in `~/.claude.json`; no local `.mcp.json` required.

- Codex CLI
  ```bash
  codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox "<prompt>"
  ```
  Requires Codex subscription/auth.

- Gemini CLI (Node >= 20 required)
  ```bash
  PATH="/opt/homebrew/opt/node@20/bin:$PATH" gemini -p --approval-mode yolo --allowed-mcp-server-names rlm "<prompt>"
  ```
  Ensure `node --version` reports `v20` or newer before running.

- Claude Desktop (manual check)
  1. Open Claude Desktop → **Configure**
  2. Open **Servers**
  3. Verify server name `rlm` shows **Connected**
  4. Run a prompt that triggers `rlm_init` and confirm trace output appears in `~/.cache/rlm-mcp/traces`.

## Example usage (natural language, any client)

> *“Load `/Users/me/big-logs/app.log` into rlm and find every ERROR with a
> stack trace. Show me the first 10 with context.”*

The model will call `rlm_init` → `rlm_grep` → optionally `rlm_peek` for
context and return a summary without ever pasting the whole log into chat.

## Development

```bash
git clone https://github.com/OCWC22/rlm-mcp-server
cd rlm-mcp-server
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
rlm-mcp            # stdio MCP server
```

## License

MIT. See [LICENSE](LICENSE).

## Paper compatibility — what we support and don't

The RLM paper (arXiv:2512.24601, §2) defines **three invariants** distinguishing
a true RLM from a superficially similar strawman (Algorithm 2). This server
now meets **3/3** core invariants, with explicit non-goals called out below. Honest breakdown
below — graded from the paper author's point of view.

### ✅ Implemented faithfully

**Invariant #1 — symbolic handle to prompt P** (§2).
User prompt never enters root LM context. `rlm_init(path)` loads into a pickled
per-session dict; host model sees only metadata (char count, path, buffer
count) via `rlm_status`.
→ Maps to Algorithm 1 `state ← InitREPL(prompt=P)`.

**Invariant #2 — persistent Python REPL** (§2).
`rlm_exec(code)` runs arbitrary Python against a persistent globals dict
pickled across calls. Variables set in one call are readable in the next —
the exact pattern in paper Appendix C.1 examples.
→ Maps to Algorithm 1 `(state, stdout) ← REPL(state, code)`.

Injected in the exec environment:
- `context`, `content`, `buffers` (mutable state)
- `peek`, `grep`, `chunk_indices`, `write_chunks`, `add_buffer` (helpers)
- `llm_query(prompt, ...)` — see #3

**Metadata-only root history** (§2 footnote 1).
`rlm_peek` caps output at 50k chars; `rlm_status` returns constant-size metadata.
Trace log truncates any field >2000 chars. Matches `hist ← [Metadata(state)]`.

### ✅ Implemented faithfully (continued)

**Invariant #3 — symbolic recursion via `llm_query`** (§2).
`rlm_exec` is async and executes user code in a worker thread while bridging
sync `llm_query(...)` calls back to MCP Sampling on the main event loop via
`asyncio.run_coroutine_threadsafe(...)`. This preserves paper-style in-code
recursion loops (`for chunk in chunks: llm_query(...)`) without forcing
callback fallback purely because of sync/async mismatch.

When Sampling is unavailable in the connected client/session, recursion still
works through callback mode (`need_subquery` + `rlm_sub_query_result`) with
explicit host round-trips.

### ❌ Not implemented (explicit negative space)

- **`FINAL()` / `FINAL_VAR()` termination** (Algorithm 1). Paper terminates
  when root sets a `Final` variable. Ours relies on the host model stopping
  when satisfied. Matters for long-output tasks (§4.1 "long output tasks").
- **Constant-size history compaction** (§2 footnote 1). Paper trims each turn
  to *c* tokens for ≤ K/c root iterations. We leave root-history management
  to the host — Claude/Codex/Gemini each do their own.
- **Parallel async sub-calls** (§4 obs. 4, Appendix B). Paper flags async
  fan-out as the main latency fix. We still execute sub-calls one-at-a-time.
- **Batched `llm_query`** (§C.1b Qwen3-Coder prompt). Paper warns against
  excessive sub-calls; `richardwhiteii/rlm` ships `rlm_sub_query_batch`; we
  don't — single-call only for now.
- **Native post-trained RLM model** (§4 obs. 6, Appendix A). Paper trains
  RLM-Qwen3-8B (+28.3% avg). Not applicable — we're inference-time scaffold
  over whatever host model the client uses.
- **Deeper recursion** (§6 limitation). Paper and ours both depth-1. True
  RLM-inside-RLM would need nested MCP clients.
- **Sub-call sandboxing**. Paper's Fleet variant runs the REPL in Modal/Daytona.
  Ours is in-process on the user's machine with `pickle` + `exec`. Trust
  boundary: your local user. See SECURITY WARNING.

### Alex Zhang POV grade

| Paper §2 invariant | Us | richardwhiteii | Fleet-RLM | alexzhang13/rlm |
|---|---|---|---|---|
| #1 symbolic handle | ✅ | ✅ | ✅ | ✅ |
| #2 persistent REPL | ✅ | ⚠️ subprocess-per-call | ✅ (Daytona) | ✅ |
| #3 symbolic recursion | ✅ sampling bridge + callback fallback | ✅ | ✅ | ✅ |
| Free/local | ✅ no key | ⚠️ Ollama optional | ❌ Daytona | ❌ API keys |
| Paper-native eval | ⚠️ harness scaffold (S-NIAH + OOLONG loader) | ❌ | partial | ✅ |

Paper §B "negative results we tried" sanity check:
- "Models without sufficient coding capabilities struggle as RLMs" — host-model
  quality is a hard floor for us too; Haiku struggles with loop code for `rlm_exec`.
- "Thinking models with insufficient output tokens struggle" — we don't cap
  host-side thinking budget; that's the host's problem.
- "Distinguishing final answer from a thought is brittle" — we sidestep this
  by not having a `FINAL()` mechanism at all; the host handles termination.

## Use cases

Explore concrete end-to-end walkthroughs under [`examples/`](./examples/):

- [`examples/kernel-research.md`](./examples/kernel-research.md) — GPU kernel review flow using grep anchors, `rlm_exec` structural loops, and recursive hotspot interpretation.
- [`examples/paper-analysis.md`](./examples/paper-analysis.md) — long-paper deep dive with section-aware chunking and evidence-first synthesis.
- [`examples/codebase-triage.md`](./examples/codebase-triage.md) — grep-first architecture triage over a pre-concatenated code corpus.

These are realistic transcripts (with illustrative model outputs) meant to help host LMs pick the right tool sequence quickly.

### Cite the paper

```bibtex
@article{zhang2026rlm,
  title={Recursive Language Models},
  author={Zhang, Alex L. and Kraska, Tim and Khattab, Omar},
  journal={arXiv preprint arXiv:2512.24601},
  year={2026}
}
```
