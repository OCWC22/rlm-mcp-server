"""CLI driver for CDNA4 GEPA MVP.

Modes:
  --dry-run    build pipeline/program/examples/metric without LM calls
  --baseline   evaluate unoptimized program on valset
  --optimize   run GEPA compile on trainset + valset and save artifact
  --eval PATH  load saved artifact and evaluate on valset
"""

import argparse
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from bench.common.config import (
    REFLECTION_DEFAULT,
    REFLECTION_ENV,
    TASK_DEFAULT,
    TASK_ENV,
    reflection_lm,
    task_lm,
)

HERE = Path(__file__).resolve().parent
ARTIFACT_PATH = HERE / "compiled" / "cdna4_runner.json"
GEPA_LOG_DIR = HERE / "gepa_logs"
RESULTS_JSON = HERE / "results.json"
RESULTS_MD = HERE / "results.md"
VERSION_COMPARISON_JSON = HERE / "version_comparison.json"
LAST_EVAL_JSON = HERE / "last_eval.json"


def _import_pipeline():
    """Import sibling pipeline with a stable module name for GEPA pickling."""
    module_name = "cdna4_gepa_pipeline"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, HERE / "pipeline.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to import pipeline module")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _import_dspy():
    try:
        import dspy
    except Exception as exc:
        raise RuntimeError(
            "dspy is required for baseline/optimize/eval. Install DSPy 3.2.x first."
        ) from exc
    return dspy


def _read_lm_env(require_models):
    task_model = os.getenv(TASK_ENV, "").strip()
    reflection_model = os.getenv(REFLECTION_ENV, "").strip()

    if task_model and reflection_model:
        return task_model, reflection_model

    if require_models:
        raise RuntimeError(
            "Missing LM env vars. Set both "
            f"{TASK_ENV} and {REFLECTION_ENV}. Suggested defaults: "
            f"{TASK_ENV}={TASK_DEFAULT}, {REFLECTION_ENV}={REFLECTION_DEFAULT}."
        )

    print("skipping LM configure")
    return "", ""


def _configure_dspy(task_model, reflection_model):
    dspy = _import_dspy()
    configured_task_lm = task_lm(model=task_model)
    configured_reflection_lm = reflection_lm(model=reflection_model)
    dspy.configure(lm=configured_task_lm)
    return dspy, configured_task_lm, configured_reflection_lm


def _build_context():
    pipeline = _import_pipeline()
    _ = pipeline.CDNA4Signature
    program = pipeline.CDNA4Runner()
    allset = pipeline.make_examples("all")
    trainset = pipeline.make_examples("train")
    valset = pipeline.make_examples("val")
    metric = pipeline.rich_metric
    return pipeline, program, allset, trainset, valset, metric


def _make_evaluator(dspy, valset, metric):
    return dspy.Evaluate(
        devset=valset,
        metric=metric,
        num_threads=1,
        display_progress=True,
        provide_traceback=True,
        failure_score=0.0,
        save_as_json=str(LAST_EVAL_JSON),
    )


