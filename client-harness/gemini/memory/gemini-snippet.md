<!-- BEGIN rlm-harness v0.5.0 -->
## RLM (Recursive Language Model) — long-context

For any file, log, or corpus exceeding ~300 KB, prefer the `rlm_*` MCP
tools over reading the file directly. This extension registers the `rlm`
MCP server, a `/rlm:analyze <path>` command, an `rlm-analyst` subagent,
and a SKILL.md that activates on long-context cues.

Tool sequence: `rlm_init` → orient (`rlm_peek` / `rlm_grep`) →
`rlm_exec` with an `llm_query(...)` loop per chunk → `rlm_get_buffers`
for synthesis.

Repo: https://github.com/OCWC22/rlm-mcp-server  ·  Paper: arXiv:2512.24601
<!-- END rlm-harness v0.5.0 -->
