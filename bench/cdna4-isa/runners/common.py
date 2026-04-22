from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BENCH_ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = BENCH_ROOT / "questions.jsonl"
RESULTS_ROOT = BENCH_ROOT / "results"

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
    with questions_path.open() as f:
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
    with out_path.open("w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")

    return out_path