def _write_results_md(results):
    if "optimized_score" in results:
        delta = float(results["optimized_score"]) - float(results.get("baseline_score", 0.0))
        RESULTS_MD.write_text(
            "\n".join(
                [
                    "# CDNA4 GEPA Results",
                    "",
                    "| Metric | Baseline | Optimized | Δ |",
                    "|---|---:|---:|---:|",
                    f"| Overall | {float(results['baseline_score']):.3f} | {float(results['optimized_score']):.3f} | **{delta:+.3f}** |",
                    "",
                    f"- Task LM: `{results['task_model']}`",
                    f"- Reflection LM: `{results['reflection_model']}`",
                    "- GEPA mode: `auto=\"light\"`, seed=0",
                    f"- Trainset: {results['trainset_size']} · valset: {results['valset_size']}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return

    RESULTS_MD.write_text(
        "\n".join(
            [
                "# CDNA4 GEPA Eval Results",
                "",
                f"- Artifact: `{results.get('artifact', '')}`",
                f"- Score: **{float(results.get('score', 0.0)):.3f}**",
                f"- Task LM: `{results.get('task_model', '')}`",
                f"- Reflection LM: `{results.get('reflection_model', '')}`",
                f"- Valset size: {results.get('valset_size', 0)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _read_previous_results():
    if not RESULTS_JSON.exists():
        return {}
    try:
        payload = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}


def _write_version_comparison(current, historical):
    status = "refreshed" if historical else "initial"

    payload = {
        "example": "cdna4-gepa",
        "comparison_date": datetime.now(timezone.utc).date().isoformat(),
        "status": status,
        "historical_artifact": historical,
        "current_artifact": current,
        "notes": [
            "This file follows the dspy-agent-skills version comparison convention.",
            "CDNA4 GEPA MVP uses the benchmark runner prompt as the optimized student.",
        ],
    }

    VERSION_COMPARISON_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def cmd_dry_run(_args):
    _read_lm_env(require_models=False)
    pipeline, program, allset, trainset, valset, metric = _build_context()

    print(f"signature={pipeline.CDNA4Signature.__name__}")
    print(f"program={program.__class__.__name__}")
    print(f"examples(all/train/val)={len(allset)}/{len(trainset)}/{len(valset)}")
    print(f"metric={metric.__name__}")
    print("OK dry-run")
    return 0


def cmd_baseline(_args):
    try:
        task_model, reflection_model = _read_lm_env(require_models=True)
        dspy, _task_lm, _reflection_lm = _configure_dspy(task_model, reflection_model)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    pipeline, program, _allset, _trainset, valset, metric = _build_context()
    evaluator = _make_evaluator(dspy, valset, metric)

    t0 = time.time()
    result = evaluator(program)
    dt = time.time() - t0

    print(f"BASELINE overall={result.score:.3f} ({dt:.1f}s over {len(valset)} examples)")
    return 0


def cmd_optimize(_args):
    try:
        task_model, reflection_model = _read_lm_env(require_models=True)
        dspy, _task_lm, reflection_lm = _configure_dspy(task_model, reflection_model)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    pipeline, program, _allset, trainset, valset, metric = _build_context()

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    GEPA_LOG_DIR.mkdir(parents=True, exist_ok=True)

    evaluator = _make_evaluator(dspy, valset, metric)

    t0 = time.time()
    baseline_score = float(evaluator(program).score)
    baseline_seconds = time.time() - t0

    optimizer = dspy.GEPA(
        metric=metric,
        auto="light",
        reflection_lm=reflection_lm,
        reflection_minibatch_size=8,
        candidate_selection_strategy="pareto",
        use_merge=True,
        track_best_outputs=True,
        log_dir=str(GEPA_LOG_DIR),
        seed=0,
        gepa_kwargs={"use_cloudpickle": True},
    )

    t1 = time.time()
    optimized = optimizer.compile(student=program, trainset=trainset, valset=valset)
    optimize_seconds = time.time() - t1

    optimized.save(str(ARTIFACT_PATH), save_program=False)

    t2 = time.time()
    optimized_score = float(evaluator(optimized).score)
    eval_seconds = time.time() - t2

    results = {
        "task_model": task_model,
        "reflection_model": reflection_model,
        "auto": "light",
        "seed": 0,
        "trainset_size": len(trainset),
        "valset_size": len(valset),
        "baseline_score": baseline_score,
        "optimized_score": optimized_score,
        "improvement": optimized_score - baseline_score,
        "baseline_seconds": round(baseline_seconds, 1),
        "optimize_seconds": round(optimize_seconds, 1),
        "eval_seconds": round(eval_seconds, 1),
        "artifact": str(ARTIFACT_PATH),
    }

    previous = _read_previous_results()
    RESULTS_JSON.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    _write_results_md(results)
    _write_version_comparison(results, previous)

    print(f"Saved optimized artifact to {ARTIFACT_PATH}")
    print(f"OPTIMIZED overall={optimized_score:.3f}")
    return 0


def cmd_eval(path):
    try:
        task_model, reflection_model = _read_lm_env(require_models=True)
        dspy, _task_lm, _reflection_lm = _configure_dspy(task_model, reflection_model)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    pipeline, program, _allset, _trainset, valset, metric = _build_context()

    artifact = Path(path)
    if not artifact.exists():
        print(f"error: artifact not found: {artifact}", file=sys.stderr)
        return 2

    program.load(str(artifact))

    evaluator = _make_evaluator(dspy, valset, metric)
    t0 = time.time()
    score = float(evaluator(program).score)
    dt = time.time() - t0

    results = {
        "task_model": task_model,
        "reflection_model": reflection_model,
        "score": score,
        "valset_size": len(valset),
        "artifact": str(artifact),
        "eval_seconds": round(dt, 1),
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    previous = _read_previous_results()
    RESULTS_JSON.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    _write_results_md(results)
    _write_version_comparison(results, previous)

    print(f"{artifact.name}: {score:.3f}")
    print(f"Wrote {RESULTS_JSON.name}, {RESULTS_MD.name}, and {VERSION_COMPARISON_JSON.name}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--baseline", action="store_true")
    group.add_argument("--optimize", action="store_true")
    group.add_argument("--eval", metavar="PATH")
    args = parser.parse_args(argv)

    if args.dry_run:
        return cmd_dry_run(args)
    if args.baseline:
        return cmd_baseline(args)
    if args.optimize:
        return cmd_optimize(args)
    if args.eval:
        return cmd_eval(args.eval)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
