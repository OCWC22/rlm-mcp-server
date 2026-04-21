# AGENTS.md — rlm-mcp-server

> **Paper:** *Recursive Language Models* — Zhang, Kraska, Khattab (MIT CSAIL)
> https://arxiv.org/abs/2512.24601
> **Reference impl:** https://github.com/alexzhang13/rlm
> **This repo:** https://github.com/OCWC22/rlm-mcp-server

## Architecture at a glance

- Transport: MCP stdio via FastMCP (`mcp>=1.2`)
- State: pickled per-session dicts at `$RLM_STATE_DIR` (default `~/.cache/rlm-mcp`)
- Traces: JSONL per-session-per-day at `$RLM_TRACE_DIR` (default `$RLM_STATE_DIR/traces`)
- Tools (14):
  - `rlm_init` — load file content into a named session
  - `rlm_status` — inspect session metadata (chars/buffers/globals)
  - `rlm_peek` — slice context text by char range
  - `rlm_grep` — regex search with snippets
  - `rlm_chunk_indices` — compute chunk span plan
  - `rlm_write_chunks` — materialize chunk files
  - `rlm_add_buffer` — append note buffer entry
  - `rlm_get_buffers` — read all session buffers
  - `rlm_clear_buffers` — clear buffer list
  - `rlm_exec` — stateful Python `exec()` with persisted globals + helpers
  - `rlm_sub_query` — recursive LLM call (sampling-first, callback fallback)
  - `rlm_sub_query_result` — submit callback-mode subquery answers
  - `rlm_reset` — delete one session state file
  - `rlm_list_sessions` — enumerate stored sessions

## Paper mapping (arXiv:2512.24601)

- Invariant #1 symbolic handle → `rlm_init` + per-session persisted state
- Invariant #2 persistent REPL → `rlm_exec` with pickled globals
- Invariant #3 programmatic recursion → `rlm_sub_query` + in-exec `llm_query`
- Known gaps:
  - in-exec `llm_query` now uses a sync→async sampling bridge when sampling is available; callback fallback remains for unsupported clients
  - No scheduler/planner layer yet (tools expose primitives; orchestration is host-model driven)

## How to add a tool

1. Add a new function in `rlm_mcp.py` and decorate with `@mcp.tool()` and `@_traced("tool_name")`.
2. Keep `session_id` semantics consistent (`default` + `_safe_id`) and ensure return types are JSON-serializable.
3. Call `_trace(tool, input, output)` on success paths (decorator will trace uncaught errors).
4. Update README’s tool table and behavior notes.
5. Add/adjust unit-ish direct-call checks and stdio handshake expectations (tool count).

## Client compatibility

Canonical namespace layout:

- `rlm` (only entry) → `/Users/chen/.claude/mcp-servers/rlm/run_server.sh`
  - configured in **Claude Desktop**, **Claude Code**, **Codex CLI**, and **Gemini CLI**
- `rlm-richardwhiteii` is intentionally deregistered from client configs
  (the local repo can remain on disk as a dormant fallback checkout)

Maintainer scripts for self-healing parity:

- `python3 scripts/install_clients.py` — idempotently rewires detected clients
  to this checkout and refreshes timestamped config backups before writes.
- `python3 scripts/verify_clients.py` — runs stdio handshake smoke checks per
  detected client (expect 14 tools, including `rlm_exec` and `rlm_sub_query`).

Execution mode behavior remains:

- Claude Desktop / Claude Code: sampling path typically available (`ctx.session.create_message`)
- Codex CLI / Gemini CLI: may require callback mode (`need_subquery` + `rlm_sub_query_result`)

## Running locally

```bash
cd ~/.claude/mcp-servers/rlm

# Canonical branch state after consolidation:
# - main is the single source of truth
# - feat/full-rlm-v0.2 and feat/paper-fidelity-v0.3 are merged/deleted
git fetch origin
git checkout main
git pull --ff-only

python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Server
rlm-mcp

# Smoke test: handshake + list tools (expect 14, including rlm_sub_query)
.venv/bin/python - <<'PYCODE'
import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

async def main():
    params = StdioServerParameters(command='.venv/bin/python', args=['rlm_mcp.py'])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print(len(tools.tools), [t.name for t in tools.tools])

anyio.run(main)
PYCODE
```

## Tracing

- Enabled by default.
- Disable with `RLM_TRACE_DISABLE=1`.
- Trace files: `$RLM_TRACE_DIR/<session>-<YYYYMMDD>.jsonl`.
- Inspect with:
  - `rlm-trace ls`
  - `rlm-trace tail -n 20 --session default`
  - `rlm-trace export /tmp/rlm-traces.jsonl`
- Phase 3 consumes exported JSONL traces for GEPA/DSPy prompt optimization.

## Testing discipline

- Unit-ish: direct Python imports/calls for deterministic behavior
- Handshake: stdio MCP initialize + `tools/list`
- Integration: verify trace persistence + truncation + opt-out + `rlm-trace` commands

## What NOT to do

- Don’t store context `content` in traces (size + PII risk)
- Don’t add sandboxing to `rlm_exec` here (explicitly out of scope; trust boundary is local user)
- Don’t add paid/external LLM dependencies (`mcp>=1.2` only; sampling + callback are sufficient)
- Don’t share pickle state files between users (RCE risk)

## GEPA optimization loop (Phase 3)

- Phase 2 trace collection is live (`rlm-trace export`).
- Phase 3 GEPA scaffold is live under `gepa/` (see `gepa/README.md`).
- Intended user-driven loop:
  1. Run real sessions against this MCP server.
  2. Export traces via `rlm-trace export /path/to/traces.jsonl`.
  3. Run `python -m gepa.gepa_optimize --trainset /path/to/traces.jsonl --metric heuristic`
     for free trace-shape scoring, or `--metric eval` for benchmark-style
     examples that include `query/context/gold` and execute `eval.harness`.
  4. Review compiled output and manually copy improved tool descriptions back into
     `rlm_mcp.py` `@mcp.tool(description=...)` arguments.
- This loop is **not automatic**; optimization runs are user-initiated and may incur LM cost.
