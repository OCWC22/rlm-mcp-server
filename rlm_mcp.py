#!/usr/bin/env python3
"""RLM MCP server — persistent text REPL for long-context workflows.

Free, local, no API keys. Exposes a stateful text buffer (one per named
session) to any MCP client so the host model can load huge files, peek,
grep, chunk, and materialise chunks for sub-agent analysis.

State pickles live in $RLM_STATE_DIR (fallback: $RLM_DATA_DIR, default: ~/.cache/rlm-mcp/).
"""
from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
import io
import json
import os
import pickle
import re
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server.fastmcp import Context, FastMCP

def _resolve_env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    return Path(value).expanduser()


_state_from_primary = _resolve_env_path("RLM_STATE_DIR")
_state_from_alias = _resolve_env_path("RLM_DATA_DIR")
if _state_from_primary is not None:
    STATE_DIR = _state_from_primary
    _STATE_DIR_SOURCE = "RLM_STATE_DIR"
elif _state_from_alias is not None:
    STATE_DIR = _state_from_alias
    _STATE_DIR_SOURCE = "RLM_DATA_DIR"
else:
    STATE_DIR = Path.home() / ".cache" / "rlm-mcp"
    _STATE_DIR_SOURCE = "default"

_trace_from_primary = _resolve_env_path("RLM_TRACE_DIR")
if _trace_from_primary is not None:
    TRACE_DIR = _trace_from_primary
    _TRACE_DIR_SOURCE = "RLM_TRACE_DIR"
else:
    TRACE_DIR = STATE_DIR / "traces"
    _TRACE_DIR_SOURCE = "default"

TRACE_DISABLED = os.environ.get("RLM_TRACE_DISABLE") == "1"
STATE_DIR.mkdir(parents=True, exist_ok=True)
print(
    f"[rlm-config] state_dir={STATE_DIR} ({_STATE_DIR_SOURCE}) "
    f"trace_dir={TRACE_DIR} ({_TRACE_DIR_SOURCE})",
    file=sys.stderr,
)
_TRACE_MAX_STR = 2_000
_TRACE_HEAD_TAIL = 200
_SERVER_START_NS = time.perf_counter_ns()
_TRACE_WRITE_FAILURE_TYPES: set[str] = set()
_TRACE_START_NS: contextvars.ContextVar[int | None] = contextvars.ContextVar("rlm_trace_start_ns", default=None)
_TRACE_SESSION_ID: contextvars.ContextVar[str] = contextvars.ContextVar("rlm_trace_session_id", default="default")
_TRACE_EMITTED: contextvars.ContextVar[bool] = contextvars.ContextVar("rlm_trace_emitted", default=False)

if not TRACE_DISABLED:
    try:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        print(f"[rlm-trace] enable failed ({type(exc).__name__}): {exc}", file=sys.stderr)
    else:
        print(f"[rlm-trace] enabled dir={TRACE_DIR}", file=sys.stderr)

MAX_PEEK_CHARS = 50_000
MAX_EXEC_OUTPUT_CHARS = 8_000

_SESSION_RUNTIME: dict[str, dict[str, Any]] = {}

mcp = FastMCP("rlm")


def _trace_truncate_string(value: str) -> str | dict[str, Any]:
    if len(value) <= _TRACE_MAX_STR:
        return value
    return {
        "_truncated": True,
        "len": len(value),
        "head": value[:_TRACE_HEAD_TAIL],
        "tail": value[-_TRACE_HEAD_TAIL:],
    }


def _trace_redacted_content(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {"_redacted": True, "reason": "content_field", "len": len(value)}
    return {"_redacted": True, "reason": "content_field"}


def _sanitize_trace(value: Any, key: str | None = None) -> Any:
    if key == "content":
        return _trace_redacted_content(value)

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        return _trace_truncate_string(value)

    if isinstance(value, bytes):
        return _trace_truncate_string(value.decode("utf-8", errors="replace"))

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(k): _sanitize_trace(v, key=str(k)) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_sanitize_trace(v) for v in value]

    if hasattr(value, "model_dump"):
        try:
            return _sanitize_trace(value.model_dump())
        except Exception:
            pass

    return _trace_truncate_string(repr(value))


