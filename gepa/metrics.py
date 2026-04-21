from __future__ import annotations

from typing import Any


def _peek_span(rec: dict[str, Any]) -> int:
    inp = rec.get("input") if isinstance(rec.get("input"), dict) else {}
    s, e = inp.get("start", 0), inp.get("end", 0)
    return max(0, e - s) if isinstance(s, int) and isinstance(e, int) else 0


def _context_length(records: list[dict[str, Any]]) -> int:
    for rec in records:
        if rec.get("tool") == "rlm_init":
            out = rec.get("output") if isinstance(rec.get("output"), dict) else {}
            if isinstance(out.get("chars"), int):
                return int(out["chars"])
    return 0


def _coerce_records(obj: Any) -> list[dict[str, Any]]:
    if isinstance(obj, list) and all(isinstance(x, dict) for x in obj):
        return obj
    if isinstance(obj, dict) and isinstance(obj.get("records"), list):
        recs = obj["records"]
        return recs if all(isinstance(x, dict) for x in recs) else []
    recs = getattr(obj, "records", None)
    if isinstance(recs, list) and all(isinstance(x, dict) for x in recs):
        return recs
    return []


def score_session_trace(records: list[dict[str, Any]]) -> float:
    if not records:
        return 0.0
    tools = [str(r.get("tool", "")) for r in records]
    score = 0.0

    if tools and tools[0] == "rlm_init" and tools.count("rlm_init") == 1:
        score += 0.25

    huge_peeks = [i for i, r in enumerate(records) if r.get("tool") == "rlm_peek" and _peek_span(r) > 50_000]
    if not huge_peeks or {"rlm_exec", "rlm_grep"} & set(tools[: huge_peeks[0]]):
        score += 0.25

    has_subquery = "rlm_sub_query" in tools or any(
        r.get("tool") == "rlm_exec"
        and isinstance(r.get("input"), dict)
        and isinstance(r["input"].get("code"), str)
        and "llm_query(" in r["input"]["code"]
        for r in records
    )
    if _context_length(records) <= 50_000 or has_subquery:
        score += 0.25

    if tools.count("rlm_peek") <= 3:
        score += 0.25

    return max(0.0, min(1.0, round(score, 3)))


def score(gold: Any, pred: Any = None, trace: Any = None, pred_name: str | None = None, pred_trace: Any = None) -> float:
    """GEPA-compatible scaffold metric (replace for real optimization work)."""
    _ = (pred, trace, pred_name, pred_trace)
    return score_session_trace(_coerce_records(gold))
