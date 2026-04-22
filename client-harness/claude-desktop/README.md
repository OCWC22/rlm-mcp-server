# Claude Desktop — RLM manual checklist

Claude Desktop has no file-based extension primitives beyond MCP server
registration. The rlm MCP server is already configured in
`~/Library/Application Support/Claude/claude_desktop_config.json`.

## Verify manually

1. Fully quit Claude Desktop (Cmd-Q).
2. Relaunch.
3. Open a new chat.
4. Click the + (attach) menu — you should see entries from the rlm MCP
   server including the 3 workflow prompts:
   - kernel_analysis
   - paper_deep_dive
   - codebase_triage
5. To use: click + and pick "Add from rlm" to inject one as a template.

## What cannot be automated

- No CLAUDE.md injection (Desktop does not read it)
- No slash commands beyond MCP-advertised prompts
- No subagents / skills / extensions
- Only the MCP server config file is writable by this repo installer.

## Recommended UX hint

Because Desktop discovery is manual, users benefit from knowing the prompt
names up front. Include them in onboarding. The rlm-mcp-server README
"Use cases" section is a good external reference.