def _bind_trace_input(fn: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    try:
        bound = inspect.signature(fn).bind_partial(*args, **kwargs)
        bound.apply_defaults()
        return {k: v for k, v in bound.arguments.items() if k != "ctx"}
    except Exception:
        return {"args": list(args), "kwargs": kwargs}


def _trace_write_failure_once(exc: Exception) -> None:
    exc_name = type(exc).__name__
    if exc_name in _TRACE_WRITE_FAILURE_TYPES:
        return
    _TRACE_WRITE_FAILURE_TYPES.add(exc_name)
    print(f"[rlm-trace] write failed ({exc_name}): {exc}", file=sys.stderr)


def _trace(tool: str, input_data: Any, output_data: Any, session_id: str | None = None) -> None:
    """Append one JSONL trace record per tool call."""
    _TRACE_EMITTED.set(True)

    if TRACE_DISABLED:
        return

    sid = _safe_id(session_id or _TRACE_SESSION_ID.get())
    now_utc = datetime.now(timezone.utc)
    now_ns = time.perf_counter_ns()
    started_ns = _TRACE_START_NS.get()
    duration_ms = 0
    if started_ns is not None:
        duration_ms = int(max(0, (now_ns - started_ns) // 1_000_000))

    record = {
        "ts": now_utc.isoformat().replace("+00:00", "Z"),
        "ns": int(now_ns - _SERVER_START_NS),
        "session_id": sid,
        "tool": tool,
        "input": _sanitize_trace(input_data),
        "output": _sanitize_trace(output_data),
        "duration_ms": duration_ms,
    }

    trace_path = TRACE_DIR / f"{sid}-{now_utc.strftime('%Y%m%d')}.jsonl"
    try:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        with trace_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:
        _trace_write_failure_once(exc)


def _traced(tool_name: str):
    """Decorator that captures per-call timing/session and traces uncaught errors."""

    def decorator(fn: Any):
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any):
                bound_input = _bind_trace_input(fn, args, kwargs)
                sid = _safe_id(str(bound_input.get("session_id", "default")))
                start_token = _TRACE_START_NS.set(time.perf_counter_ns())
                sid_token = _TRACE_SESSION_ID.set(sid)
                emitted_token = _TRACE_EMITTED.set(False)
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    if not _TRACE_EMITTED.get():
                        _trace(
                            tool_name,
                            bound_input,
                            {"error": f"{type(exc).__name__}: {exc}"},
                            session_id=sid,
                        )
                    raise
                finally:
                    _TRACE_START_NS.reset(start_token)
                    _TRACE_SESSION_ID.reset(sid_token)
                    _TRACE_EMITTED.reset(emitted_token)

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any):
            bound_input = _bind_trace_input(fn, args, kwargs)
            sid = _safe_id(str(bound_input.get("session_id", "default")))
            start_token = _TRACE_START_NS.set(time.perf_counter_ns())
            sid_token = _TRACE_SESSION_ID.set(sid)
            emitted_token = _TRACE_EMITTED.set(False)
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                if not _TRACE_EMITTED.get():
                    _trace(
                        tool_name,
                        bound_input,
                        {"error": f"{type(exc).__name__}: {exc}"},
                        session_id=sid,
                    )
                raise
            finally:
                _TRACE_START_NS.reset(start_token)
                _TRACE_SESSION_ID.reset(sid_token)
                _TRACE_EMITTED.reset(emitted_token)

        return sync_wrapper

    return decorator


class RLMCallbackRequired(RuntimeError):
    """Raised when callback-mode sub-query results are required."""

    def __init__(self, request_id: str, prompt: str):
        self.request_id = request_id
        self.prompt = prompt
        super().__init__(f"callback required: {request_id}")


def _safe_id(session_id: str) -> str:
    cleaned = "".join(c for c in session_id if c.isalnum() or c in "._-")
    return cleaned or "default"


def _state_path(session_id: str) -> Path:
    return STATE_DIR / f"{_safe_id(session_id)}.pkl"


def _default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "context": {
            "path": "<memory>",
            "loaded_at": time.time(),
            "content": "",
        },
        "buffers": [],
        "globals": {},
    }


def _load(session_id: str) -> dict[str, Any]:
    p = _state_path(session_id)
    if not p.exists():
        raise FileNotFoundError(f"No session {session_id!r}. Call rlm_init first.")
    with p.open("rb") as f:
        return pickle.load(f)


def _load_for_exec(session_id: str) -> dict[str, Any]:
    p = _state_path(session_id)
    if not p.exists():
        return _default_state()
    with p.open("rb") as f:
        state = pickle.load(f)
    if not isinstance(state, dict):
        return _default_state()
    return state


def _save(session_id: str, state: dict[str, Any]) -> None:
    p = _state_path(session_id)
    tmp = p.with_suffix(".pkl.tmp")
    with tmp.open("wb") as f:
        pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(p)


def _normalize_exec_state(state: dict[str, Any]) -> dict[str, Any]:
    context = state.get("context")
    if not isinstance(context, dict):
        context = _default_state()["context"]
    if "path" not in context:
        context["path"] = "<memory>"
    if "loaded_at" not in context:
        context["loaded_at"] = time.time()
    if "content" not in context:
        context["content"] = ""
    context["content"] = str(context.get("content", ""))

    buffers = state.get("buffers")
    if not isinstance(buffers, list):
        buffers = []

    persisted = state.get("globals")
    if not isinstance(persisted, dict):
        persisted = {}

    state["context"] = context
    state["buffers"] = buffers
    state["globals"] = persisted
    state.setdefault("version", 1)
    return state


