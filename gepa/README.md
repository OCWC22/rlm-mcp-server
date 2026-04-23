> For the RLM paper see [arXiv:2512.24601](https://arxiv.org/abs/2512.24601).

# GEPA legacy scaffold (diagnostics)

The original trace-first GEPA scaffold has been retired from the active optimization path and moved to `gepa/_diagnostics/`.

Use these files only for trace-shape diagnostics:

- `gepa/_diagnostics/signatures.py`
- `gepa/_diagnostics/trace_to_dataset.py`
- `gepa/_diagnostics/legacy_metrics.py`
- `gepa/_diagnostics/legacy_optimize.py`

For the v0.7.0 CDNA4 GEPA MVP pipeline/driver, use `bench/cdna4-isa/gepa/`.
