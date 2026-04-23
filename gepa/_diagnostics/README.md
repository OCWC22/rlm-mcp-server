# GEPA diagnostics (legacy scaffold)

This folder preserves the pre-v0.7.0 GEPA scaffold for trace-shape diagnostics.

These utilities are **diagnostic-only** and are **not** the v0.7.0 CDNA4 optimization path.

## Contents

- `signatures.py` — legacy `RLMToolSelection` signature/student module.
- `trace_to_dataset.py` — legacy trace JSONL → DSPy dataset conversion.
- `legacy_metrics.py` — legacy heuristic/eval-harness metrics.
- `legacy_optimize.py` — legacy optimizer entry point for trace-derived datasets.

Use `bench/cdna4-isa/gepa/` for the v0.7.0 CDNA4 GEPA MVP pipeline/driver.
