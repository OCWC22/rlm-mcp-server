> For the RLM paper see [arXiv:2512.24601](https://arxiv.org/abs/2512.24601).

# GEPA scaffold for `rlm-repl-mcp`

This directory is a **scaffold** for optimizing RLM tool-description prompts from real trace data. It is **not** a pre-trained optimizer output and it does **not** auto-run optimization. A real GEPA run requires an LM backend and will consume tokens/compute.

## What this is

- `trace_to_dataset.py`: converts `rlm-trace export` JSONL into GEPA/DSPy-compatible training examples
- `signatures.py`: minimal DSPy signature (`RLMToolSelection`) and baseline tool-description text
- `metrics.py`: simple heuristic trace-quality metric (0..1)
- `gepa_optimize.py`: optimization entry point (`GEPA.compile(...)`) with API-shape fallbacks

## What this is NOT

- Not a complete evaluator for all user tasks
- Not an automatic production tuning loop
- Not guaranteed to improve results without enough diverse traces and a better metric

## Prereqs

1. Collect real traces (Phase 2):
   ```bash
   rlm-trace export /tmp/rlm-traces.jsonl
   ```
2. Install optional GEPA deps:
   ```bash
   pip install 'rlm-repl-mcp[gepa]'
   ```
3. Configure an LM backend for DSPy (API key provider or local OpenAI-compatible endpoint, e.g. Ollama/LiteLLM bridge).

## Run

```bash
python -m gepa.gepa_optimize --trainset /tmp/rlm-traces.jsonl --out gepa/compiled/tool_descriptions.json
```

Optional knobs:
- `--lm` (default `openai/gpt-4o-mini`)
- `--num-threads` (default `4`)
- `--max-calls` (default `50`)

## Known limitations (honest)

- The metric is intentionally naive; it rewards basic navigation patterns only.
- The dataset builder uses heuristic task segmentation (session boundaries + time gaps + terminal tools).
- You likely need **50+ real traces** before optimization becomes meaningful.
- This scaffold does not automatically copy optimized descriptions back into `rlm_mcp.py`.

## Suggested loop

1. Run real sessions against the MCP server.
2. Export traces with `rlm-trace export`.
3. Run `python -m gepa.gepa_optimize ...`.
4. Review compiled output.
5. Manually update tool descriptions in `rlm_mcp.py` (`@mcp.tool(description=...)`) and re-test.
