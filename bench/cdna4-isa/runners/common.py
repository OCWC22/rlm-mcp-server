from __future__ import annotations

import json
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCH_ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = BENCH_ROOT / "questions.jsonl"
INPUTS_ROOT = BENCH_ROOT / "inputs"
ISA_PATH = INPUTS_ROOT / "cdna4_isa.txt"
RESULTS_ROOT = BENCH_ROOT / "results"

CODEX_COMMAND_PREFIX = [
    "codex",
    "exec",
    "--skip-git-repo-check",
    "--dangerously-bypass-approvals-and-sandbox",
]
CODEX_TIMEOUT_SECONDS = 180

# v0.7.0: per-complexity timeout — quadratic trajectories need more budget
TIMEOUT_BY_COMPLEXITY = {"constant": 180, "linear": 240, "quadratic": 420}

def timeout_for(question: dict) -> int:
    """Return per-complexity timeout, falling back to CODEX_TIMEOUT_SECONDS."""
    return TIMEOUT_BY_COMPLEXITY.get(question.get("complexity", "linear"), CODEX_TIMEOUT_SECONDS)

REQUIRED_QUESTION_FIELDS = {
    "id",
    "section",
    "difficulty",
    "complexity",
    "question",
    "reference_answer",
    "keywords_for_scoring",
}


def load_questions(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load questions from JSONL and validate required fields."""
    questions_path = Path(path) if path else QUESTIONS_PATH
    rows: list[dict[str, Any]] = []
    with questions_path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            missing = REQUIRED_QUESTION_FIELDS - set(row.keys())
            if missing:
                missing_list = ", ".join(sorted(missing))
                raise ValueError(f"{questions_path}:{lineno} missing fields: {missing_list}")
            rows.append(row)
    return rows


def select_questions(
    questions: list[dict[str, Any]],
    *,
    subset: int | None = None,
    question_id: str | None = None,
) -> list[dict[str, Any]]:
    """Apply subset / question-id selection semantics."""
    if subset is not None and subset <= 0:
        raise ValueError("--subset must be > 0")

    if question_id:
        selected = [row for row in questions if row.get("id") == question_id]
        if not selected:
            raise ValueError(f"Question ID not found: {question_id}")
        return selected

    if subset is not None:
        return questions[:subset]

    return questions


def estimate_tokens(text: str) -> int:
    """Very rough token estimate used for benchmark bookkeeping."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def result_path_for(
    method: str,
    question_id: str,
    *,
    results_root: str | Path | None = None,
) -> Path:
    root = Path(results_root) if results_root else RESULTS_ROOT
    return root / method / f"{question_id}.json"


def write_result(
    method: str,
    question_id: str,
    payload: dict[str, Any],
    *,
    results_root: str | Path | None = None,
) -> Path:
    """Write one per-question result JSON file."""
    root = Path(results_root) if results_root else RESULTS_ROOT
    output_dir = root / method
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / f"{question_id}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")

    return out_path


def _decode_timeout_stream(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def run_codex_exec(
    prompt: str,
    *,
    timeout_seconds: int = CODEX_TIMEOUT_SECONDS,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Run codex exec with stdin prompt; always enforce timeout <= 180s."""
    safe_timeout = min(timeout_seconds, CODEX_TIMEOUT_SECONDS)
    command = [*CODEX_COMMAND_PREFIX, "-"]
    command_used = shlex.join(command)

    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=safe_timeout,
            check=False,
            cwd=str(cwd) if cwd else None,
        )
    except subprocess.TimeoutExpired as exc:
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        return {
            "status": "timeout",
            "answer": _decode_timeout_stream(exc.stdout).strip(),
            "stderr": _decode_timeout_stream(exc.stderr).strip(),
            "latency_ms": latency_ms,
            "returncode": None,
            "command_used": command_used,
        }
    except Exception as exc:  # noqa: BLE001
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        return {
            "status": "error",
            "answer": "",
            "stderr": f"{type(exc).__name__}: {exc}",
            "latency_ms": latency_ms,
            "returncode": None,
            "command_used": command_used,
        }

    latency_ms = round((time.monotonic() - started) * 1000, 2)
    return {
        "status": "ok" if proc.returncode == 0 else "error",
        "answer": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "latency_ms": latency_ms,
        "returncode": proc.returncode,
        "command_used": command_used,
    }
