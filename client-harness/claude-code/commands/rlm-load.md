---
description: Load a file into an RLM session and prime the model to analyze it with the rlm MCP tools.
argument-hint: <file-path> [session_id]
---

You are about to analyze a long-context file using the `rlm` MCP server.

**File to analyze:** `$1`
**Session ID:** `${2:-rlm-load-default}`

Steps:
1. Call `rlm_init(path="$1", session_id="${2:-rlm-load-default}")`.
2. Call `rlm_status("${2:-rlm-load-default}")` to report size + buffer count.
3. Call `rlm_peek(0, 1000)` for a structural preview.
4. Ask the user what analysis they want, then route to the right workflow:
   - Code repository → `rlm_grep` + `rlm_exec` loop
   - Paper / long doc → use the `/mcp__rlm__paper_deep_dive` prompt
   - GPU/CUDA/HIP kernel → use the `/mcp__rlm__kernel_analysis` prompt
   - Generic multi-file corpus → use the `/mcp__rlm__codebase_triage` prompt

Do NOT Read the file with the built-in Read tool — offload it to the RLM session.
