from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .signatures import TOOL_DESCRIPTIONS_TEMPLATE

TERMINAL_TOOLS = {"rlm_get_buffers", "rlm_status", "rlm_list_sessions", "rlm_reset"}


def load_trace_records(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).expanduser().open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                records.append(row)
    return records


def _parse_ts(ts: Any) -> datetime | None:
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _split_terminal(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    out: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    for rec in records:
        cur.append(rec)
        if rec.get("tool") in TERMINAL_TOOLS:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def split_root_tasks(records: list[dict[str, Any]], gap_seconds: int = 45) -> list[list[dict[str, Any]]]:
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        by_session[str(rec.get("session_id", "default"))].append(rec)

    tasks: list[list[dict[str, Any]]] = []
    for session_records in by_session.values():
        session_records.sort(key=lambda r: (str(r.get("ts", "")), int(r.get("ns", 0))))
        cur: list[dict[str, Any]] = []
        prev_ts: datetime | None = None
        for rec in session_records:
            ts = _parse_ts(rec.get("ts"))
            if cur and prev_ts and ts and (ts - prev_ts).total_seconds() > gap_seconds:
                tasks.extend(_split_terminal(cur))
                cur = []
            cur.append(rec)
            if ts is not None:
                prev_ts = ts
        if cur:
            tasks.extend(_split_terminal(cur))
    return [t for t in tasks if t]


def _example_row(task: list[dict[str, Any]]) -> dict[str, Any]:
    tools = [str(r.get("tool", "")) for r in task if r.get("tool")]
    context_length = 0
    query = "analyze the loaded context"
    for rec in task:
        inp = rec.get("input") if isinstance(rec.get("input"), dict) else {}
        out = rec.get("output") if isinstance(rec.get("output"), dict) else {}
        if rec.get("tool") == "rlm_init" and isinstance(out.get("chars"), int):
            context_length = int(out["chars"])
        if query == "analyze the loaded context":
            for key in ("query", "prompt", "text", "code", "pattern", "path"):
                value = inp.get(key)
                if isinstance(value, str) and value.strip():
                    query = value
                    break
    outcome = str(task[-1].get("output")) if task else ""
    if len(outcome) > 240:
        outcome = outcome[:240] + "..."
    return {
        "query": query,
        "context_length": context_length,
        "tool_descriptions": TOOL_DESCRIPTIONS_TEMPLATE,
        "first_tool": tools[0] if tools else "",
        "rationale": f"Observed trajectory ended with {tools[-1] if tools else 'none'}",
        "tool_sequence": tools,
        "session_id": str(task[0].get("session_id", "default")) if task else "default",
        "outcome_summary": outcome,
        "records": task,
    }


def _to_dspy(rows: list[dict[str, Any]]) -> list[Any]:
    try:
        import dspy
    except Exception:
        return rows
    return [dspy.Example(**row).with_inputs("query", "context_length", "tool_descriptions") for row in rows]


def load_trainset(path: str | Path, gap_seconds: int = 45) -> list[Any]:
    rows = [_example_row(t) for t in split_root_tasks(load_trace_records(path), gap_seconds=gap_seconds)]
    rows = [r for r in rows if r.get("first_tool")]
    return _to_dspy(rows)
