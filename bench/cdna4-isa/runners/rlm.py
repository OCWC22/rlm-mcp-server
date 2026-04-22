"""RLM-driven runner for CDNA4 ISA benchmark questions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import common

METHOD = "rlm"
TRACE_ROOT = Path.home() / ".cache" / "rlm-mcp" / "traces"
METHOD_NOTES = "RLM tool flow: rlm_init -> rlm_grep/rlm_peek -> optional rlm_exec(llm_query)"


def build_prompt(*, isa_path: Path, session_id: str, question: dict[str, str]) -> str:
    return (
        "Use the rlm MCP tools to answer this question from the CDNA4 ISA corpus.\n"
        "Do not answer from memory; ground your answer in tool calls.\n"
        f"Session ID: {session_id}\n"
        f"ISA path (absolute): {isa_path}\n\n"
        "Required sequence:\n"
        f"1) rlm_init(path=\"{isa_path}\", session_id=\"{session_id}\")\n"
        f"2) rlm_grep(pattern=<good keyword regex>, session_id=\"{session_id}\")\n"
        f"3) rlm_peek(...) around the strongest hits with session_id=\"{session_id}\"\n"
        "4) If still uncertain, call rlm_exec with Python code that loops through candidate spans and uses llm_query(...) for synthesis.\n\n"
        f"Question ID: {question['id']}\n"
        f"Section: {question['section']}\n"
        f"Question: {question['question']}\n\n"
        "Output only the final answer text. If evidence is insufficient, respond UNKNOWN.\n"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", default=str(common.QUESTIONS_PATH), help="Path to questions.jsonl")
    parser.add_argument("--isa-path", default=str(common.ISA_PATH), help="Path to full ISA text file")
    parser.add_argument("--results-dir", default=str(common.RESULTS_ROOT), help="Output root directory")
    parser.add_argument("--subset", type=int, help="Run only the first N questions")
    parser.add_argument("--question-id", help="Run only one question by ID (e.g., Q07)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing per-question result files")
    return parser.parse_args()


def find_trace_file(session_id: str) -> tuple[str, int]:
    pattern = f"{session_id}-*.jsonl"
    matches = sorted(TRACE_ROOT.glob(pattern))
    if not matches:
        return "", 0

    trace_path = matches[-1]
    try:
        line_count = sum(1 for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip())
    except Exception:  # noqa: BLE001
        line_count = 0

    return str(trace_path), line_count


def make_session_id(question_id: str) -> str:
    utc_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"cdna4-bench-{question_id}-{utc_stamp}"


def main() -> int:
    args = parse_args()
    isa_path = Path(args.isa_path).resolve()

    questions = common.load_questions(args.questions)
    selected = common.select_questions(
        questions,
        subset=args.subset,
        question_id=args.question_id,
    )

    total = len(selected)
    if total == 0:
        print("No questions selected.")
        return 0

    for idx, question in enumerate(selected, start=1):
        qid = str(question["id"])
        section = str(question["section"])
        progress_prefix = f"[{idx}/{total}] {qid} (section={section})"

        out_path = common.result_path_for(METHOD, qid, results_root=args.results_dir)
        if out_path.exists() and not args.force:
            print(f"{progress_prefix} ... skipped (exists)")
            continue

        session_id = make_session_id(qid)
        prompt = build_prompt(isa_path=isa_path, session_id=session_id, question=question)
        run = common.run_codex_exec(prompt, cwd=common.REPO_ROOT)

        answer = run.get("answer", "")
        status = run.get("status", "error")
        latency_ms = float(run.get("latency_ms", 0.0))
        latency_s = latency_ms / 1000.0

        trace_file, trace_line_count = find_trace_file(session_id)

        payload: dict[str, object] = {
            "answer": answer,
            "method_notes": METHOD_NOTES,
            "latency_ms": latency_ms,
            "tokens_in_estimated": common.estimate_tokens(prompt),
            "tokens_out_estimated": common.estimate_tokens(answer),
            "command_used": run.get("command_used", ""),
            "trace_file": trace_file,
            "trace_line_count": trace_line_count,
            "status": status,
            "session_id": session_id,
        }

        stderr = run.get("stderr", "")
        if stderr:
            payload["stderr"] = stderr

        common.write_result(METHOD, qid, payload, results_root=args.results_dir)

        if status == "timeout":
            print(f"{progress_prefix} ... timeout in {latency_s:.1f}s")
        elif status == "error":
            print(f"{progress_prefix} ... error in {latency_s:.1f}s")
        else:
            print(f"{progress_prefix} ... done in {latency_s:.1f}s")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