def _truncate(s: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + f"\n... [truncated to {max_chars} chars] ...\n"


def _is_pickleable(value: Any) -> bool:
    try:
        pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        return True
    except Exception:
        return False


def _filter_pickleable(d: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    kept: dict[str, Any] = {}
    dropped: list[str] = []
    for k, v in d.items():
        if _is_pickleable(v):
            kept[k] = v
        else:
            dropped.append(k)
    return kept, dropped


def _runtime(session_id: str) -> dict[str, Any]:
    sid = _safe_id(session_id)
    if sid not in _SESSION_RUNTIME:
        _SESSION_RUNTIME[sid] = {
            "use_callback": False,
            "pending_requests": {},
            "prompt_results": {},
            "results_by_request_id": {},
            "last_sampling_error": None,
        }
    return _SESSION_RUNTIME[sid]


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


def _make_helpers(context_ref: dict[str, Any], buffers_ref: list[str]) -> dict[str, Any]:
    def peek(start: int = 0, end: int = 2000) -> str:
        content = str(context_ref.get("content", ""))
        a = max(0, start)
        b = min(len(content), end)
        if b - a > MAX_PEEK_CHARS:
            b = a + MAX_PEEK_CHARS
        out = content[a:b]
        if b < end:
            out += f"\n... [peek truncated at {MAX_PEEK_CHARS} chars] ..."
        return out

    def grep(
        pattern: str,
        max_matches: int = 20,
        window: int = 120,
        case_insensitive: bool = False,
    ) -> list[dict[str, Any]]:
        content = str(context_ref.get("content", ""))
        flags = re.IGNORECASE if case_insensitive else 0
        out: list[dict[str, Any]] = []
        for m in re.finditer(pattern, content, flags):
            start, end = m.span()
            out.append(
                {
                    "match": m.group(0),
                    "span": [start, end],
                    "snippet": content[max(0, start - window):min(len(content), end + window)],
                }
            )
            if len(out) >= max_matches:
                break
        return out

    def chunk_indices(size: int = 200_000, overlap: int = 0) -> list[list[int]]:
        content = str(context_ref.get("content", ""))
        return _compute_spans(len(content), size, overlap)

    def write_chunks(
        out_dir: str,
        size: int = 200_000,
        overlap: int = 0,
        prefix: str = "chunk",
    ) -> list[str]:
        content = str(context_ref.get("content", ""))
        spans = _compute_spans(len(content), size, overlap)
        out = Path(out_dir).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        for i, (a, b) in enumerate(spans):
            f = out / f"{prefix}_{i:04d}.txt"
            f.write_text(content[a:b], encoding="utf-8")
            paths.append(str(f))
        return paths

    def add_buffer(text: str) -> int:
        buffers_ref.append(str(text))
        return len(buffers_ref)

    return {
        "peek": peek,
        "grep": grep,
        "chunk_indices": chunk_indices,
        "write_chunks": write_chunks,
        "add_buffer": add_buffer,
    }


def _consume_callback_result(session_id: str, prompt: str) -> str | None:
    runtime = _runtime(session_id)
    prompt_results = runtime.setdefault("prompt_results", {})
    queue = prompt_results.get(prompt)
    if not queue:
        return None
    result = queue.pop(0)
    if not queue:
        prompt_results.pop(prompt, None)
    return result


def _queue_callback_request(session_id: str, prompt: str, max_tokens: int) -> dict[str, Any]:
    runtime = _runtime(session_id)
    request_id = str(uuid.uuid4())
    runtime.setdefault("pending_requests", {})[request_id] = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "created_at": time.time(),
    }
    return {"need_subquery": True, "prompt": prompt, "request_id": request_id}


def _store_callback_result(session_id: str, request_id: str, result: str) -> dict[str, Any]:
    runtime = _runtime(session_id)
    runtime.setdefault("results_by_request_id", {})[request_id] = result

    pending = runtime.setdefault("pending_requests", {}).pop(request_id, None)
    if isinstance(pending, dict) and "prompt" in pending:
        prompt = str(pending["prompt"])
        runtime.setdefault("prompt_results", {}).setdefault(prompt, []).append(result)
        return {
            "stored": True,
            "request_id": request_id,
            "matched": True,
            "prompt": prompt,
        }

    return {
        "stored": True,
        "request_id": request_id,
        "matched": False,
        "message": "request_id was not pending; result stored by request_id only",
    }


async def _sampling_sub_query(prompt: str, max_tokens: int, ctx: Context | None) -> str:
    if ctx is None:
        raise RuntimeError("MCP Context unavailable for sampling")

    message = types.SamplingMessage(
        role="user",
        content=types.TextContent(type="text", text=prompt),
    )
    result = await ctx.session.create_message(
        messages=[message],
        max_tokens=max_tokens,
    )

    content = result.content
    if isinstance(content, types.TextContent):
        return content.text

    if hasattr(content, "text"):
        return str(getattr(content, "text"))

    if hasattr(content, "model_dump"):
        return json.dumps(content.model_dump(), ensure_ascii=False)

    return str(content)


async def _sub_query_impl(
    prompt: str,
    max_tokens: int,
    session_id: str,
    ctx: Context | None,
) -> str | dict[str, Any]:
    sid = _safe_id(session_id)
    runtime = _runtime(sid)

    cached = _consume_callback_result(sid, prompt)
    if cached is not None:
        return cached

    if runtime.get("use_callback"):
        return _queue_callback_request(sid, prompt, max_tokens)

    try:
        return await _sampling_sub_query(prompt=prompt, max_tokens=max_tokens, ctx=ctx)
    except (AttributeError, NotImplementedError) as exc:
        runtime["use_callback"] = True
        runtime["last_sampling_error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        runtime["use_callback"] = True
        runtime["last_sampling_error"] = f"{type(exc).__name__}: {exc}"

    return _queue_callback_request(sid, prompt, max_tokens)


# --- v0.7.0: mandatory Appendix-C.1 scaffolding appended to every prompt template ---
MANDATORY_SCAFFOLD = """
# --- MANDATORY recursive scaffold (paper arXiv:2512.24601 Appendix C.1) ---
# You MUST follow these steps. Do NOT answer from a single peek or single grep hit.
#
# After orientation, call rlm_exec with code shaped like:
#
#   hits = grep(r"<broad regex covering every candidate term>", max_matches=40)
#   for i, h in enumerate(hits):
#       s, e = h["span"]
#       chunk = content[max(0, s-500):min(len(content), e+2000)]
#       ans = llm_query(
#           f"Question: {question}\n\n"
#           f"From this excerpt, extract ALL facts relevant to the question. "
#           f"Excerpt (hit {i+1}/{len(hits)}):\n{chunk}",
#           max_tokens=400,
#       )
#       add_buffer(ans)
#   print(f"collected {len(hits)} chunk answers")
#
# Then one final rlm_exec to synthesize from buffers:
#
#   bufs = rlm_get_buffers(session_id)
#   final = llm_query(
#       f"Synthesize a complete answer to: {question}\n\n"
#       f"Per-chunk findings (merge, dedupe, keep every distinct fact):\n" +
#       "\n---\n".join(bufs),
#       max_tokens=800,
#   )
#   print(final)
#
# Missing variants/cases on enumeration tasks is a hard failure — err toward
# more chunks and broader regex. If initial grep returns <10 hits for a
# comparison task, widen the regex and re-run before the loop.
# --- end scaffold ---
"""

@mcp.prompt(
    description=(
        "Prime a GPU-kernel analysis workflow over rlm tools with grep anchors, "
        "stateful exec loops, and recursive hotspot reviews."
    )
)
def kernel_analysis(kernel_path: str, question: str) -> list[dict[str, str]]:
    """Prompt template for AMD HIP / CUDA / Triton kernel inspection workflows."""
    return [
        {
            "role": "assistant",
            "content": (
                "Use this tool sequence for kernel review: rlm_init -> rlm_status -> "
                "rlm_grep for primitives (__global__, dim3, __shared__, atomicAdd, "
                "wave_size, threadIdx/blockIdx) -> rlm_exec for per-function stats -> "
                "llm_query/rlm_sub_query for semantic hotspot analysis -> "
                "rlm_add_buffer + rlm_get_buffers for final synthesis. If callback mode "
                "is requested, satisfy it with rlm_sub_query_result and resume."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Analyze GPU kernel source at `{kernel_path}` and answer: {question}\n\n"
                "Start by loading the file into session `kernel_analysis`. Then grep for "
                "launch signatures, shared-memory usage, synchronization, atomics, and "
                "warp/wave assumptions. Next run rlm_exec code that enumerates likely "
                "functions, estimates memory-access and reduction patterns, and records "
                "intermediate conclusions with rlm_add_buffer. Use recursive sub-queries "
                "for contentious hotspots (e.g., occupancy bottlenecks or race risks), "
                "and finish with a prioritized summary grounded in concrete spans."
                + MANDATORY_SCAFFOLD
            ),
        },
    ]


@mcp.prompt(
    description=(
        "Prime a paper-reading workflow that chunks sections, runs focused recursive "
        "sub-analyses, and synthesizes topic-specific conclusions."
    )
)
def paper_deep_dive(paper_path: str, topic: str) -> list[dict[str, str]]:
    """Prompt template for long-form academic text analysis."""
    return [
        {
            "role": "assistant",
            "content": (
                "Use this sequence: rlm_init -> rlm_status -> rlm_grep on topic terms -> "
                "rlm_exec to split by section headers and track section metadata -> "
                "rlm_sub_query or llm_query per section -> rlm_add_buffer and "
                "rlm_get_buffers for synthesis. Keep findings tied to explicit section "
                "spans and quote snippets when confidence is low."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Deep-dive `{paper_path}` with focus topic: {topic}.\n\n"
                "Load into session `paper_deep_dive`, identify structural boundaries "
                "(abstract, intro, method, results, discussion/appendix), and collect "
                "topic-relevant evidence in each section. Use recursive sub-queries to "
                "extract claims, assumptions, metrics, and failure modes section-by-"
                "section. End with a synthesized answer that distinguishes confirmed "
                "claims, inferred implications, and open questions."
                + MANDATORY_SCAFFOLD
            ),
        },
    ]


@mcp.prompt(
    description=(
        "Prime a large-codebase triage workflow using grep discovery, stateful "
        "navigation logic, and buffered synthesis."
    )
)
def codebase_triage(repo_path: str, question: str) -> list[dict[str, str]]:
    """Prompt template for pre-concatenated corpus triage and architecture discovery."""
    return [
        {
            "role": "assistant",
            "content": (
                "Assume repo_path points to a pre-concatenated corpus file (for example: "
                "find ... -type f | xargs cat > corpus.txt). Use rlm_init -> rlm_status -> "
                "rlm_grep to locate candidate modules and symbols -> rlm_exec to build a "
                "navigation index and shortlist hotspots -> rlm_add_buffer/rlm_get_buffers "
                "for roll-up. Use rlm_sub_query for focused semantic reads of dense spans."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Triage corpus `{repo_path}` to answer: {question}.\n\n"
                "Start broad with grep-driven discovery (entrypoints, config, APIs, "
                "tests), then narrow to the files or symbol clusters most relevant to "
                "the question. Use rlm_exec to maintain evolving maps of components, "
                "dependencies, and unresolved hypotheses across turns. Finish with a "
                "concise findings report plus concrete follow-up probes if certainty is "
                "below high confidence."
                + MANDATORY_SCAFFOLD
            ),
        },
    ]


@mcp.tool()
@_traced("rlm_init")
def rlm_init(path: str, session_id: str = "default", max_bytes: int | None = None) -> dict:
    """Call this when you have a local text file and need it loaded into an RLM session for repeated analysis.

Example: args = {"path": "/tmp/corpus.txt", "session_id": "paper", "max_bytes": 2_000_000}. Next step is typically `rlm_status` to confirm load size, followed by `rlm_grep` or `rlm_peek` for targeted reads. NEVER use this for binary assets when byte-perfect fidelity matters.
"""
    tool_input = {"path": path, "session_id": session_id, "max_bytes": max_bytes}

    p = Path(path).expanduser()
    if not p.exists():
        out = {"error": f"File not found: {p}"}
        _trace("rlm_init", tool_input, out)
        return out

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
        "globals": {},
    }
    _save(session_id, state)

    out = {
        "session_id": _safe_id(session_id),
        "path": str(p),
        "chars": len(content),
        "state_file": str(_state_path(session_id)),
    }
    _trace("rlm_init", tool_input, out)
    return out


@mcp.tool()
@_traced("rlm_status")
def rlm_status(session_id: str = "default") -> dict:
    """Call this when you need a quick metadata check before deeper tool calls.

Example: args = {"session_id": "paper"}. Next step is usually `rlm_grep` or `rlm_peek` once you confirm the expected file and character count are loaded. NEVER use this when you need the underlying text itself.
"""
    tool_input = {"session_id": session_id}

    try:
        s = _load(session_id)
    except FileNotFoundError as e:
        out = {"error": str(e)}
        _trace("rlm_status", tool_input, out)
        return out

    ctx = s["context"]
    out = {
        "session_id": _safe_id(session_id),
        "path": ctx["path"],
        "chars": len(ctx["content"]),
        "loaded_at": ctx["loaded_at"],
        "buffers": len(s["buffers"]),
        "globals": len(s.get("globals", {})),
    }
    _trace("rlm_status", tool_input, out)
    return out


@mcp.tool()
@_traced("rlm_peek")
def rlm_peek(start: int = 0, end: int = 2000, session_id: str = "default") -> str:
    """Call this when you know a character range and need exact text from the loaded context.

Example: args = {"start": 12_000, "end": 15_000, "session_id": "paper"}. Next step is typically to summarize that slice, run `rlm_grep` for nearby anchors, or store a takeaway with `rlm_add_buffer`. NEVER use this as a full-document export path; it intentionally caps large reads.
"""
    tool_input = {"start": start, "end": end, "session_id": session_id}

    s = _load(session_id)
    content = s["context"]["content"]
    a = max(0, start)
    b = min(len(content), end)
    if b - a > MAX_PEEK_CHARS:
        b = a + MAX_PEEK_CHARS
    out = content[a:b]
    if b < end:
        out += f"\n... [peek truncated at {MAX_PEEK_CHARS} chars] ..."

    _trace("rlm_peek", tool_input, out)
    return out


@mcp.tool()
@_traced("rlm_grep")
def rlm_grep(
    pattern: str,
    max_matches: int = 20,
    window: int = 120,
    case_insensitive: bool = False,
    session_id: str = "default",
) -> list[dict]:
    """Call this when you have a regex or keyword pattern and need fast anchor points into long context.

Example: args = {"pattern": "atomicAdd|__shared__", "max_matches": 30, "window": 200, "session_id": "kernel"}. Next step is usually `rlm_peek` around interesting spans or `rlm_add_buffer` to capture findings for synthesis. NEVER use this as a syntax-aware parser for languages that require an AST.
"""
    tool_input = {
        "pattern": pattern,
        "max_matches": max_matches,
        "window": window,
        "case_insensitive": case_insensitive,
        "session_id": session_id,
    }

    s = _load(session_id)
    content = s["context"]["content"]
    flags = re.IGNORECASE if case_insensitive else 0
    out: list[dict] = []

    for m in re.finditer(pattern, content, flags):
        start, end = m.span()
        out.append(
            {
                "match": m.group(0),
                "span": [start, end],
                "snippet": content[max(0, start - window):min(len(content), end + window)],
            }
        )
        if len(out) >= max_matches:
            break

    _trace("rlm_grep", tool_input, out)
    return out


@mcp.tool()
@_traced("rlm_chunk_indices")
def rlm_chunk_indices(
    size: int = 200_000,
    overlap: int = 0,
    session_id: str = "default",
) -> list[list[int]]:
    """Call this when you need a deterministic chunking plan before iterative analysis.

Example: args = {"size": 120_000, "overlap": 2_000, "session_id": "paper"}. Next step is typically iterating those spans with `rlm_peek` in a loop or materializing files with `rlm_write_chunks`. NEVER use this expecting text output; it returns span metadata only.
"""
    tool_input = {"size": size, "overlap": overlap, "session_id": session_id}

    s = _load(session_id)
    out = _compute_spans(len(s["context"]["content"]), size, overlap)

    _trace("rlm_chunk_indices", tool_input, out)
    return out


@mcp.tool()
@_traced("rlm_write_chunks")
def rlm_write_chunks(
    out_dir: str,
    size: int = 200_000,
    overlap: int = 0,
    prefix: str = "chunk",
    session_id: str = "default",
) -> list[str]:
    """Call this when downstream tooling or sub-agents need chunk files on disk rather than in-memory spans.

Example: args = {"out_dir": "/tmp/paper_chunks", "size": 100_000, "overlap": 1_000, "prefix": "sec", "session_id": "paper"}. Next step is typically looping over returned paths with `rlm_sub_query`/`llm_query` and then consolidating conclusions in buffers. NEVER use this for quick interactive inspection where `rlm_peek` is enough.
"""
    tool_input = {
        "out_dir": out_dir,
        "size": size,
        "overlap": overlap,
        "prefix": prefix,
        "session_id": session_id,
    }

    s = _load(session_id)
    content = s["context"]["content"]
    spans = _compute_spans(len(content), size, overlap)
    out_dir_path = Path(out_dir).expanduser()
    out_dir_path.mkdir(parents=True, exist_ok=True)

    paths: list[str] = []
    for i, (a, b) in enumerate(spans):
        f = out_dir_path / f"{prefix}_{i:04d}.txt"
        f.write_text(content[a:b], encoding="utf-8")
        paths.append(str(f))

    _trace("rlm_write_chunks", tool_input, paths)
    return paths


@mcp.tool()
@_traced("rlm_add_buffer")
def rlm_add_buffer(text: str, session_id: str = "default") -> int:
    """Call this when you want to persist an intermediate insight without mutating the main context.

Example: args = {"text": "Kernel launch bounds imply 256-thread blocks", "session_id": "kernel"}. Next step is typically `rlm_get_buffers` for synthesis or `rlm_clear_buffers` when starting a fresh pass. NEVER use this as a replacement for structured source data.
"""
    tool_input = {"text": text, "session_id": session_id}

    s = _load(session_id)
    s["buffers"].append(str(text))
    _save(session_id, s)

    out = len(s["buffers"])
    _trace("rlm_add_buffer", tool_input, out)
    return out


@mcp.tool()
@_traced("rlm_get_buffers")
def rlm_get_buffers(session_id: str = "default") -> list[str]:
    """Call this when you need the full ordered note trail accumulated via `rlm_add_buffer`.

Example: args = {"session_id": "paper"}. Next step is usually writing a synthesis from these notes or pruning stale entries with `rlm_clear_buffers`. NEVER use this expecting raw context slices from the loaded file.
"""
    tool_input = {"session_id": session_id}

    s = _load(session_id)
    out = list(s["buffers"])

    _trace("rlm_get_buffers", tool_input, out)
    return out


@mcp.tool()
@_traced("rlm_clear_buffers")
def rlm_clear_buffers(session_id: str = "default") -> int:
    """Call this when you are starting a new analysis phase and want to wipe intermediate notes.

Example: args = {"session_id": "triage"}. Next step is usually another `rlm_add_buffer` cycle with cleaner hypotheses tied to the new objective. NEVER use this to delete session context or persisted globals; use `rlm_reset` for that.
"""
    tool_input = {"session_id": session_id}

    s = _load(session_id)
    n = len(s["buffers"])
    s["buffers"] = []
    _save(session_id, s)

    _trace("rlm_clear_buffers", tool_input, n)
    return n


def _execute_code(code: str, env: dict[str, Any]) -> dict[str, Any]:
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    callback_required: dict[str, str] | None = None

    with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
        try:
            exec(code, env, env)
        except RLMCallbackRequired as exc:
            callback_required = {
                "request_id": exc.request_id,
                "prompt": exc.prompt,
            }
        except Exception:
            traceback.print_exc(file=stderr_buf)

    out: dict[str, Any] = {
        "stdout": _truncate(stdout_buf.getvalue(), MAX_EXEC_OUTPUT_CHARS),
        "stderr": _truncate(stderr_buf.getvalue(), MAX_EXEC_OUTPUT_CHARS),
    }
    if callback_required is not None:
        out["callback_required"] = callback_required
    return out


@mcp.tool()
@_traced("rlm_exec")
async def rlm_exec(code: str, session_id: str = "default", ctx: Context | None = None) -> dict:
    """Call this when you need programmable control flow over loaded context with persistent variables across invocations.

Example: args = {"session_id": "kernel", "code": "hits = grep('atomicAdd')\nprint(len(hits))"}. Next step is typically to inspect `stdout`/`stderr`, iterate on the code, and optionally recurse with `llm_query` for hotspot interpretation. NEVER use this with untrusted code; execution is intentionally unsandboxed.
"""
    tool_input = {"code": code, "session_id": session_id}

    sid = _safe_id(session_id)
    runtime = _runtime(sid)
    main_loop = asyncio.get_running_loop()

    state = _normalize_exec_state(_load_for_exec(sid))
    context_ref = state["context"]
    buffers_ref = state["buffers"]
    persisted_globals = state["globals"]

    def llm_query(prompt: str, max_tokens: int = 2000) -> str:
        cached = _consume_callback_result(sid, prompt)
        if cached is not None:
            return cached

        if ctx is None or runtime.get("use_callback"):
            queued = _queue_callback_request(sid, prompt, max_tokens)
            raise RLMCallbackRequired(
                request_id=str(queued["request_id"]),
                prompt=str(queued["prompt"]),
            )

        async def _do() -> str:
            return await _sampling_sub_query(prompt=prompt, max_tokens=max_tokens, ctx=ctx)

        try:
            fut = asyncio.run_coroutine_threadsafe(_do(), main_loop)
            return str(fut.result(timeout=300))
        except Exception as exc:
            runtime["use_callback"] = True
            runtime["last_sampling_error"] = f"{type(exc).__name__}: {exc}"
            queued = _queue_callback_request(sid, prompt, max_tokens)
            raise RLMCallbackRequired(
                request_id=str(queued["request_id"]),
                prompt=str(queued["prompt"]),
            )

    env: dict[str, Any] = dict(persisted_globals)
    env["context"] = context_ref
    env["content"] = context_ref.get("content", "")
    env["buffers"] = buffers_ref

    helpers = _make_helpers(context_ref, buffers_ref)
    env.update(helpers)
    env["llm_query"] = llm_query

    exec_out = await main_loop.run_in_executor(None, _execute_code, code, env)

    maybe_ctx = env.get("context")
    if isinstance(maybe_ctx, dict) and "content" in maybe_ctx:
        state["context"] = maybe_ctx

    maybe_buffers = env.get("buffers")
    if isinstance(maybe_buffers, list):
        state["buffers"] = maybe_buffers

    injected_keys = {
        "__builtins__",
        "context",
        "content",
        "buffers",
        "llm_query",
        *helpers.keys(),
    }
    to_persist = {k: v for k, v in env.items() if k not in injected_keys}
    filtered, dropped = _filter_pickleable(to_persist)
    state["globals"] = filtered

    _save(sid, state)

    stderr = str(exec_out.get("stderr", ""))
    if dropped:
        dropped_msg = "Dropped unpickleable variables: " + ", ".join(dropped)
        if stderr:
            stderr = f"{stderr.rstrip()}\n{dropped_msg}\n"
        else:
            stderr = f"{dropped_msg}\n"

    out: dict[str, Any] = {
        "stdout": str(exec_out.get("stdout", "")),
        "stderr": _truncate(stderr, MAX_EXEC_OUTPUT_CHARS),
    }
    if "callback_required" in exec_out:
        out["callback_required"] = exec_out["callback_required"]

    _trace("rlm_exec", tool_input, out)
    return out


@mcp.tool()
@_traced("rlm_sub_query")
async def rlm_sub_query(
    prompt: str,
    max_tokens: int = 2000,
    session_id: str = "default",
    ctx: Context | None = None,
) -> str | dict:
    """Call this when you need one focused recursive model call without writing a full `rlm_exec` program.

Example: args = {"prompt": "Summarize risks in function reduce_warp", "max_tokens": 800, "session_id": "kernel"}. Next step is either consuming the returned text directly or, if `need_subquery` is returned, providing the answer through `rlm_sub_query_result` before retrying. NEVER use this for broad multi-step orchestration that belongs in host-level planning.
"""
    tool_input = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "session_id": session_id,
    }

    out = await _sub_query_impl(
        prompt=prompt,
        max_tokens=max_tokens,
        session_id=session_id,
        ctx=ctx,
    )

    _trace("rlm_sub_query", tool_input, out)
    return out


