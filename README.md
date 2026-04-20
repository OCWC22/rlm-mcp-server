# rlm-repl-mcp

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

State pickles live at `$RLM_STATE_DIR` (default `~/.cache/rlm-mcp/`).

## New in v0.2.0 (Phase 1)

- `rlm_exec` now provides a persistent Python execution environment keyed by
  `session_id` and saves pickleable globals between calls.
- `rlm_exec` injects `context`, `content`, `buffers`, and helpers:
  `peek`, `grep`, `chunk_indices`, `write_chunks`, `add_buffer`.
- `rlm_exec` also injects `llm_query(prompt, max_tokens=2000)` so recursive
  sub-queries can be triggered directly from executed Python code.
- `rlm_sub_query` attempts MCP Sampling first (`ctx.session.create_message`). If
  sampling is unavailable in the connected client/session, it falls back to a
  callback loop and returns:
  `{"need_subquery": true, "prompt": "...", "request_id": "..."}`.
- In fallback mode, call `rlm_sub_query_result(request_id, result)` and then
  re-run the original call (or re-run `rlm_exec` block) to consume the result.
- `_trace(tool, input, output)` is currently a no-op seam for Phase 2 JSONL
  trace collection.

### Client compatibility note

Claude Desktop and Claude Code typically support MCP Sampling and use the
primary path. Codex CLI and Gemini CLI can hit callback fallback behavior,
which is supported via `rlm_sub_query_result`.

### Security note (`rlm_exec`)

`rlm_exec` executes arbitrary Python code and persists state via pickle. This
is **not sandboxed** and should only be used with trusted code and trusted
local sessions.

## Install

### Option 1 — Smithery (recommended, once published)

```bash
smithery install rlm-repl-mcp
```

### Option 2 — pipx / uv from GitHub

```bash
pipx install git+https://github.com/OCWC22/rlm-repl-mcp
# or
uv tool install git+https://github.com/OCWC22/rlm-repl-mcp

# Then point any MCP client at the `rlm-mcp` command.
```

### Option 3 — clone & run (zero deps beyond Python 3.10+)

```bash
git clone https://github.com/OCWC22/rlm-repl-mcp
cd rlm-repl-mcp && chmod +x run_server.sh
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

Either the MCP (as above) OR the bundled skill + subagent at
[OCWC22/claude_code_RLM](https://github.com/Brainqub3/claude_code_RLM) — the
skill integrates a Haiku subagent for chunk-level extraction.

## Example usage (natural language, any client)

> *“Load `/Users/me/big-logs/app.log` into rlm and find every ERROR with a
> stack trace. Show me the first 10 with context.”*

The model will call `rlm_init` → `rlm_grep` → optionally `rlm_peek` for
context and return a summary without ever pasting the whole log into chat.

## Development

```bash
git clone https://github.com/OCWC22/rlm-repl-mcp
cd rlm-repl-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
rlm-mcp            # stdio MCP server
```

## License

MIT. See [LICENSE](LICENSE).
