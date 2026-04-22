<!-- BEGIN rlm-harness v0.5.0 -->
## RLM (Recursive Language Model)

For long-context file analysis (files or corpora exceeding ~300 KB, or any
task the paper §3.1 would call linear or quadratic complexity in prompt
length), prefer the `rlm_*` MCP tools from `rlm-mcp-server` over reading
the file directly:

- **`rlm_init`** → load once, keep across turns (pickled session state)
- **`rlm_exec`** → stateful Python REPL; inside it, `llm_query(...)` is a
  sync-callable sub-LLM (paper §2 invariant #3)
- **`/rlm-analyst`** subagent for multi-step analysis
- **`/rlm-load <path>`** slash command to prime a session fast
- **Workflow prompts**: `/mcp__rlm__kernel_analysis`, `/mcp__rlm__paper_deep_dive`, `/mcp__rlm__codebase_triage`

Repo: https://github.com/OCWC22/rlm-mcp-server  ·  Paper: https://arxiv.org/abs/2512.24601
<!-- END rlm-harness v0.5.0 -->