@mcp.tool()
@_traced("rlm_sub_query_result")
def rlm_sub_query_result(
    request_id: str,
    result: str,
    session_id: str = "default",
) -> dict:
    """Call this when `rlm_sub_query` or `llm_query` returns `need_subquery` and you must feed back a callback answer.

Example: args = {"request_id": "9f...", "result": "Section 3 claims linear memory scaling", "session_id": "paper"}. Next step is typically rerunning the original `rlm_sub_query`/`rlm_exec` call so the queued result is consumed. NEVER use this with guessed request IDs; unmatched results cannot be linked to the intended prompt flow.
"""
    tool_input = {
        "request_id": request_id,
        "result": result,
        "session_id": session_id,
    }

    out = _store_callback_result(
        session_id=session_id,
        request_id=request_id,
        result=result,
    )

    _trace("rlm_sub_query_result", tool_input, out)
    return out


@mcp.tool()
@_traced("rlm_reset")
def rlm_reset(session_id: str = "default") -> dict:
    """Call this when you need to fully discard one session’s saved context, buffers, and persisted globals.

Example: args = {"session_id": "old_experiment"}. Next step is typically `rlm_list_sessions` to verify cleanup or `rlm_init` to start a fresh session with new source text. NEVER use this when you only want to clear notes; `rlm_clear_buffers` is the safer narrow operation.
"""
    tool_input = {"session_id": session_id}

    p = _state_path(session_id)
    if p.exists():
        p.unlink()
        out = {"deleted": str(p)}
        _trace("rlm_reset", tool_input, out)
        return out

    out = {"deleted": None, "message": f"no state for {session_id!r}"}
    _trace("rlm_reset", tool_input, out)
    return out


@mcp.tool()
@_traced("rlm_list_sessions")
def rlm_list_sessions() -> list[dict]:
    """Call this when you need to discover which session IDs currently exist before selecting one for analysis.

Example: args = {}. Next step is usually `rlm_status` on a chosen session, then `rlm_grep`/`rlm_peek` to continue work in the right context. NEVER use this as a permissions boundary; it is an inventory helper only.
"""
    tool_input: dict[str, Any] = {}

    out: list[dict] = []
    for f in sorted(STATE_DIR.glob("*.pkl")):
        try:
            with f.open("rb") as fp:
                s = pickle.load(fp)
            out.append(
                {
                    "session_id": f.stem,
                    "path": s["context"]["path"],
                    "chars": len(s["context"]["content"]),
                    "buffers": len(s["buffers"]),
                    "globals": len(s.get("globals", {})),
                }
            )
        except Exception as e:
            out.append({"session_id": f.stem, "error": str(e)})

    _trace("rlm_list_sessions", tool_input, out)
    return out


def main():
    mcp.run()


if __name__ == "__main__":
    main()
