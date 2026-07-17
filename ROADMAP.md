# mcp-probe — Roadmap

> **Status (2026-07-17):** v0.1 implemented — all five families, CLI (`run`/`static`/
> `snapshot`/`badge`), JSON + `--fail-under` + `--no-regressions` gates, badge, snapshot
> regression, `--deep-security` adapters, dogfooding CI. 89 tests green (fast path
> deterministic & <1s on 30 tools). Real LLM providers wired but exercised only via the
> opt-in `live_llm` suite. See `docs/DECISIONS.md` for deviations. Remaining before launch:
> HTTP/SSE live integration tests, the demo GIF, and the 20-server leaderboard.

## v0.1 (launch)
- All five check families (Contract, Legibility, Cost, Performance, Security-lite)
- Security-lite built-in + optional `--deep-security` integration (mcp-scan / Cisco)
- CLI + CI + JSON + `mcp-probe: A` badge; snapshot regression
- Launch on HN + "your MCP server has a quality score" essay + a 20-server leaderboard

## v0.2
- Legibility auto-fix (proposes + PRs description rewrites)
- Registry scoring API; historical score tracking

## v0.3
- `stampede --from-probe` handoff (probe target upgrades to full simulation)
- Marketplace partnerships
