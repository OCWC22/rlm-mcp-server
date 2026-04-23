# codebase-triage input corpus

This domain expects a **user-provided concatenated repository corpus**.

Suggested source root:

- `/Users/chen/Projects/claude_code_RLM/rlm-mcp-server`

Recommended build process:

1. Concatenate core implementation files (for example `rlm_mcp.py`, `rlm_trace_cli.py`, `dspy_rlm/`, `scripts/`, selected docs).
2. Keep each chunk prefixed with its source file path and line range.
3. Save the corpus as UTF-8 text (for example `inputs/rlm_mcp_server_corpus.txt`).

Set `RLM_CODEBASE_TRIAGE_CORPUS` (or edit `config.yaml`) to point to the generated corpus file.
