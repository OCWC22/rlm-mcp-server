#!/usr/bin/env bash
# RLM MCP server launcher. Self-bootstraps a venv on first run.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/.venv"
PY="$VENV/bin/python"

if [ ! -x "$PY" ]; then
    echo "[rlm-mcp] Bootstrapping venv..." >&2
    python3 -m venv "$VENV" >&2
    "$VENV/bin/pip" install --quiet --upgrade pip >&2
    "$VENV/bin/pip" install --quiet -r "$DIR/requirements.txt" >&2
fi

exec "$PY" "$DIR/rlm_mcp.py" "$@"
