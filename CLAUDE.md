# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state: v0.1 implemented (all five families)

The v0.1 fast path and all five check families are implemented, tested, and dogfooded.
Python 3.11+ (`src/` layout, `pip install`), official MCP SDK, `asyncio`. What deviates
from the spec is recorded in **`docs/DECISIONS.md`** — read it before changing security
IDs, the handshake, or the token counter.

### Commands

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"   # setup

.venv/bin/pytest -m "not live_llm" -q            # full suite (unit+component+integration+e2e)
.venv/bin/pytest tests/test_scorer.py -q          # a single test file
.venv/bin/pytest -m e2e -q                        # only the live-fixture E2E scenarios
.venv/bin/pytest -m live_llm -q                   # opt-in, calls a real model (excluded by default)
.venv/bin/ruff check src/ tests/                  # lint (line-length 110)
.venv/bin/mypy src/                               # types (strict)

.venv/bin/mcp-probe run ".venv/bin/python tests/servers/good_server.py"   # live probe
.venv/bin/mcp-probe static tests/servers/dump.mcp.json --json             # offline
.venv/bin/mcp-probe run "…" --all --model ollama:qwen2.5-3b               # all five families
```

Tests spawn fixture servers with the **same interpreter running pytest** (`sys.executable`),
so they need the SDK installed in that env — always run via `.venv/bin/pytest`.

### Package layout (`src/mcp_probe/`)

- `models.py` — the frozen data model (`ServerSurface`/`Finding`/`FamilyScore`/`Report`/`CheckEngine`).
- `config.py` · `cli.py` · `exit_codes.py` — config precedence, the 4 subcommands, CI exit codes.
- `connect/` — `transport.py` is the **only** module importing the MCP SDK; `client.py` is the
  façade + `FakeClient`; `discover.py` builds surfaces (live + static dump).
- `engines/` — one file per family, each a pure `CheckEngine`; registered in `engines/__init__.py`.
- `contract/`, `legibility/`, `security/`, `perf/`, `tokens.py` — engine-specific internals.
- `scoring/` · `snapshot/` · `report/` · `handoff.py` · `trace.py` — aggregation & outputs.
- `tests/servers/` — fixture MCP servers (the TEST-PLAN §2 matrix) + `dump.mcp.json`.

## What mcp-probe is

The **CI quality suite for MCP servers** — "the `pytest` + `lighthouse` for the servers agents depend on." It connects to an MCP server, discovers its surface, and grades it across **five check families** into a single A–F **MCP Quality Score**, designed to run as a CI gate with a README badge.

Positioning is load-bearing and deliberate: security scanners (mcp-scan, Cisco) answer *"is this server dangerous?"*; mcp-probe answers *"is this server good?"* It treats security as **one light check**, defers deep security to the incumbents via `--deep-security` integration (never reimplements them), and unifies the quality *point* tools (credits mcp-xray as prior art) into a CI-native **suite and gate**. Do not drift the messaging toward "another scanner."

The five families: **Contract** (LLM-free spec/schema/determinism), **Legibility** (the differentiator — agent-comprehension score + disambiguation matrix), **Cost** (toolset token weight), **Performance** (concurrent MCP-semantic load), **Security-lite** (OWASP MCP Top 10 basics + integration adapter).

## Documentation hierarchy (read in this order)

The docs are authoritative and layered — consult them before implementing anything:

1. **`SPEC.md`** — the frozen v1.0 design spec/PRD. The baseline.
2. **`docs/PRD.md`** — numbered, testable requirements: `REQ-*` (functional, per family) and `NFR-*` (non-functional). This is the requirement-of-record; code and tests reference these IDs.
3. **`docs/ARCHITECTURE.md`** — system design, the core data model (`ServerSurface`, `Finding`, `FamilyScore`, `Report`, `CheckEngine`), the JSON output schema, and the **ADRs** (ADR-001..009) that bind implementation choices.
4. **`docs/DELIVERY-PLAN.md`** — the WBS (`W0..W6`), effort sizing, critical path, and v0.1 Definition of Done.
5. **`docs/TEST-PLAN.md`** — the acceptance backbone: E2E scenarios (`E2E-1..10`), the fixture server matrix, the `StubModel` determinism harness, and CI gates.
6. **`docs/RESEARCH.md`** — the competitive/market analysis the positioning rests on.

**Conventions in the docs that carry into code:**
- The **`⊕ Beyond original spec`** marker flags anything extending the frozen v1.0 `SPEC.md`. Preserve it when editing docs; it tracks scope past the baseline.
- Requirement IDs (`REQ-C4`, `NFR-2`, etc.) and finding codes (`C5-nondeterminism`, `S1-owasp-mcp05`) are stable identifiers — reference them in commits, tests, and `Finding.code`.
- Tier labels: **[fast]** = zero-LLM deterministic, **[llm]** = needs a small model, **[net]** = needs a live server, **[static-ok]** = works offline in `static` mode.

## Architecture: the binding decisions

The system is a **pipeline**: `connect → discover → fan out to five engines → Scorer → Renderer/JSON/badge`. When implementing, these ADRs are constraints, not suggestions:

- **ADR-001 — Engines are pure functions of `ServerSurface` (+ optional live client) → `FamilyScore`.** No engine mutates shared state; the Scorer and Renderer are the *only* aggregators. This is what makes the fast path deterministic and every engine testable with a fixed `ServerSurface` and no network/LLM. Adding a sixth family = implement the `CheckEngine` protocol and register it. **Smuggling shared mutable state into an engine violates the architecture.**
- **ADR-002 — Zero-LLM fast path is the CI default.** Contract + Cost + Performance run with no model calls (`NFR-1`); Legibility is opt-in and off the critical path. The gate must be satisfiable by the fast path alone.
- **ADR-003 — Version-aware connect.** The MCP spec is mid-transition (2025-11-25 legacy `initialize` handshake ↔ 2026-07-28 `server/discover` + `_meta`). Negotiate both, grade the result, require neither. This is the hardest correctness surface.
- **ADR-004 — Canonical Legibility scorer = pinned local model, temp 0, fixed seed, cached by `(surface_hash, model_id, seed, goal_set_version)`.** Cloud models are opt-in and marked non-canonical. A rerun on an unchanged surface is a cache hit → ~$0, byte-identical.
- **ADR-005 — `--deep-security` shells out and normalizes; never reimplements scanners.** Missing scanner → "not measured", never a failure.
- **ADR-006 — `static` mode reports live-only checks as "not measured", never `0`.** Zeroing unmeasured checks is a bug (it punishes offline use and is gameable).
- **ADR-009 — Read-only by default** (`NFR-9`); destructive tools (destructiveHint / heuristic) are skipped unless `--allow-writes`. Probing a `delete_*` tool must not fire it.

### Determinism doctrine (the whole value prop)

The tool grades code in CI, so its own output must be trustworthy:
- **Fast path** (Contract/Cost/Security-lite built-in): **byte-identical** output for identical input, enforced by golden-file tests. No wall-clock or network-order dependence in scoring.
- **Legibility**: deterministic only *under a fixed (model, seed, goal-set)*; tests use `StubModel` (never a real LLM) and assert the cache serves reruns with `call_count == 0`.
- **Performance latencies**: inherently nondeterministic → assert *invariants* (percentile ordering `p50≤p95≤p99`, leak detection, degradation classification), never absolute ms.

### Scoring rubric

Weighted mean of five 0–100 sub-scores → letter grade. Default weights: **Cost 30%, Legibility 25%, Contract 20%, Performance 15%, Security-lite 10%** (see `docs/PRD.md` §7 for rationale). A family scoring **F caps overall at C** (the "hard-gate" — no A-grade server with a broken contract or critical security finding). Every report and badge carries `rubric_version` for cross-release comparability (`NFR-7`).

### Shared primitives (vendored, bound to stampede's contracts)

mcp-probe is project #3 of the seven-project **Swarm Proof** toolkit and reuses four primitives. The portfolio decision is **vendor-first**: copy minimal versions now rather than wait on extraction (~stampede v0.2). But the *contracts* are authoritative and must not be forked:
- **concurrency-core** — the Performance load driver imports stampede's `Scheduler`/`Executor` **Protocol** and supplies uniform MCP-client tasks (not persona logic).
- **report-renderer** — render via the shared `RunReport` model (oxblood style); register a `QualityScoreReport` view over it.
- **trace-format** — **the OpenTelemetry GenAI semantic-conventions *profile*** (`gen_ai.*` spans + the `swarmproof.*` extension), *not* a bespoke schema. The `stampede --from-probe` handoff depends on cross-tool trace compatibility — consume the profile, don't fork it.
- **persona-pack** — one minimal `naive` persona (`apiVersion: swarmproof.dev/persona/v1`) for the Legibility probe.

## Working conventions

- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`), atomic, imperative mood, no AI attribution/signatures. Commit progressively as you go.
- **Testability first:** because engines are pure functions, prefer a component test that feeds a fixed `ServerSurface` and asserts an exact `FamilyScore` over any test that needs a network or a real model. Live/LLM behavior belongs in integration/E2E with fakes (`StubModel`) or the opt-in, network-gated `-m live_llm` suite (excluded from the default/PR run).
- **Dogfood:** the intended CI runs `mcp-probe` against its own `tests/servers/` fixtures — the tool must grade its own sample servers correctly (see `docs/TEST-PLAN.md` §9).
- **Honest over impressive:** document boundaries; never zero an unmeasured check; mark non-canonical scores as such.
