"""LLM judge scoring pipeline for CDNA4 ISA benchmark demo results."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

METHODS = ("baseline", "rlm")
ALLOWED_SCORES = {0.0, 0.5, 1.0}

BENCH_ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = BENCH_ROOT / "questions.jsonl"
DEFAULT_RESULTS_DIR = BENCH_ROOT / "results" / "demo"
DEFAULT_SCORES_PATH = DEFAULT_RESULTS_DIR / "scores.json"

CODEX_COMMAND_PREFIX = [
    "codex",
    "exec",
    "--skip-git-repo-check",
    "--dangerously-bypass-approvals-and-sandbox",
]
CODEX_TIMEOUT_SECONDS = 180

DEFAULT_QUESTION_IDS = [
    "Q01",
    "Q02",
    "Q05",
    "Q08",
    "Q10",
    "Q12",
    "Q14",
    "Q15",
    "Q16",
    "Q18",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--questions",
        default=str(QUESTIONS_PATH),
        help="Path to questions.jsonl",
    )
    parser.add_argument(
        "--results-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help="Directory containing baseline/ and rlm/ result JSON files",
    )
    parser.add_argument(
        "--scores-path",
        default="",
        help="Path to scores.json cache (default: <results-dir>/scores.json)",
    )
    parser.add_argument(
        "--question-ids",
        default=",".join(DEFAULT_QUESTION_IDS),
        help="Comma-separated question IDs to score",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-judge entries even if present in cache",
    )
    return parser.parse_args()


def parse_question_ids(raw: str) -> list[str]:
    ids = [item.strip() for item in raw.split(",") if item.strip()]
    if not ids:
        raise ValueError("No question IDs provided")
    # Deduplicate while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for qid in ids:
        if qid not in seen:
            ordered.append(qid)
            seen.add(qid)
    return ordered


def load_questions(path: str | Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with Path(path).open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            qid = str(row.get("id", ""))
            if not qid:
                raise ValueError(f"{path}:{lineno} missing id")
            rows[qid] = row
    return rows


def load_candidate_answer(results_dir: Path, method: str, qid: str) -> dict[str, Any]:
    result_path = results_dir / method / f"{qid}.json"
    if not result_path.exists():
        raise FileNotFoundError(f"Missing result file: {result_path}")
    return json.loads(result_path.read_text(encoding="utf-8"))


def load_scores_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"metadata": {}, "scores": {}}

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"metadata": {}, "scores": {}}

    if "scores" not in payload or not isinstance(payload["scores"], dict):
        payload["scores"] = {}
    if "metadata" not in payload or not isinstance(payload["metadata"], dict):
        payload["metadata"] = {}

    return payload


def write_scores_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def build_prompt(*, question: dict[str, Any], method: str, answer_payload: dict[str, Any]) -> str:
    candidate_answer = str(answer_payload.get("answer", "")).strip()
    status = str(answer_payload.get("status", "unknown"))
    method_notes = str(answer_payload.get("method_notes", ""))
    keywords = question.get("keywords_for_scoring", [])
    keywords_text = ", ".join(str(item) for item in keywords)

    return (
        "You are grading one benchmark answer against a reference.\n"
        "Use only this rubric: 1.0 = fully correct and complete; 0.5 = partially correct; 0.0 = incorrect or missing.\n"
        "Respond with strict JSON only: {\"score\": <0.0|0.5|1.0>, \"rationale\": \"<one sentence>\"}.\n"
        "Keep rationale to one sentence.\n\n"
        f"Question ID: {question['id']}\n"
        f"Question: {question['question']}\n"
        f"Reference answer: {question['reference_answer']}\n"
        f"Keywords for scoring: {keywords_text}\n\n"
        f"Candidate method: {method}\n"
        (f"Candidate status: {status}\n"
         f"Candidate method notes: {method_notes}\n") if status != "ok" else ""
        f"Candidate answer: {candidate_answer if candidate_answer else '[EMPTY]'}\n"
    )


def run_codex_exec(prompt: str, *, timeout_seconds: int = CODEX_TIMEOUT_SECONDS, cwd: Path | None = None) -> dict[str, Any]:
    safe_timeout = min(timeout_seconds, CODEX_TIMEOUT_SECONDS)
    command = [*CODEX_COMMAND_PREFIX, "-"]

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
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "status": "timeout",
            "answer": stdout.strip(),
            "stderr": stderr.strip(),
            "latency_ms": latency_ms,
            "returncode": None,
        }
    except Exception as exc:  # noqa: BLE001
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        return {
            "status": "error",
            "answer": "",
            "stderr": f"{type(exc).__name__}: {exc}",
            "latency_ms": latency_ms,
            "returncode": None,
        }

    latency_ms = round((time.monotonic() - started) * 1000, 2)
    return {
        "status": "ok" if proc.returncode == 0 else "error",
        "answer": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "latency_ms": latency_ms,
        "returncode": proc.returncode,
    }


def extract_json_block(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if not candidate:
        raise ValueError("Empty judge response")

    # Best case: entire output is JSON.
    try:
        payload = json.loads(candidate)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    # Fallback: first object-like block.
    match = re.search(r"\{[\s\S]*\}", candidate)
    if not match:
        raise ValueError("No JSON object found in judge response")

    payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("Judge JSON payload is not an object")
    return payload


def normalize_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid score value: {value!r}") from exc

    if score in ALLOWED_SCORES:
        return score

    closest = min(ALLOWED_SCORES, key=lambda allowed: abs(allowed - score))
    return float(closest)


def judge_answer(
    *,
    question: dict[str, Any],
    method: str,
    answer: str,
    status: str = "ok",
    method_notes: str = "",
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Judge one candidate answer and return normalized score + rationale."""

    answer_payload = {
        "answer": answer,
        "status": status,
        "method_notes": method_notes,
    }
    prompt = build_prompt(question=question, method=method, answer_payload=answer_payload)
    run = run_codex_exec(prompt, cwd=cwd or BENCH_ROOT.parents[1])

    judge_status = str(run.get("status", "error"))
    judge_raw = str(run.get("answer", "")).strip()
    judge_stderr = str(run.get("stderr", "")).strip()

    score = 0.0
    rationale = "Judge call failed; assigned 0.0 by fallback."
    parse_error = ""

    if judge_status == "ok":
        try:
            payload = extract_json_block(judge_raw)
            score = normalize_score(payload.get("score"))
            rationale = str(payload.get("rationale", "")).strip() or "No rationale provided by judge."
        except Exception as exc:  # noqa: BLE001
            parse_error = f"{type(exc).__name__}: {exc}"
            rationale = "Judge output parsing failed; assigned 0.0 by fallback."
    elif judge_status == "timeout":
        rationale = "Judge call timed out; assigned 0.0 by fallback."

    result: dict[str, Any] = {
        "score": score,
        "rationale": rationale,
        "judge_status": judge_status,
        "judge_latency_ms": float(run.get("latency_ms", 0.0)),
        "judge_raw": judge_raw,
    }

    if judge_stderr:
        result["judge_stderr"] = judge_stderr[:4000]
    if parse_error:
        result["parse_error"] = parse_error

    return result


