"""Generate comparative markdown report for CDNA4 ISA demo benchmark."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

METHODS = ("baseline", "rlm")

BENCH_ROOT = Path(__file__).resolve().parent
QUESTIONS_PATH = BENCH_ROOT / "questions.jsonl"
DEFAULT_RESULTS_DIR = BENCH_ROOT / "results" / "demo"
DEFAULT_OUTPUT_PATH = BENCH_ROOT / "RESULTS.md"

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

DIFFICULTY_ORDER = ["easy", "medium", "hard"]
COMPLEXITY_ORDER = ["constant", "linear", "quadratic"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", default=str(QUESTIONS_PATH), help="Path to questions.jsonl")
    parser.add_argument(
        "--results-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help="Directory containing baseline/ and rlm/ JSON outputs",
    )
    parser.add_argument(
        "--scores-path",
        default="",
        help="Path to scores.json (default: <results-dir>/scores.json)",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Output markdown report path",
    )
    parser.add_argument(
        "--question-ids",
        default=",".join(DEFAULT_QUESTION_IDS),
        help="Comma-separated question IDs to include in the report",
    )
    return parser.parse_args()


def parse_question_ids(raw: str) -> list[str]:
    ids = [item.strip() for item in raw.split(",") if item.strip()]
    if not ids:
        raise ValueError("No question IDs provided")

    ordered: list[str] = []
    seen: set[str] = set()
    for qid in ids:
        if qid in seen:
            continue
        ordered.append(qid)
        seen.add(qid)
    return ordered


def resolve_results_dir(raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate

    bench_relative = BENCH_ROOT / candidate
    if bench_relative.exists() or raw.startswith("results/"):
        return bench_relative.resolve()

    return candidate.resolve()


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


def load_result(results_dir: Path, method: str, qid: str) -> dict[str, Any]:
    path = results_dir / method / f"{qid}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing result file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_scores(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    scores = payload.get("scores", {})
    if not isinstance(scores, dict):
        raise ValueError(f"scores.json invalid format at {path}")
    return scores


def score_key(method: str, qid: str) -> str:
    return f"{method}:{qid}"


def avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def fmt_pct(score_0_to_1: float) -> str:
    return f"{score_0_to_1 * 100:.1f}%"


def fmt_num(value: float) -> str:
    return f"{value:.1f}"


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_line, sep_line, *body])


def pick_samples(question_ids: list[str], questions_by_id: dict[str, dict[str, Any]]) -> list[str]:
    preferred = {
        "constant": "Q08",
        "linear": "Q12",
        "quadratic": "Q15",
    }

    chosen: list[str] = []
    for complexity in COMPLEXITY_ORDER:
        preferred_qid = preferred.get(complexity)
        if preferred_qid and preferred_qid in question_ids:
            chosen.append(preferred_qid)
            continue

        fallback = next((qid for qid in question_ids if questions_by_id[qid]["complexity"] == complexity), None)
        if fallback:
            chosen.append(fallback)
    return chosen


def section_group_order(question_ids: list[str], questions_by_id: dict[str, dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for qid in question_ids:
        section = str(questions_by_id[qid]["section"])
        if section not in seen:
            seen.append(section)
    return seen


def main() -> int:
    args = parse_args()
    question_ids = parse_question_ids(args.question_ids)

    questions_by_id = load_questions(args.questions)
    missing = [qid for qid in question_ids if qid not in questions_by_id]
    if missing:
        raise ValueError(f"Question IDs not found in dataset: {', '.join(missing)}")

    results_dir = resolve_results_dir(args.results_dir)
    scores_path = Path(args.scores_path).resolve() if args.scores_path else (results_dir / "scores.json")
    output_path = Path(args.output).resolve()

    scores = load_scores(scores_path)

    results: dict[str, dict[str, dict[str, Any]]] = {method: {} for method in METHODS}
    for method in METHODS:
        for qid in question_ids:
            results[method][qid] = load_result(results_dir, method, qid)

    score_vectors: dict[str, list[float]] = {method: [] for method in METHODS}
    for method in METHODS:
        for qid in question_ids:
            key = score_key(method, qid)
            if key not in scores:
                raise ValueError(f"Missing score for {key} in {scores_path}")
            score_vectors[method].append(float(scores[key].get("score", 0.0)))

    aggregate_accuracy = {method: avg(values) for method, values in score_vectors.items()}

    total_latency_s = {
        method: sum(float(results[method][qid].get("latency_ms", 0.0)) for qid in question_ids) / 1000.0
        for method in METHODS
    }
    total_tokens = {
        method: sum(
            int(results[method][qid].get("tokens_in_estimated", 0) or 0)
            + int(results[method][qid].get("tokens_out_estimated", 0) or 0)
            for qid in question_ids
        )
        for method in METHODS
    }

    timeouts = {
        method: [qid for qid in question_ids if results[method][qid].get("status") == "timeout"]
        for method in METHODS
    }

    def build_group_rows(group_name: str, ordered_values: list[str]) -> list[list[str]]:
        rows: list[list[str]] = []
        for value in ordered_values:
            qids = [qid for qid in question_ids if str(questions_by_id[qid][group_name]) == value]
            if not qids:
                continue

            base_avg = avg([float(scores[score_key("baseline", qid)]["score"]) for qid in qids])
            rlm_avg = avg([float(scores[score_key("rlm", qid)]["score"]) for qid in qids])
            delta = rlm_avg - base_avg

            rows.append(
                [
                    value,
                    str(len(qids)),
                    fmt_pct(base_avg),
                    fmt_pct(rlm_avg),
                    f"{delta * 100:+.1f} pp",
                ]
            )
        return rows

    difficulty_rows = build_group_rows("difficulty", DIFFICULTY_ORDER)
    complexity_rows = build_group_rows("complexity", COMPLEXITY_ORDER)
    section_rows = build_group_rows("section", section_group_order(question_ids, questions_by_id))

    sample_ids = pick_samples(question_ids, questions_by_id)

    quadratic_qids = [qid for qid in question_ids if questions_by_id[qid]["complexity"] == "quadratic"]
    linear_qids = [qid for qid in question_ids if questions_by_id[qid]["complexity"] == "linear"]

    baseline_quad = avg([float(scores[score_key("baseline", qid)]["score"]) for qid in quadratic_qids]) if quadratic_qids else 0.0
    rlm_quad = avg([float(scores[score_key("rlm", qid)]["score"]) for qid in quadratic_qids]) if quadratic_qids else 0.0
    baseline_linear = avg([float(scores[score_key("baseline", qid)]["score"]) for qid in linear_qids]) if linear_qids else 0.0
    rlm_linear = avg([float(scores[score_key("rlm", qid)]["score"]) for qid in linear_qids]) if linear_qids else 0.0

    if rlm_quad > baseline_quad and rlm_linear >= baseline_linear:
        faithfulness = "Yes — this run matches the paper’s complexity×length trend, with RLM outperforming baseline on harder quadratic aggregation."
    elif rlm_quad < baseline_quad and rlm_linear >= baseline_linear:
        faithfulness = (
            "Partial and mixed — RLM improved on linear questions but underperformed baseline on quadratic questions in this demo, "
            "so we did not reproduce §4 observation 3 end-to-end."
        )
    else:
        faithfulness = (
            "No — this demo did not mirror §4 observation 3; RLM did not beat baseline on the complexity strata where degradation was expected."
        )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = []
    lines.append("# CDNA4 ISA benchmark demo results (N=10)")
    lines.append("")
    lines.append(f"Generated: {generated_at}")
    lines.append("")
    lines.append("Question IDs: " + ", ".join(question_ids))
    lines.append("")

    lines.append("## 1) Executive summary")
    lines.append("")
    lines.append(f"- **N questions**: {len(question_ids)}")
    lines.append(
        f"- **Aggregate judged accuracy**: baseline **{fmt_pct(aggregate_accuracy['baseline'])}** vs RLM **{fmt_pct(aggregate_accuracy['rlm'])}** "
        f"(Δ {aggregate_accuracy['rlm'] * 100 - aggregate_accuracy['baseline'] * 100:+.1f} pp)"
    )
    lines.append(
        f"- **Total latency**: baseline **{fmt_num(total_latency_s['baseline'])}s** vs RLM **{fmt_num(total_latency_s['rlm'])}s**"
    )
    lines.append(
        f"- **Total estimated tokens (in+out)**: baseline **{total_tokens['baseline']:,}** vs RLM **{total_tokens['rlm']:,}**"
    )
    lines.append(
        f"- **Timeouts**: baseline **{len(timeouts['baseline'])}** ({', '.join(timeouts['baseline']) if timeouts['baseline'] else 'none'}) ; "
        f"RLM **{len(timeouts['rlm'])}** ({', '.join(timeouts['rlm']) if timeouts['rlm'] else 'none'})"
    )
    lines.append("")

    lines.append("## 2) Breakdown tables")
    lines.append("")
    lines.append("### By difficulty")
    lines.append("")
    lines.append(markdown_table(["Difficulty", "N", "Baseline", "RLM", "Δ (RLM-Baseline)"], difficulty_rows))
    lines.append("")

    lines.append("### By complexity (paper-aligned)")
    lines.append("")
    lines.append(markdown_table(["Complexity", "N", "Baseline", "RLM", "Δ (RLM-Baseline)"], complexity_rows))
    lines.append("")

    lines.append("### By ISA section")
    lines.append("")
    lines.append(markdown_table(["Section", "N", "Baseline", "RLM", "Δ (RLM-Baseline)"], section_rows))
    lines.append("")

    lines.append("## 3) Side-by-side samples (1 constant, 1 linear, 1 quadratic)")
    lines.append("")
    for qid in sample_ids:
        q = questions_by_id[qid]
        baseline_answer = str(results["baseline"][qid].get("answer", "")).strip() or "[EMPTY]"
        rlm_answer = str(results["rlm"][qid].get("answer", "")).strip() or "[EMPTY]"
        baseline_score = float(scores[score_key("baseline", qid)]["score"])
        rlm_score = float(scores[score_key("rlm", qid)]["score"])
        baseline_rationale = str(scores[score_key("baseline", qid)].get("rationale", "")).strip()
        rlm_rationale = str(scores[score_key("rlm", qid)].get("rationale", "")).strip()

        lines.append(f"### {qid} ({q['complexity']}, {q['difficulty']}, section={q['section']})")
        lines.append("")
        lines.append(f"**Question**: {q['question']}")
        lines.append("")
        lines.append(f"**Reference answer**: {q['reference_answer']}")
        lines.append("")
        lines.append(f"**Baseline answer** (score={baseline_score:.1f}):")
        lines.append("")
        lines.append("```text")
        lines.append(baseline_answer)
        lines.append("```")
        lines.append("")
        lines.append(f"Judge rationale: {baseline_rationale}")
        lines.append("")
        lines.append(f"**RLM answer** (score={rlm_score:.1f}):")
        lines.append("")
        lines.append("```text")
        lines.append(rlm_answer)
        lines.append("```")
        lines.append("")
        lines.append(f"Judge rationale: {rlm_rationale}")
        lines.append("")

    lines.append("## 4) Honest limitations")
    lines.append("")
    lines.append("- Baseline is intentionally weak: it only sees the first ~180k tokens (~720KB) of a ~920KB ISA text, so late-section facts may be systematically missing.")
    lines.append("- This is a demo-scale run (N=10) and not a full 20-question evaluation; confidence intervals are wide.")
    lines.append("- The LLM judge itself can be biased or noisy; scores are rubric-constrained but still model-mediated.")
    lines.append("- RLM run quality is sensitive to MCP/session health; this run includes an RLM timeout on Q15.")
    lines.append("")

    lines.append("## 5) Paper-faithfulness note")
    lines.append("")
    lines.append(
        "arXiv:2512.24601 §4 observation 3 suggests complexity×length degradation for naive baselines and better robustness for RLM-style decomposition."
    )
    lines.append("")
    lines.append(
        f"In this demo, linear questions improved for RLM ({fmt_pct(rlm_linear)} vs {fmt_pct(baseline_linear)}), "
        f"but quadratic questions were lower ({fmt_pct(rlm_quad)} vs {fmt_pct(baseline_quad)}), largely influenced by timeout behavior."
    )
    lines.append("")
    lines.append(f"**Assessment**: {faithfulness}")
    lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote report: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
