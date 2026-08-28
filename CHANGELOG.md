# Changelog

All notable changes to mcp-quality are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [0.1.0] — unreleased

First public release: the CI quality suite for MCP servers. Grades any MCP server across
five check families into a single **MCP Quality Score**, gates CI, and prints a badge.

### Added
- **Contract** `[fast]` — JSON-RPC/handshake conformance, JSON-Schema validity,
  deterministic argument synthesis + invocation, output-shape conformance, and a
  determinism probe. Read-only by default; destructive tools skipped unless `--allow-writes`.
- **Cost** `[fast]` — whole-toolset token count, leave-one-out per-tool attribution,
  $-per-task. Offline-deterministic (tiktoken, labeled as an estimate) with an **opt-in**
  authoritative Anthropic `count_tokens` path (`--token-model anthropic:<model>`) that
  falls back silently without a key.
- **Security-lite** `[fast]` — injection/tool-poisoning, secrets (regex + entropy), and
  dangerous-capability lints mapped to the **OWASP MCP Top 10** (`MCP01/03/05:2025`);
  `--deep-security` folds in mcp-scan (Snyk) / Cisco findings when installed.
- **Performance** `[net]` — concurrent load with real MCP semantics, p50/p95/p99, max
  stable concurrency, degradation classification, and connection-leak detection.
- **Legibility** `[llm]` — offline description lints + lexical confusable-shortlist
  always; a seeded comprehension probe, an **N×N disambiguation matrix**, and proposed
  rewrites when a model is configured. Results cached by
  `(surface_hash, model, seed, goal_set)` — warm reruns invoke the model zero times.
- Transports: **stdio**, **Streamable-HTTP**, and legacy **SSE**; version-aware
  `initialize` handshake (spec `2025-11-25`).
- CLI: `run` · `static` (offline/air-gapped) · `snapshot` (+ `--no-regressions`) · `badge`.
- Outputs: graded terminal report, HTML, versioned JSON (`mcp-quality/report@1`) with
  `--fail-under`, an SVG + shields.io badge, and the `stampede --from-probe` handoff seed.
- Scoring: weighted mean (Cost 30 / Legibility 25 / Contract 20 / Performance 15 /
  Security 10), hard-gate cap at C, versioned rubric (`2026.07.1`).
- 139 tests (unit + component + integration + E2E over stdio & HTTP/SSE), opt-in
  `live_llm` / `deep_security` suites, and a dogfooding CI (test / dogfood / determinism /
  offline jobs).
- A reproducible [leaderboard](docs/leaderboard.md) of real public MCP servers and a
  captured [demo](docs/demo.md).

Also included (planned as the "v0.2" milestone, shipped in this first release):
- **Legibility auto-fix** — `mcp-quality fix` applies the proposed description rewrites to
  source (name-anchored find/replace), with `--apply` / `--pr` (REQ-L7).
- **Historical tracking** — `mcp-quality run --record` + `mcp-quality compare` + a sticky PR
  score-delta comment workflow.
- **Cost** — response-bloat sampling (`--response-bloat`) and lazy-loading remediation
  hints (REQ-$5/$6).
- **Contract** — error-path conformance (malformed input must not crash) + deprecated-SSE
  forward-compat lint (REQ-C9/C10).
- **Security** — Cisco `readiness` analyzer folded into Performance/Contract (REQ-S6).
- **Transport/gating** — HTTP/SSE auth headers (`--header`), per-family gates
  (`--fail-under-family`).
- **Registry scoring API** — `mcp-quality serve` (`POST /score` · `/verify` · `/healthz`),
  in the `[registry]` extra.

### Dependencies
- Pinned `mcp>=1.28,<2`: SDK v2 renamed `FastMCP`→`MCPServer` and changed result-field
  casing. Migration to v2 is tracked separately.

### Notes
- Deviations from the design spec are recorded in [docs/DECISIONS.md](docs/DECISIONS.md)
  (OWASP MCP Top 10 mapping; why the `2026-07-28` stateless `server/discover` path is not
  yet implemented; the offline-token estimate).

[0.1.0]: https://github.com/swarmproof/mcp-probe/releases/tag/v0.1.0
