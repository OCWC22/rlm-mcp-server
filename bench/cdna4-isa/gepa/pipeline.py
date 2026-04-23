"""CDNA4 GEPA pipeline wiring for the benchmark runner prompt."""

import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import dspy
except Exception:
    dspy = None

HERE = Path(__file__).resolve().parent
CDNA4_ROOT = HERE.parent
QUESTIONS_PATH = CDNA4_ROOT / "questions.jsonl"
ISA_PATH = CDNA4_ROOT / "inputs" / "cdna4_isa.txt"
RUNNER_COMMON_PATH = CDNA4_ROOT / "runners" / "common.py"
RUNNER_RLM_PATH = CDNA4_ROOT / "runners" / "rlm.py"
LLM_JUDGE_PATH = CDNA4_ROOT / "scoring" / "llm_judge.py"

RUNNER_SYSTEM_PROMPT = (
    "Use the rlm MCP tools to answer this question from the CDNA4 ISA corpus.\n"
    "Do not answer from memory; ground your answer in tool calls.\n"
    "Required sequence:\n"
    "1) rlm_init(path=<absolute isa path>, session_id=<session id>)\n"
    "2) rlm_grep(pattern=<good keyword regex>, session_id=<session id>)\n"
    "3) rlm_peek(...) around the strongest hits\n"
    "4) If still uncertain, call rlm_exec with Python code that loops through candidate spans and uses llm_query(...) for synthesis.\n"
    "Output only the final answer text. If evidence is insufficient, respond UNKNOWN."
)


class _ExampleShim(dict):
    """Tiny fallback shape to keep --dry-run working without DSPy installed."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def with_inputs(self, *inputs: str):
        self["_inputs"] = list(inputs)
        return self


class _PredictionShim(dict):
    """Dict-like fallback that mirrors dspy.Prediction key/attr access."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


if dspy is not None:
    try:

        class CDNA4Signature(dspy.Signature, instructions=RUNNER_SYSTEM_PROMPT):
            question: str = dspy.InputField()
            section: str = dspy.InputField()
            complexity: str = dspy.InputField()
            answer: str = dspy.OutputField(desc="final grounded answer text")
            rationale: str = dspy.OutputField(desc="brief reasoning summary")

    except TypeError:

        class CDNA4Signature(dspy.Signature):
            instructions = RUNNER_SYSTEM_PROMPT
            question: str = dspy.InputField()
            section: str = dspy.InputField()
            complexity: str = dspy.InputField()
            answer: str = dspy.OutputField(desc="final grounded answer text")
            rationale: str = dspy.OutputField(desc="brief reasoning summary")

else:

    class CDNA4Signature:  # pragma: no cover - fallback for no-dspy dry-run
        instructions = RUNNER_SYSTEM_PROMPT


