# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.1] - 2026-04-21

### Added
- New `scripts/verify_end_to_end.py` harness for CLI end-to-end checks (Claude Code, Codex CLI, Gemini CLI) with `--json` and `--dry-run` modes.
- README per-client end-to-end invocation cheat sheet and manual Claude Desktop verification checklist.

### Changed
- `rlm_mcp.py` now accepts `RLM_DATA_DIR` as a fallback alias for `RLM_STATE_DIR`, expands `~` in configured paths, and logs resolved config sources once at startup.
- `scripts/install_clients.py` now warns (non-fatal) when Gemini CLI is detected with Node.js < 20.
- Added explicit MCP-vs-skill coexistence guidance in `README.md` and `AGENTS.md`.
- README now points release notes readers to `CHANGELOG.md` and removes stale version-frozen notes.

## [0.3.0] - 2026-04-20

### Added
- True sync-bridged symbolic recursion inside `rlm_exec`, completing paper invariants **3/3**.
- Evaluation harness (`eval/`) with synthetic S-NIAH benchmark support.
- GEPA metric wiring that scores prompt candidates against real benchmark outputs.

### Changed
- Repository canonically standardized around `rlm-mcp-server` on `main`.
- Paper-faithful framing and evaluation guidance expanded in docs.

## [0.2.0] - 2026-04-20

### Added
- `rlm_exec`: stateful Python execution with persisted globals per `session_id`.
- `rlm_sub_query` + `rlm_sub_query_result`: recursive sub-query flow with callback fallback when Sampling is unavailable.
- JSONL tracing with timing/redaction and `rlm-trace` inspection/export CLI.
- GEPA scaffold (`gepa/`) plus trace-to-dataset workflow.

### Changed
- MCP surface expanded from 11 tools to 14 tools.
- Package/repo naming and docs aligned to `rlm-mcp-server` and paper terminology.

## [0.1.0] - 2026-04-20

### Added
- Initial release (`45e6730`) of a simple persistent-REPL MCP server.
- 11-tool baseline: session load/status/peek/grep/chunk/buffer/reset primitives for long-context workflows.

[Unreleased]: https://github.com/OCWC22/rlm-mcp-server/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/OCWC22/rlm-mcp-server/compare/v0.4.0...v0.4.1
[0.3.0]: https://github.com/OCWC22/rlm-mcp-server/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/OCWC22/rlm-mcp-server/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/OCWC22/rlm-mcp-server/tree/45e67309b1cc00bad749139ecb872625d8c82bfe
