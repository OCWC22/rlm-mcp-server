"""Synthetic Needle-In-A-Haystack task generator.

This loader is zero-cost and self-contained. It generates synthetic tasks where
one UUID "needle" is embedded in random filler text. The evaluator must recover
that UUID from context using RLM tools.
"""

from __future__ import annotations

import random
import uuid
from typing import Any

SUPPORTED_LENGTHS = (4_000, 16_000, 64_000, 256_000)

# ~2k chars of neutral filler text. Kept inline so smoke tests are zero-dependency.
FILLER_SENTENCES = [
    "Autonomous systems improve reliability when they expose clear state transitions.",
    "Engineers often debug long traces by narrowing on distinctive markers first.",
    "A deterministic harness helps separate tool correctness from model behavior.",
    "Short feedback loops make regressions obvious before they impact users.",
    "Many evaluation bugs come from accidental leakage between benchmark examples.",
    "Practical REPL workflows rely on stable helper functions and bounded outputs.",
    "Text corpora for stress tests should avoid accidental answer collisions.",
    "Good benchmark scaffolds report both aggregate score and per-task failures.",
    "Context windows are finite, so retrieval strategy strongly affects quality.",
    "When costs matter, synthetic probes are useful for fast local iteration.",
    "A random seed ensures that failing cases can be reproduced exactly.",
    "Parallel execution can hide flaky behavior if shared state is not isolated.",
    "Instrumentation should capture enough metadata for post-hoc diagnosis.",
    "Small, composable tools often outperform monolithic one-shot prompts.",
    "Long documents frequently require regex-based triage before summarization.",
    "A robust harness should keep external dependencies optional and lazy.",
    "Ground-truth labels must be unambiguous to support exact-match scoring.",
    "Reliability work benefits from scripted drivers that are easy to reason about.",
    "Synthetic datasets are useful as smoke tests before expensive benchmarks.",
    "The best debugging sessions keep notes in append-only buffers for auditability.",
    "Operational readiness depends on clear failure modes and actionable errors.",
    "Subprocess isolation avoids cross-task contamination in benchmark runs.",
    "Structured JSON outputs make regression tracking much easier over time.",
    "Simple baselines are still valuable when they expose infrastructure breakage.",
]


def _build_haystack(rng: random.Random, target_chars: int) -> str:
    chunks: list[str] = []
    while len(" ".join(chunks)) < target_chars:
        chunks.append(rng.choice(FILLER_SENTENCES))
    return " ".join(chunks)


def load_tasks(n: int = 10, length: int = 4_000, seed: int = 7) -> list[dict[str, Any]]:
    """Generate synthetic S-NIAH tasks.

    Each task shape: {task_id, query, context, gold, metadata}.
    """
    if length not in SUPPORTED_LENGTHS:
        allowed = ", ".join(str(x) for x in SUPPORTED_LENGTHS)
        raise ValueError(f"unsupported length={length}; choose one of: {allowed}")

    rng = random.Random(seed)
    tasks: list[dict[str, Any]] = []

    for i in range(n):
        needle = str(uuid.UUID(int=rng.getrandbits(128)))
        haystack = _build_haystack(rng, max(1_000, length))
        insert_at = rng.randrange(len(haystack) + 1)
        context = haystack[:insert_at] + " " + needle + " " + haystack[insert_at:]

        tasks.append(
            {
                "task_id": f"sniah-{length}-{i:04d}",
                "query": "What UUID appears in the text?",
                "context": context,
                "gold": needle,
                "metadata": {
                    "dataset": "sniah",
                    "target_length": length,
                    "actual_length": len(context),
                    "needle_position": insert_at,
                    "seed": seed,
                },
            }
        )

    return tasks