def key_for(method: str, qid: str) -> str:
    return f"{method}:{qid}"


def resolve_results_dir(raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate

    # Common invocation from repo root passes "results/demo".
    bench_relative = BENCH_ROOT / candidate
    if bench_relative.exists() or raw.startswith("results/"):
        return bench_relative.resolve()

    return candidate.resolve()


def main() -> int:
    args = parse_args()
    results_dir = resolve_results_dir(args.results_dir)
    question_ids = parse_question_ids(args.question_ids)
    questions_by_id = load_questions(args.questions)

    missing = [qid for qid in question_ids if qid not in questions_by_id]
    if missing:
        raise ValueError(f"Question IDs not found in dataset: {', '.join(missing)}")

    scores_path = Path(args.scores_path).resolve() if args.scores_path else (results_dir / "scores.json")
    cache = load_scores_cache(scores_path)
    scores = cache["scores"]

    total = len(question_ids) * len(METHODS)
    done = 0

    for qid in question_ids:
        question = questions_by_id[qid]
        for method in METHODS:
            done += 1
            cache_key = key_for(method, qid)
            if cache_key in scores and not args.force:
                print(f"[{done}/{total}] {cache_key} ... cached")
                continue

            answer_payload = load_candidate_answer(results_dir, method, qid)
            prompt = build_prompt(question=question, method=method, answer_payload=answer_payload)
            run = run_codex_exec(prompt, cwd=BENCH_ROOT.parents[1])

            judged_at = datetime.now(timezone.utc).isoformat()
            judge_status = run.get("status", "error")
            judge_raw = str(run.get("answer", "")).strip()
            judge_stderr = str(run.get("stderr", "")).strip()

            score = 0.0
            rationale = "Judge call failed; assigned 0.0 by fallback."
            parse_error = ""

            if judge_status == "ok":
                try:
                    payload = extract_json_block(judge_raw)
                    score = normalize_score(payload.get("score"))
                    rationale = str(payload.get("rationale", "")).strip() or "No rationale provided by judge."
                except Exception as exc:  # noqa: BLE001
                    parse_error = f"{type(exc).__name__}: {exc}"
                    rationale = "Judge output parsing failed; assigned 0.0 by fallback."
            elif judge_status == "timeout":
                rationale = "Judge call timed out; assigned 0.0 by fallback."

            entry: dict[str, Any] = {
                "method": method,
                "question_id": qid,
                "score": score,
                "rationale": rationale,
                "candidate_status": answer_payload.get("status", "unknown"),
                "judge_status": judge_status,
                "judge_latency_ms": float(run.get("latency_ms", 0.0)),
                "judge_raw": judge_raw,
                "judged_at_utc": judged_at,
            }

            if judge_stderr:
                entry["judge_stderr"] = judge_stderr[:4000]
            if parse_error:
                entry["parse_error"] = parse_error

            scores[cache_key] = entry
            print(f"[{done}/{total}] {cache_key} ... score={score:.1f} ({judge_status})")

            cache["metadata"] = {
                "updated_at_utc": judged_at,
                "results_dir": str(results_dir),
                "scores_path": str(scores_path),
                "question_ids": question_ids,
                "methods": list(METHODS),
                "score_scale": [0.0, 0.5, 1.0],
                "judge_invocation": "codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox -",
            }
            write_scores_cache(scores_path, cache)

    # Final write to keep metadata fresh even when fully cached.
    cache["metadata"] = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "results_dir": str(results_dir),
        "scores_path": str(scores_path),
        "question_ids": question_ids,
        "methods": list(METHODS),
        "score_scale": [0.0, 0.5, 1.0],
        "judge_invocation": "codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox -",
    }
    write_scores_cache(scores_path, cache)

    print(f"Wrote scores cache: {scores_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
