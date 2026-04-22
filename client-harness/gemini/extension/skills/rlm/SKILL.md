---
name: rlm
description: RLM loop for long-context tasks. Activate when a user asks about a file, log, or corpus exceeding ~300 KB, or when iterative chunk analysis is needed. Loads content once into an rlm MCP session, chunks it, and drives llm_query sub-calls inside rlm_exec for recursive synthesis.
---

Drive the `rlm` MCP server for long-context workflows.

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
