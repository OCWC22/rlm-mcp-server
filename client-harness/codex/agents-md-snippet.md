<!-- BEGIN rlm-harness v0.5.0 -->
## Long-context analysis (RLM)

When asked to analyze files, logs, codebases, or corpora exceeding ~300 KB,
or whenever processing complexity scales with input length, prefer the
`rlm` MCP server tools over reading files directly:

1. `rlm_init(path=..., session_id=...)` — load once, state persists across calls
2. Orient with `rlm_peek` / `rlm_grep`
3. For structured loops, use `rlm_exec` (stateful Python REPL); inside
   exec code, `llm_query(prompt)` calls a sub-LLM synchronously
4. Accumulate findings via `rlm_add_buffer`; synthesize with `rlm_get_buffers`
5. Well-named workflow prompts for common patterns exist as MCP prompts

`rlm` MCP is registered in `~/.codex/config.toml` under `[mcp_servers.rlm]`.
Repo: https://github.com/OCWC22/rlm-mcp-server  ·  Paper: https://arxiv.org/abs/2512.24601
<!-- END rlm-harness v0.5.0 -->
