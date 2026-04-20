# rlm-repl-mcp

Simple Recursive Language Model (RLM) style **persistent text REPL** exposed over
MCP. Free, local, no API keys. Load huge text files once, then let any MCP
client (Claude Desktop, Codex CLI, Gemini CLI, Claude Code, Cursor, etc.)
peek / grep / chunk / annotate them without re-paying context tokens per turn.

> Inspired by [Recursive Language Models](https://arxiv.org/abs/2512.24601)
> (Zhang, Kraska, Khattab — MIT CSAIL). The paper’s key idea: externalise long
> prompts into a REPL and let the LM call itself recursively over snippets.

## What it gives you

11 MCP tools:

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
| `rlm_reset(session_id?)` | Delete a session |
| `rlm_list_sessions()` | List all active sessions |

State pickles live at `$RLM_STATE_DIR` (default `~/.cache/rlm-mcp/`).

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
