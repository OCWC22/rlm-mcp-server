#!/usr/bin/env python3
"""Trace inspection utility for rlm-repl-mcp JSONL traces."""
from __future__ import annotations

import argparse
import json
import os
from collections import deque
from pathlib import Path
from typing import Iterable


def _safe_id(session_id: str) -> str:
    cleaned = "".join(c for c in session_id if c.isalnum() or c in "._-")
    return cleaned or "default"


def _trace_dir() -> Path:
    state_dir = Path(os.environ.get("RLM_STATE_DIR", Path.home() / ".cache" / "rlm-mcp"))
    trace_dir_env = os.environ.get("RLM_TRACE_DIR")
    return Path(trace_dir_env).expanduser() if trace_dir_env else (state_dir / "traces")


def _iter_trace_files(session_id: str | None = None) -> Iterable[Path]:
    root = _trace_dir()
    if not root.exists():
        return []
    if session_id:
        prefix = f"{_safe_id(session_id)}-"
        return sorted(p for p in root.glob("*.jsonl") if p.name.startswith(prefix))
    return sorted(root.glob("*.jsonl"))


def _count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def cmd_ls(_: argparse.Namespace) -> int:
    files = list(_iter_trace_files())
    if not files:
        print(f"No trace files found in {_trace_dir()}")
        return 0

    print(f"Trace dir: {_trace_dir()}")
    for p in files:
        print(f"{p.name}\tsize={p.stat().st_size}\tlines={_count_lines(p)}")
    return 0


def cmd_tail(args: argparse.Namespace) -> int:
    files = list(_iter_trace_files(args.session))
    if not files:
        print("No matching trace files")
        return 0

    buf: deque[dict] = deque(maxlen=args.n)
    for p in files:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    record = {"_decode_error": True, "raw": line}
                record["_file"] = p.name
                buf.append(record)

    for rec in buf:
        print(json.dumps(rec, indent=2, ensure_ascii=False))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    files = list(_iter_trace_files())
    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with out_path.open("w", encoding="utf-8") as out:
        for p in files:
            with p.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line:
                        continue
                    out.write(line + "\n")
                    written += 1

    print(f"Exported {written} records to {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rlm-trace", description="Inspect rlm-mcp JSONL traces")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_ls = sub.add_parser("ls", help="List trace files with size and line count")
    p_ls.set_defaults(func=cmd_ls)

    p_tail = sub.add_parser("tail", help="Pretty-print last N records")
    p_tail.add_argument("-n", type=int, default=10, help="Number of records to print")
    p_tail.add_argument("--session", default=None, help="Filter to a session id")
    p_tail.set_defaults(func=cmd_tail)

    p_export = sub.add_parser("export", help="Concatenate traces into a single JSONL file")
    p_export.add_argument("out", help="Output JSONL path")
    p_export.set_defaults(func=cmd_export)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
