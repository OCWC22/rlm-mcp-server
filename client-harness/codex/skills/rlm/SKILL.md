---
name: rlm
description: Recursive Language Model loop for long-context tasks. Use this skill whenever you need to analyze files, logs, or corpora that exceed ~300 KB, are too large for a single context window, or require iterative chunk-by-chunk reasoning. Drives the `rlm` MCP server tools to load, chunk, recursively query, and synthesize.
---

This skill activates the RLM (Recursive Language Model) workflow from `rlm-mcp-server`.

## When to invoke

- Files or text ≥ ~300 KB
- Multi-file corpora pre-concatenated via `find + cat`
- Any task where the paper §3.1 would call complexity "linear" or "quadratic" in input length (e.g. aggregate statistics across every entry, pairwise relations)
- Long kernel/CUDA/HIP source analysis
- arXiv-length papers, legal documents, build/CI logs

## Tool sequence

1. `rlm_init(path=<file>, session_id=<slug>)`
2. `rlm_status(<slug>)` — confirm size + existing buffers
3. Orient: `rlm_peek(0, 1000)` then `rlm_grep(<pattern>)`
4. Plan: `rlm_chunk_indices(size=150000)` or a semantic split (by section header)
5. Execute: `rlm_exec(code=...)` with a Python loop that calls `llm_query(prompt)` per chunk and `add_buffer(...)` the result
6. Synthesize: `rlm_get_buffers(<slug>)` then compose the final answer

## Workflow prompts

If the MCP server advertises prompts, prefer them over ad-hoc tool sequences:

- `kernel_analysis(kernel_path, question)` — GPU kernel review
- `paper_deep_dive(paper_path, topic)` — academic text
- `codebase_triage(repo_path, question)` — large code corpus

Repo: https://github.com/OCWC22/rlm-mcp-server
Paper: https://arxiv.org/abs/2512.24601 (Zhang et al., MIT CSAIL)
