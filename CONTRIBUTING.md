# Contributing to `rlm-mcp-server`

Thanks for contributing.

## Development setup

```bash
git clone https://github.com/OCWC22/rlm-mcp-server
cd rlm-mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Branch policy

- Branch from `main` using a short-lived topic branch.
- Naming guidance:
  - `feat/<topic>`
  - `fix/<topic>`
  - `chore/<topic>`
  - `docs/<topic>`
- Keep commits logical and focused.
- Merge back to `main` only after CI is green.
- Prefer fast-forward merges for single-agent maintenance flows.

## Commit conventions

Use clear, scoped subjects (Conventional-Commit style is encouraged):

- `feat: ...`
- `fix: ...`
- `docs: ...`
- `chore: ...`
- `refactor: ...`
- `test: ...`

## How to add or update an MCP tool

1. Add/modify the tool function in `rlm_mcp.py`.
2. Decorate with `@mcp.tool()` and `@_traced("tool_name")`.
3. Keep `session_id` behavior consistent with `_safe_id("default")` semantics.
4. Return JSON-serializable values.
5. Keep tracing behavior intact (`_trace(...)` on success paths; decorator handles uncaught errors).
6. Update user-facing docs (`README.md`, and `CHANGELOG.md` when relevant).

## Required checks before opening a PR

Run from repo root:

```bash
# 1) Editable install
pip install -e .

# 2) Import smoke
python -c "import rlm_mcp; import rlm_trace_cli; from eval import harness; from gepa import metrics, signatures, trace_to_dataset; print('OK')"

# 3) Stdio handshake / tool count
python - <<'PY'
import anyio
import sys
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

EXPECTED = 14

async def main():
    params = StdioServerParameters(command=sys.executable, args=["rlm_mcp.py"], cwd=".")
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            await s.send_notification(types.InitializedNotification())
            tools = await s.list_tools()
            count = len(tools.tools)
            print(f"tool_count={count}")
            if count != EXPECTED:
                raise SystemExit(f"expected {EXPECTED} tools, got {count}")

anyio.run(main)
PY

# 4) Deterministic mini-eval
python -m eval.harness --dataset=sniah --n=5 --length=2000
```

The S-NIAH mini-eval is expected to score `1.0`.

## Dependency policy

- Do not add new runtime dependencies lightly.
- Keep the base package lean (`mcp>=1.2` at present).
- Place experimental/optional packages under extras when possible.

## Release policy

- Update `CHANGELOG.md` before tagging.
- Create annotated tags (`git tag -a vX.Y.Z -m "vX.Y.Z"`).
- Publish GitHub releases with concise highlight notes and generated release notes.