def _import_file_module(module_name: str, path: Path):
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import module from {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _import_runner_common():
    return _import_file_module("cdna4_runner_common", RUNNER_COMMON_PATH)


def _import_runner_rlm():
    return _import_file_module("cdna4_runner_rlm", RUNNER_RLM_PATH)


def _import_llm_judge():
    return _import_file_module("cdna4_llm_judge", LLM_JUDGE_PATH)


def _load_question_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with QUESTIONS_PATH.open(encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _question_key(question: str, section: str, complexity: str) -> tuple[str, str, str]:
    return (question.strip(), section.strip().lower(), complexity.strip().lower())


def _id_number(question_id: str) -> int:
    match = re.search(r"(\d+)$", str(question_id))
    if not match:
        return 0
    return int(match.group(1))


def _to_example(payload: dict[str, Any]):
    if dspy is None:
        return _ExampleShim(payload).with_inputs("question", "section", "complexity")
    return dspy.Example(**payload).with_inputs("question", "section", "complexity")


if dspy is not None:

    class CDNA4Runner(dspy.Module):
        """Runner wrapper that GEPA optimizes by mutating signature instructions."""

        def __init__(self, isa_path=None):
            super().__init__()
            self._runner_common = _import_runner_common()
            self._runner_rlm = _import_runner_rlm()
            self._isa_path = Path(isa_path).resolve() if isa_path else Path(ISA_PATH).resolve()
            self._questions = _load_question_rows()
            self._questions_by_key = {
                _question_key(str(row.get("question", "")), str(row.get("section", "")), str(row.get("complexity", ""))): row
                for row in self._questions
            }

        def _lookup_question(self, *, question: str, section: str, complexity: str) -> dict[str, Any]:
            found = self._questions_by_key.get(_question_key(question, section, complexity))
            if found:
                return found

            return {
                "id": "GEPA",
                "section": section,
                "complexity": complexity,
                "question": question,
                "reference_answer": "",
                "keywords_for_scoring": [],
            }

        def forward(self, question: str, section: str, complexity: str):
            row = self._lookup_question(question=question, section=section, complexity=complexity)
            qid = str(row.get("id", "GEPA"))
            session_id = f"cdna4-gepa-{qid}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

            prompt = self._runner_rlm.build_prompt(isa_path=self._isa_path, session_id=session_id, question=row)
            run = self._runner_common.run_codex_exec(prompt, cwd=self._runner_common.REPO_ROOT)

            answer = str(run.get("answer", "")).strip() or "UNKNOWN"
            status = str(run.get("status", "error"))
            stderr = str(run.get("stderr", "")).strip()

            rationale = f"status={status}; id={qid}"
            if status != "ok" and stderr:
                rationale += f"; stderr={stderr[:240]}"

            return dspy.Prediction(answer=answer, rationale=rationale)

else:

    class CDNA4Runner:  # pragma: no cover - fallback for no-dspy dry-run
        def __init__(self, isa_path=None):
            self._isa_path = Path(isa_path).resolve() if isa_path else Path(ISA_PATH).resolve()

        def forward(self, question: str, section: str, complexity: str):
            raise RuntimeError(
                "dspy is required to run CDNA4Runner.forward(). Install dspy for baseline/optimize/eval."
            )


def _coerce_keywords(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    return []


def _keyword_misses(answer: str, keywords: list[str]) -> list[str]:
    lowered = answer.lower()
    misses: list[str] = []
    for keyword in keywords:
        if keyword.lower() not in lowered:
            misses.append(keyword)
    return misses


def rich_metric(gold, pred, trace=None, **_):
    _ = trace
    pred_answer = str(getattr(pred, "answer", "")).strip()

    question_payload = {
        "id": str(getattr(gold, "id", "GEPA")),
        "question": str(getattr(gold, "question", "")),
        "reference_answer": str(getattr(gold, "reference_answer", "")),
        "keywords_for_scoring": _coerce_keywords(getattr(gold, "keywords_for_scoring", [])),
    }

    llm_judge = _import_llm_judge()
    judged = llm_judge.judge_answer(
        question=question_payload,
        method="gepa-cdna4-runner",
        answer=pred_answer,
        status="ok" if pred_answer else "error",
        method_notes="CDNA4Runner via runners.rlm.build_prompt + run_codex_exec",
    )

    score = float(judged.get("score", 0.0))
    judge_rationale = str(judged.get("rationale", "")).strip() or "No rationale provided by judge."

    misses = _keyword_misses(pred_answer, question_payload["keywords_for_scoring"])
    if misses:
        judge_rationale += f" Missing keywords: {', '.join(misses[:8])}."
    if not pred_answer:
        judge_rationale += " Candidate answer was empty."

    if dspy is None:
        return _PredictionShim(score=score, feedback=judge_rationale)

    return dspy.Prediction(score=score, feedback=judge_rationale)


def make_examples(split: str = "all"):
    split_norm = split.strip().lower()
    if split_norm not in {"all", "train", "val"}:
        raise ValueError("split must be one of: all, train, val")

    rows = _load_question_rows()
    examples = []

    for row in rows:
        qid = str(row.get("id", ""))
        qnum = _id_number(qid)

        if split_norm == "train" and not (1 <= qnum <= 12):
            continue
        if split_norm == "val" and not (13 <= qnum <= 20):
            continue

        payload = {
            "id": qid,
            "question": str(row.get("question", "")),
            "section": str(row.get("section", "")),
            "complexity": str(row.get("complexity", "")),
            "reference_answer": str(row.get("reference_answer", "")),
            "keywords_for_scoring": list(row.get("keywords_for_scoring", [])),
        }
        examples.append(_to_example(payload))

    return examples
