"""Naive baseline runner for CDNA4 ISA benchmark questions."""

from __future__ import annotations

import argparse
from pathlib import Path

import common

METHOD = "baseline"
TRUNCATED_TOKENS = 180_000
TRUNCATED_CHAR_LIMIT = TRUNCATED_TOKENS * 4
METHOD_NOTES = "truncated first 720KB of 920KB"


def build_prompt(*, isa_excerpt: str, question: dict[str, str]) -> str:
    return (
        "You are answering technical questions about the AMD CDNA4 ISA.\n"
        "Context below is only the first ~180k tokens (~720KB) of a 920KB source file.\n"
        "If the answer requires content after this point, say UNKNOWN.\n"
        "Answer in 2-6 concise sentences with direct facts only.\n\n"
        "[ISA_EXCERPT_BEGIN]\n"
        f"{isa_excerpt}\n"
        "[ISA_EXCERPT_END]\n\n"
        f"Question ID: {question['id']}\n"
        f"Section: {question['section']}\n"
        f"Question: {question['question']}\n\n"
        "Final answer:\n"
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


def main() -> int:
    args = parse_args()

    questions = common.load_questions(args.questions)
    selected = common.select_questions(
        questions,
        subset=args.subset,
        question_id=args.question_id,
    )

    isa_text = Path(args.isa_path).read_text(encoding="utf-8", errors="replace")
    isa_excerpt = isa_text[:TRUNCATED_CHAR_LIMIT]

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

        prompt = build_prompt(isa_excerpt=isa_excerpt, question=question)
        run = common.run_codex_exec(prompt, cwd=common.REPO_ROOT)

        answer = run.get("answer", "")
        status = run.get("status", "error")
        latency_ms = float(run.get("latency_ms", 0.0))
        latency_s = latency_ms / 1000.0

        payload: dict[str, object] = {
            "answer": answer,
            "method_notes": METHOD_NOTES,
            "latency_ms": latency_ms,
            "tokens_in_estimated": common.estimate_tokens(prompt),
            "tokens_out_estimated": common.estimate_tokens(answer),
            "command_used": run.get("command_used", ""),
            "status": status,
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
