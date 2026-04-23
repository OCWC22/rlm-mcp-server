from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path
from typing import Any

from .legacy_metrics import eval_harness_metric, score
from .signatures import RLMToolSelection, make_student_module
from .trace_to_dataset import load_trainset

METRICS = {
    "heuristic": score,
    "eval": eval_harness_metric,
}


def _import_dspy_gepa():
    try:
        import dspy
    except Exception as exc:
        raise RuntimeError(
            "DSPy is not installed. Install optional deps: pip install 'rlm-mcp-server[gepa]'"
        ) from exc

    GEPA = getattr(dspy, "GEPA", None)
    if GEPA is None:
        try:
            from dspy.teleprompt.gepa.gepa import GEPA as GEPAFallback  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "Could not import GEPA from DSPy. Expected dspy.GEPA or dspy.teleprompt.gepa.gepa.GEPA"
            ) from exc
        GEPA = GEPAFallback

    return dspy, GEPA


def _build_optimizer(GEPA: Any, metric_fn: Any, num_threads: int, max_calls: int):
    kwargs = {"metric": metric_fn, "num_threads": num_threads}
    params = inspect.signature(GEPA).parameters
    if "max_metric_calls" in params:
        kwargs["max_metric_calls"] = max_calls
    elif "max_calls" in params:
        kwargs["max_calls"] = max_calls
    return GEPA(**kwargs)


def run(
    trainset_path: str | Path,
    out_path: str | Path,
    lm_name: str,
    num_threads: int,
    max_calls: int,
    metric_name: str = "heuristic",
) -> int:
    trainset = load_trainset(trainset_path)
    if not trainset:
        print("No training examples produced from trace file.", file=sys.stderr)
        return 2

    metric_fn = METRICS.get(metric_name)
    if metric_fn is None:
        print(f"Unknown metric {metric_name!r}; choose one of: {', '.join(sorted(METRICS))}", file=sys.stderr)
        return 2

    try:
        dspy, GEPA = _import_dspy_gepa()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    dspy.configure(lm=dspy.LM(lm_name))

    try:
        student = make_student_module()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    optimizer = _build_optimizer(GEPA, metric_fn, num_threads=num_threads, max_calls=max_calls)
    compiled = optimizer.compile(student=student, trainset=trainset)

    out = Path(out_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(compiled, "save"):
        compiled.save(str(out))
        print(f"Saved compiled GEPA artifact to {out}")
    else:
        out.write_text(json.dumps({"repr": repr(compiled)}, indent=2), encoding="utf-8")
        print(f"Compiled object has no .save(); wrote repr scaffold to {out}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run GEPA scaffold optimization over exported RLM traces")
    p.add_argument("--trainset", required=True, help="Path to JSONL file from `rlm-trace export`")
    p.add_argument("--out", default="gepa/compiled/tool_descriptions.json", help="Output path")
    p.add_argument("--lm", default="openai/gpt-4o-mini", help="DSPy LM identifier")
    p.add_argument("--num-threads", type=int, default=4)
    p.add_argument("--max-calls", type=int, default=50)
    p.add_argument("--metric", choices=sorted(METRICS), default="heuristic", help="Metric mode")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _ = RLMToolSelection  # explicit touch so import remains visible in scaffold
    return run(
        trainset_path=args.trainset,
        out_path=args.out,
        lm_name=args.lm,
        num_threads=args.num_threads,
        max_calls=args.max_calls,
        metric_name=args.metric,
    )


if __name__ == "__main__":
    raise SystemExit(main())
