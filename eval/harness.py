"""Paper-aligned evaluation harness scaffold for rlm-mcp-server."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import anyio

from .loaders import load_dataset_tasks
from .runners.mcp_client import MCPToolClient

UUID_REGEX = r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
EXEC_EXTRACT_CODE = f"""import re
m = re.search(r"{UUID_REGEX}", content)
print(m.group(0) if m else "")
"""


def _extract_uuid(text: str) -> str:
    match = re.search(UUID_REGEX, text or "")
    return match.group(0) if match else ""


def _extract_exec_answer(exec_result: Any) -> str:
    if isinstance(exec_result, dict):
        stdout = str(exec_result.get("stdout", "")).strip()
        if stdout:
            return _extract_uuid(stdout.splitlines()[-1]) or stdout.splitlines()[-1].strip()
    if isinstance(exec_result, str):
        return _extract_uuid(exec_result) or exec_result.strip()
    return ""


async def _run_task_async(task: dict[str, Any], tools_sequence_hint: str | None = None) -> dict[str, Any]:
    task_id = str(task.get("task_id", f"task-{uuid.uuid4().hex[:8]}"))
    query = str(task.get("query", ""))
    context = str(task.get("context", ""))
    gold = str(task.get("gold", "")).strip()

    session_id = f"eval-{uuid.uuid4().hex[:10]}"
    driver_hint = tools_sequence_hint or "rlm_peek -> rlm_grep -> rlm_exec"

    tool_times: dict[str, int] = {}
    tmp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
            f.write(context)
            tmp_path = Path(f.name)

        async with MCPToolClient(timeout_seconds=60.0) as client:
            t0 = time.perf_counter()
            await client.call_tool("rlm_init", {"path": str(tmp_path), "session_id": session_id})
            tool_times["rlm_init"] = int((time.perf_counter() - t0) * 1000)

            peek_end = min(max(2_000, len(context) // 8), 20_000)
            t0 = time.perf_counter()
            _ = await client.call_tool("rlm_peek", {"start": 0, "end": peek_end, "session_id": session_id})
            tool_times["rlm_peek"] = int((time.perf_counter() - t0) * 1000)

            t0 = time.perf_counter()
            grep_result = await client.call_tool(
                "rlm_grep",
                {
                    "pattern": UUID_REGEX,
                    "max_matches": 5,
                    "window": 48,
                    "session_id": session_id,
                },
            )
            tool_times["rlm_grep"] = int((time.perf_counter() - t0) * 1000)

            t0 = time.perf_counter()
            exec_result = await client.call_tool(
                "rlm_exec",
                {"code": EXEC_EXTRACT_CODE, "session_id": session_id},
            )
            tool_times["rlm_exec"] = int((time.perf_counter() - t0) * 1000)

        answer = ""
        if isinstance(grep_result, list) and grep_result:
            first = grep_result[0]
            if isinstance(first, dict):
                answer = str(first.get("match", "")).strip()

        if not answer:
            answer = _extract_exec_answer(exec_result)

        if not answer:
            answer = _extract_uuid(query)

        score = 1.0 if answer == gold else 0.0
        return {
            "task_id": task_id,
            "score": score,
            "answer": answer,
            "gold": gold,
            "driver": driver_hint,
            "timing_ms": tool_times,
            "metadata": task.get("metadata", {}),
        }
    except Exception as exc:
        return {
            "task_id": task_id,
            "score": 0.0,
            "answer": "",
            "gold": gold,
            "error": f"{type(exc).__name__}: {exc}",
            "driver": driver_hint,
            "timing_ms": tool_times,
            "metadata": task.get("metadata", {}),
        }
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _run_task_sync(task: dict[str, Any], tools_sequence_hint: str | None = None) -> dict[str, Any]:
    return anyio.run(_run_task_async, task, tools_sequence_hint)


def run_eval(tasks: list, tools_sequence_hint: str | None = None, max_parallel: int = 1) -> dict:
    """Run deterministic tool-plumbing evaluation over tasks.

    Args:
        tasks: list of {query, context, gold, metadata}
        tools_sequence_hint: optional driver description
        max_parallel: task-level parallelism (fresh server process per task)
    """
    started = time.perf_counter()
    if not tasks:
        return {
            "task_count": 0,
            "pass_count": 0,
            "score": 0.0,
            "per_task": [],
            "timing_ms": {"total": 0, "avg_per_task": 0},
        }

    workers = max(1, int(max_parallel))
    if workers == 1:
        per_task = [_run_task_sync(task, tools_sequence_hint=tools_sequence_hint) for task in tasks]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_run_task_sync, task, tools_sequence_hint) for task in tasks]
            per_task = [f.result() for f in futures]

    pass_count = sum(1 for row in per_task if float(row.get("score", 0.0)) >= 1.0)
    task_count = len(per_task)
    total_ms = int((time.perf_counter() - started) * 1000)
    score = pass_count / task_count if task_count else 0.0

    return {
        "task_count": task_count,
        "pass_count": pass_count,
        "score": score,
        "per_task": per_task,
        "timing_ms": {
            "total": total_ms,
            "avg_per_task": int(total_ms / task_count) if task_count else 0,
            "max_parallel": workers,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run deterministic RLM eval harness tasks")
    p.add_argument("--dataset", default="sniah", choices=["sniah", "oolong", "browsecomp", "longbench"])
    p.add_argument("--n", type=int, default=10, help="Number of tasks")
    p.add_argument("--length", type=int, default=4_000, help="Synthetic length for S-NIAH")
    p.add_argument("--split", default="trec_coarse", help="Dataset split (OOLONG)")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--max-parallel", type=int, default=1)
    p.add_argument("--tools-sequence-hint", default=None)
    return p


def _load_cli_tasks(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.dataset == "sniah":
        return load_dataset_tasks("sniah", n=args.n, length=args.length, seed=args.seed)
    if args.dataset == "oolong":
        return load_dataset_tasks("oolong", n=args.n, split=args.split, seed=args.seed)
    return load_dataset_tasks(args.dataset, n=args.n, split=args.split, seed=args.seed)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    tasks = _load_cli_tasks(args)
    report = run_eval(tasks, tools_sequence_hint=args.tools_sequence_hint, max_parallel=args.max_parallel)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
