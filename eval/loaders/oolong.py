"""Loader for alexbertsch/oolong (trec_coarse split by default)."""

from __future__ import annotations

from typing import Any


def _first_present(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _coerce_gold(row: dict[str, Any]) -> str:
    gold = _first_present(row, ("gold", "answer", "label_text", "label", "target", "output"))
    if gold is None:
        answers = row.get("answers")
        if isinstance(answers, list) and answers:
            gold = answers[0]
    if isinstance(gold, list):
        gold = gold[0] if gold else ""
    return "" if gold is None else str(gold)


def load_tasks(n: int = 100, split: str = "trec_coarse", seed: int = 0) -> list[dict[str, Any]]:
    """Load OOLONG benchmark examples.

    Requires optional deps:
        pip install 'rlm-mcp-server[eval]'
    """
    _ = seed  # reserved for future shuffling support
    try:
        from datasets import load_dataset
    except Exception as exc:
        raise RuntimeError("datasets package required; install with: pip install 'rlm-mcp-server[eval]'") from exc

    ds = load_dataset("alexbertsch/oolong", split=split)
    limit = min(int(n), len(ds))

    tasks: list[dict[str, Any]] = []
    for idx in range(limit):
        row = dict(ds[idx])
        query = _first_present(row, ("query", "question", "prompt", "instruction"))
        context = _first_present(row, ("context", "document", "passage", "text", "input", "body"))
        tasks.append(
            {
                "task_id": f"oolong-{split}-{idx:05d}",
                "query": str(query) if query is not None else "Answer the question using the context.",
                "context": str(context) if context is not None else "",
                "gold": _coerce_gold(row),
                "metadata": {
                    "dataset": "oolong",
                    "split": split,
                    "row_index": idx,
                    "raw_keys": sorted(row.keys()),
                },
            }
        )

    return tasks
