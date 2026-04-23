"""Regression guards for DSPy 3.2.x contract pitfalls."""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_PATH = REPO_ROOT / "bench" / "cdna4-isa" / "gepa" / "pipeline.py"
DSPY_RLM_DIR = REPO_ROOT / "dspy_rlm"
DSPY_RLM_FILES = sorted(DSPY_RLM_DIR.glob("*.py"))

METRIC_RULE_FILES = [PIPELINE_PATH, *DSPY_RLM_FILES]
OVERALL_SCORE_RULE_FILES = [PIPELINE_PATH, *DSPY_RLM_FILES]
SIGNATURE_RULE_FILES = [PIPELINE_PATH, DSPY_RLM_DIR / "signatures.py"]


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _metric_dict_offenders() -> list[str]:
    offenders: list[str] = []

    for path in METRIC_RULE_FILES:
        tree = _parse(path)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if "metric" not in fn.name.lower():
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
                    rel = path.relative_to(REPO_ROOT)
                    offenders.append(f"{rel}:{node.lineno} ({fn.name})")

    return offenders


def _overall_score_offenders() -> list[str]:
    offenders: list[str] = []

    for path in OVERALL_SCORE_RULE_FILES:
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "overall_score":
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}:{getattr(node, 'lineno', '?')}")

    return offenders


def _future_annotations_offenders() -> list[str]:
    offenders: list[str] = []

    for path in SIGNATURE_RULE_FILES:
        tree = _parse(path)
        for node in getattr(tree, "body", []):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module != "__future__":
                continue
            if any(alias.name == "annotations" for alias in node.names):
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}:{node.lineno}")

    return offenders


RULES = [
    (
        "metric_returns_prediction",
        _metric_dict_offenders,
        "Metrics must return dspy.Prediction(score=..., feedback=...).",
    ),
    (
        "no_overall_score",
        _overall_score_offenders,
        "Use EvaluationResult.score, never .overall_score.",
    ),
    (
        "no_future_annotations_in_signatures",
        _future_annotations_offenders,
        "Do not use `from __future__ import annotations` in DSPy signature files.",
    ),
]


@pytest.mark.parametrize("rule_id, checker, message", RULES, ids=lambda rule: rule)
def test_dspy_3_2_contract_rules(rule_id: str, checker, message: str):
    _ = rule_id
    offenders = checker()
    assert not offenders, message + (" Offenders: " + ", ".join(offenders) if offenders else "")
