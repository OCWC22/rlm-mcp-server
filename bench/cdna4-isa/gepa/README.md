# CDNA4 GEPA MVP (v0.7.0 Item 1)

This directory contains the CDNA4 benchmark-facing GEPA workflow.

It mirrors the `examples/01-rag-qa/` structure from `dspy-agent-skills` and adapts it to the real CDNA4 runner path:

- `pipeline.py` defines the DSPy signature/module, dataset loader, and rich metric.
- `run.py` provides `--dry-run`, `--baseline`, `--optimize`, and `--eval` entry points.

## Credits

Design and structure are adapted from:

- `dspy-agent-skills/examples/01-rag-qa/pipeline.py`
- `dspy-agent-skills/examples/01-rag-qa/run.py`

## Quick usage

From repo root (`rlm-mcp-server/`):

```bash
# No LM calls; only builds signature/module/examples/metric
python3 -m bench.cdna4-isa.gepa.run --dry-run

# Required for baseline/optimize/eval:
export RLM_TASK_LM=openrouter/openai/gpt-5-mini
export RLM_REFLECTION_LM=openrouter/openai/gpt-5.4

python3 -m bench.cdna4-isa.gepa.run --baseline
python3 -m bench.cdna4-isa.gepa.run --optimize
python3 -m bench.cdna4-isa.gepa.run --eval bench/cdna4-isa/gepa/compiled/cdna4_runner.json
```

`--optimize` writes:

- `bench/cdna4-isa/gepa/compiled/cdna4_runner.json`
- `bench/cdna4-isa/gepa/results.json`
- `bench/cdna4-isa/gepa/results.md`
- `bench/cdna4-isa/gepa/version_comparison.json`

## Import-path note (`cdna4-isa` hyphen)

The benchmark folder uses a hyphen (`bench/cdna4-isa/`), so `run.py` imports `pipeline.py` via `importlib.util.spec_from_file_location(...)` using a stable module alias (`cdna4_gepa_pipeline`).

This avoids fragile direct package imports while keeping `python -m bench.cdna4-isa.gepa.run ...` usable.

## Data split

`pipeline.make_examples(split=...)` uses deterministic IDs:

- train: `Q01`–`Q12`
- val: `Q13`–`Q20`
- all: full dataset
