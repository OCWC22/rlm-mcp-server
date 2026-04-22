# client-harness/ — per-CLI RLM artifacts

Each subdirectory contains the native extension artifacts for one client.
`scripts/install_clients.py --deploy-harness` reads this tree and deploys
artifacts to each detected client via copy / symlink / marker-merge, with
timestamped backups before any write.

## Layout

- `claude-code/agents/rlm-analyst.md`  →  `~/.claude/agents/`
- `claude-code/commands/rlm-load.md`   →  `~/.claude/commands/`
- `claude-code/memory/rlm-snippet.md`  →  marker-merged into `~/.claude/CLAUDE.md`
- `codex/agents-md-snippet.md`         →  marker-merged into `~/.codex/AGENTS.md`
- `codex/skills/rlm/SKILL.md`          →  `~/.codex/skills/rlm/SKILL.md`
- `gemini/extension/`                  →  `~/.gemini/extensions/rlm/` (via `gemini extensions install`)
- `gemini/memory/gemini-snippet.md`    →  marker-merged into `~/.gemini/GEMINI.md` (fallback if no extension install)
- `claude-desktop/README.md`           →  manual checklist (no file automation possible)

## Idempotency

Every marker-merged snippet uses `<!-- BEGIN rlm-harness v0.5.0 -->` /
`<!-- END rlm-harness v0.5.0 -->` sentinels. Re-running the installer skips
files that already contain a matching block. Bump the version in the marker
when snippet content changes.

## Design notes (summary)

- **Claude Code**: subagents, commands, and MCP prompts all fire automatically
- **Codex CLI**: no user-defined slash commands; AGENTS.md is the reliable injection path
- **Gemini CLI**: extension bundles are the cleanest distribution; GEMINI.md is always additive
- **Claude Desktop**: no file-based primitives; MCP prompts via + attach menu only

## UNCONFIRMED items (as of 2026-04-21)

- Whether MCP `prompts/list` surfaces as user-invocable slash commands in
  Codex CLI and Gemini CLI. Confirmed for Claude Code.
- Whether `~/.codex/instructions.md` is an official slot or a leftover.
- Whether `gemini skills link` resolves the `~/.agents/skills/` alias when
  symlinking from this repo.

Live-test these before claiming full automatic coverage in v0.5.1+.

## Paper + repo

- Repo: https://github.com/OCWC22/rlm-mcp-server
- Paper: https://arxiv.org/abs/2512.24601
