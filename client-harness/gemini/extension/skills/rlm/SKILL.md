---
name: rlm
description: RLM loop for long-context tasks. Activate when a user asks about a file, log, or corpus exceeding ~300 KB, or when iterative chunk analysis is needed. Loads content once into an rlm MCP session, chunks it, and drives llm_query sub-calls inside rlm_exec for recursive synthesis.
---

Drive the `rlm` MCP server for long-context workflows.

This is the long-context READ path, not the Trampoline PredictRLM BUILD skill.
Use it to analyze existing files/corpora. Do not use it to scaffold a reusable
`predict-rlm` package; for that, use the Trampoline PredictRLM skill.

Routing rule:
- READ a large existing corpus now -> use this MCP-backed skill.
- BUILD a callable Python/DSPy RLM package -> use Trampoline PredictRLM.
- CODE an application that directly imports `dspy.RLM` -> use DSPy RLM module
  guidance.
- DEBUG-LOOP inside a repo with local RLM doctrine -> follow that repo's
  `AGENTS.md` / `.claude/rules/`.

## Canonical sequence

1. `rlm_init(path=<file>, session_id=<slug>)`
2. `rlm_status(<slug>)`
3. `rlm_peek` / `rlm_grep` to orient
4. `rlm_chunk_indices` or semantic split
5. `rlm_exec` with a Python loop calling `llm_query(...)` per chunk
6. `rlm_get_buffers(<slug>)` → synthesize

## When the MCP advertises prompts

Prefer `/rlm:analyze <path>` (custom command in this extension) or the MCP prompts if surfaced as slash commands.

Repo: https://github.com/OCWC22/rlm-mcp-server
