# Changelog

All notable changes to the Antigravity Migration package are documented here.

## [1.2.0] — 2026-04-19

### Added
- `start_antigravity.ps1` — one-click launcher for all MCP servers
- Environment variable validation on startup
- SOUL.md v3 with M4STCLAW personality integration

### Fixed
- OpenRouter endpoint URL in `opencode.jsonc`
- Missing SambaNova provider in fallback chain

## [1.1.0] — 2026-04-10

### Added
- 5 MCP server configurations (system, browser, memory, vision, web)
- 21-provider LLM fallback chain with prioritized routing
- `.env.example` with all 56 API key slots documented

### Changed
- Migrated from `opencode.json` to `opencode.jsonc` for inline comments

## [1.0.0] — 2026-03-28

### Added
- Initial migration package for M4ST v6 → Antigravity IDE transition
- Core `opencode.jsonc` configuration
- README with complete migration guide
- SOUL.md personality layer
