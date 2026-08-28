# mcp-quality — Roadmap

The CI quality suite for MCP servers. This document tracks **what's shipped**, **where we
are**, and **what's next**.

The through-line for what comes next: mcp-quality *executes* a server and checks what it
**actually does** against what its metadata **claims** — error handling, runtime cost,
annotation honesty, version stability, tool selection, spec conformance. That behavioral
lane is the focus of v0.3.

---

## ✅ Shipped — released as `0.1.0` on PyPI

`pip install mcp-quality`. Five graded check families → one **MCP Quality Score** (A–F),
CI gate, and badge. Runs over **stdio · Streamable-HTTP · SSE**, live or offline.

**Contract** — JSON-RPC / handshake conformance · JSON-Schema validity · deterministic
argument synthesis + invocation · output-shape conformance · determinism probe ·
error-path (malformed-input) probe · forward-compat lint · snapshot regression.

**Cost** — token weight of the whole toolset · per-tool leave-one-out attribution ·
opt-in response-bloat sampling · $-per-task · authoritative Anthropic `count_tokens`
(opt-in, falls back to an offline estimate).

**Legibility** — offline description lints + lexical confusable-shortlist · a seeded
agent-comprehension probe · an **N×N disambiguation matrix** · proposed rewrites, with
`mcp-quality fix` to apply them (`--apply` / `--pr`).

**Performance** — concurrent load with real MCP semantics · p50/p95/p99 · max stable
concurrency · degradation classification · connection-leak detection.

**Security-lite** — injection / secrets / dangerous-capability lints mapped to the OWASP
MCP Top 10 · `--deep-security` folds in mcp-scan / Cisco (incl. the readiness analyzer).

**Cross-cutting** — versioned scoring rubric with hard-gates · graded terminal + HTML
reports · versioned JSON (`mcp-quality/report@1`) · `--fail-under` / `--fail-under-family`
gates · snapshot `--no-regressions` · SVG + shields.io badge · historical tracking
(`--record`) and a PR score-delta comment (`compare`) · the `stampede --from-probe`
handoff seed · a registry scoring API (`mcp-quality serve`) · read-only by default with
`--allow-writes` · HTTP/SSE auth headers · deterministic, air-gapped `static` mode.

**Commands:** `run` · `static` · `snapshot` · `badge` · `fix` · `compare` · `serve`.

---

## 📍 Where we are now

- **Live on PyPI** (`mcp-quality 0.1.0`), published via trusted publishing.
- **Green CI** across Python 3.11/3.12 — 139 tests (unit · component · integration · E2E
  over stdio + HTTP/SSE), plus opt-in `live_llm` and `deep_security` suites.
- **Validated end-to-end against real servers** — a public [leaderboard](./docs/leaderboard.md)
  of reference MCP servers, and a live authenticated production run.

---

## 🔜 Next — v0.3: behavioral conformance

Doubling down on the checks only a runner can perform: comparing a server's real behavior
to its declared contract. ([milestone](https://github.com/swarmproof/mcp-probe/milestone/2))

**Deeper behavioral checks**
- **Error-recovery affordance** — grade the *error payload an agent receives* (structured?
  retryable? actionable? no leaked internals?), not just whether the server crashed. [#25]
- **Context Efficiency** — measure *runtime* response size per tool + pagination hygiene,
  and surface a comparable per-server context-footprint number. [#26]
- **Safety-Contract** (new family) — verify tool annotations are *true*: a `readOnlyHint`
  tool that mutates, or an `idempotentHint` tool that differs on repeat, is flagged. [#28]
- **Selection accuracy + over-triggering gate** — deterministic (AST-matched) right-tool
  selection, plus a false-fire gate for prompts no tool should handle. [#29]
- **Description-quality lint rubric** — namespacing, unambiguous params, no leaked
  low-level identifiers, pagination defaults (offline, no model). [#30]

**Trust over time**
- **Capability-stability / breaking-change gate** — diff the tool surface *and behavior*
  across versions; fail the PR on silent scope expansion or a breaking schema change. [#27]
- **`pass^k` reliability overlay** — report consistency across K runs, not just pass@1;
  a reliability score distinct from peak accuracy. [#31]

**Spec conformance**
- **2026-07-28 stateless-conformance** — `server/discover` present, `tools/list` stable
  across connections, required `_meta` enforced, stateful-handle hygiene. [#32]

---

## 🔭 Later — exploratory (v0.4+)

Evals for MCP surfaces beyond tools, gated on a reusable message-capture harness: sampling
prompt-safety / exfiltration risk, elicitation UX & secret-handling, resource-link
resolution, authorization least-privilege, and long-running Tasks lifecycle. [#33]

Also on the horizon: multi-model consensus legibility, distributed load, and marketplace /
registry partnerships built on the scoring API.

---

*Issues live in the [tracker](https://github.com/swarmproof/mcp-probe/issues); changes land
in [`CHANGELOG.md`](./CHANGELOG.md).*
