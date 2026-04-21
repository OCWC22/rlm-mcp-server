# Eval harness scaffold (`eval/`)

Paper reference: [arXiv:2512.24601](https://arxiv.org/abs/2512.24601) (see §3.1 for benchmark/task framing).

This package adds a **paper-native evaluation scaffold** so tool-description optimization can target benchmark scores instead of only heuristic trajectory shape.

## Included datasets/loaders

- `sniah` (synthetic needle-in-haystack): fully local + free, generated on the fly.
- `oolong` (`alexbertsch/oolong`, split `trec_coarse`): free to download, requires optional `datasets` dependency.
- `browsecomp` + `longbench`: documented loader stubs only in v0.3 (not bundled due external setup/license constraints).

## Cost and licensing notes

- **S-NIAH synthetic**: free.
- **OOLONG**: free download via Hugging Face datasets (`pip install 'rlm-mcp-server[eval]'`).
- **BrowseComp / LongBench**: not bundled here; some variants have separate dataset licensing/setup. Review upstream terms before use.

## Run

```bash
python -m eval.harness --dataset=sniah --n=10
python -m eval.harness --dataset=sniah --n=10 --length=4000
python -m eval.harness --dataset=oolong --n=50 --split=trec_coarse
```

## Important caveat (intentional for v0.3)

The harness driver is **scripted**, not LLM-driven. That means v0.3 measures
whether the MCP tool plumbing works reliably (`rlm_init -> rlm_peek -> rlm_grep -> rlm_exec`) rather than whether a host LLM can discover and execute optimal strategies.

A true end-to-end RLM capability evaluation requires an MCP-aware LLM in the loop and benchmark-level scoring of model behavior. That is planned for v0.4.
