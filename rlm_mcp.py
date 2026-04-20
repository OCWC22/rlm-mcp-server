#!/usr/bin/env python3
"""RLM MCP server — persistent text REPL for long-context workflows.

Free, local, no API keys. Exposes a stateful text buffer (one per named
session) to any MCP client so the host model can load huge files, peek,
grep, chunk, and materialise chunks for sub-agent analysis.

State pickles live in $RLM_STATE_DIR (default: ~/.cache/rlm-mcp/).
"""
from __future__ import annotations

import os
import pickle
import re
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

STATE_DIR = Path(os.environ.get("RLM_STATE_DIR", Path.home() / ".cache" / "rlm-mcp"))
STATE_DIR.mkdir(parents=True, exist_ok=True)

MAX_PEEK_CHARS = 50_000

mcp = FastMCP("rlm")


def _safe_id(session_id: str) -> str:
    cleaned = "".join(c for c in session_id if c.isalnum() or c in "._-")
    return cleaned or "default"


def _state_path(session_id: str) -> Path:
    return STATE_DIR / f"{_safe_id(session_id)}.pkl"


def _load(session_id: str) -> dict[str, Any]:
    p = _state_path(session_id)
    if not p.exists():
        raise FileNotFoundError(f"No session {session_id!r}. Call rlm_init first.")
    with p.open("rb") as f:
        return pickle.load(f)


def _save(session_id: str, state: dict[str, Any]) -> None:
    p = _state_path(session_id)
    tmp = p.with_suffix(".pkl.tmp")
    with tmp.open("wb") as f:
        pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(p)


def _compute_spans(n: int, size: int, overlap: int) -> list[list[int]]:
    if size <= 0:
        raise ValueError("size must be > 0")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")
    step = size - overlap
    spans: list[list[int]] = []
    for start in range(0, n, step):
        end = min(n, start + size)
        spans.append([start, end])
        if end >= n:
            break
    return spans


@mcp.tool()
def rlm_init(path: str, session_id: str = "default", max_bytes: int | None = None) -> dict:
    """Load a text file into a named session. Overwrites if the session exists."""
    p = Path(path).expanduser()
    if not p.exists():
        return {"error": f"File not found: {p}"}
    with p.open("rb") as f:
        data = f.read() if max_bytes is None else f.read(max_bytes)
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        content = data.decode("utf-8", errors="replace")
    state = {
        "version": 1,
        "context": {"path": str(p), "loaded_at": time.time(), "content": content},
        "buffers": [],
    }
    _save(session_id, state)
    return {
        "session_id": _safe_id(session_id),
        "path": str(p),
        "chars": len(content),
        "state_file": str(_state_path(session_id)),
    }


@mcp.tool()
def rlm_status(session_id: str = "default") -> dict:
    """Return current session stats."""
    try:
        s = _load(session_id)
    except FileNotFoundError as e:
        return {"error": str(e)}
    ctx = s["context"]
    return {
        "session_id": _safe_id(session_id),
        "path": ctx["path"],
        "chars": len(ctx["content"]),
        "loaded_at": ctx["loaded_at"],
        "buffers": len(s["buffers"]),
    }


@mcp.tool()
def rlm_peek(start: int = 0, end: int = 2000, session_id: str = "default") -> str:
    """Return content[start:end] from the session context. Capped at 50k chars."""
    s = _load(session_id)
    content = s["context"]["content"]
    a = max(0, start)
    b = min(len(content), end)
    if b - a > MAX_PEEK_CHARS:
        b = a + MAX_PEEK_CHARS
    out = content[a:b]
    if b < end:
        out += f"\n... [peek truncated at {MAX_PEEK_CHARS} chars] ..."
    return out


@mcp.tool()
def rlm_grep(
    pattern: str,
    max_matches: int = 20,
    window: int = 120,
    case_insensitive: bool = False,
    session_id: str = "default",
) -> list[dict]:
    """Regex search over the session context. Returns [{match, span, snippet}, ...]."""
    s = _load(session_id)
    content = s["context"]["content"]
    flags = re.IGNORECASE if case_insensitive else 0
    out: list[dict] = []
    for m in re.finditer(pattern, content, flags):
        start, end = m.span()
        out.append({
            "match": m.group(0),
            "span": [start, end],
            "snippet": content[max(0, start - window):min(len(content), end + window)],
        })
        if len(out) >= max_matches:
            break
    return out


@mcp.tool()
def rlm_chunk_indices(size: int = 200_000, overlap: int = 0, session_id: str = "default") -> list[list[int]]:
    """Return [start, end] spans that tile the context. Default 200k chars, no overlap."""
    s = _load(session_id)
    return _compute_spans(len(s["context"]["content"]), size, overlap)


@mcp.tool()
def rlm_write_chunks(
    out_dir: str,
    size: int = 200_000,
    overlap: int = 0,
    prefix: str = "chunk",
    session_id: str = "default",
) -> list[str]:
    """Materialise chunks as UTF-8 text files under out_dir. Returns written paths."""
    s = _load(session_id)
    content = s["context"]["content"]
    spans = _compute_spans(len(content), size, overlap)
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for i, (a, b) in enumerate(spans):
        f = out / f"{prefix}_{i:04d}.txt"
        f.write_text(content[a:b], encoding="utf-8")
        paths.append(str(f))
    return paths


@mcp.tool()
def rlm_add_buffer(text: str, session_id: str = "default") -> int:
    """Append an intermediate note. Returns new buffer count."""
    s = _load(session_id)
    s["buffers"].append(str(text))
    _save(session_id, s)
    return len(s["buffers"])


@mcp.tool()
def rlm_get_buffers(session_id: str = "default") -> list[str]:
    """Return all buffers for the session (append order)."""
    s = _load(session_id)
    return list(s["buffers"])


@mcp.tool()
def rlm_clear_buffers(session_id: str = "default") -> int:
    """Clear all buffers. Returns number cleared."""
    s = _load(session_id)
    n = len(s["buffers"])
    s["buffers"] = []
    _save(session_id, s)
    return n


@mcp.tool()
def rlm_reset(session_id: str = "default") -> dict:
    """Delete a session state file."""
    p = _state_path(session_id)
    if p.exists():
        p.unlink()
        return {"deleted": str(p)}
    return {"deleted": None, "message": f"no state for {session_id!r}"}


@mcp.tool()
def rlm_list_sessions() -> list[dict]:
    """List all active sessions."""
    out: list[dict] = []
    for f in sorted(STATE_DIR.glob("*.pkl")):
        try:
            with f.open("rb") as fp:
                s = pickle.load(fp)
            out.append({
                "session_id": f.stem,
                "path": s["context"]["path"],
                "chars": len(s["context"]["content"]),
                "buffers": len(s["buffers"]),
            })
        except Exception as e:
            out.append({"session_id": f.stem, "error": str(e)})
    return out


def main():
    mcp.run()


if __name__ == "__main__":
    main()
