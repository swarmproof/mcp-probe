# mcp-probe — Roadmap

> **Status (2026-07-18):** v0.1 feature-complete. All five families, CLI
> (`run`/`static`/`snapshot`/`badge`), JSON + `--fail-under` + `--no-regressions` gates,
> badge, snapshot regression, `--deep-security` adapters, opt-in authoritative Anthropic
> token counts, the disambiguation-matrix renderer, and dogfooding CI. **97 tests green**
> (+ opt-in `live_llm`, verified against Ollama) over stdio + Streamable-HTTP + SSE.
> [Leaderboard](../docs/leaderboard.md) run against 7 real public MCP servers (6×A, 1×D);
> [demo](../docs/demo.md) captured. See `docs/DECISIONS.md` for deviations.
> Remaining: record the demo GIF (script in `scripts/demo.sh`; needs asciinema), expand the
> leaderboard, and the launch essay.

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
