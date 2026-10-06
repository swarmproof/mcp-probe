# mcp-quality — Roadmap

The CI quality suite for MCP servers. This document tracks **what's shipped**, **where we
are**, and **what's next**.

The through-line: mcp-quality *executes* a server and checks what it **actually does**
against what its metadata **claims** — error handling, runtime cost, annotation honesty,
version stability, tool selection, spec conformance. The behavioral lane (**v0.3**) and the
scale/trust/ecosystem lane (**v0.4**) are both shipped; what's left is cross-host scale and
a few probes gated on evolving SDK/spec support.

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

- **Live on PyPI** (`mcp-quality 0.5.0`), published via trusted publishing — the v0.4
  milestone (authz, tasks, consensus, distributed load, registry) on **MCP SDK v2**.
- **Six scored families** (Contract · Cost · Legibility · Performance · Security-lite ·
  Safety-Contract) plus an **experimental** spec-surface family, all behind one rubric.
- **Green CI** across Python 3.11/3.12/3.13 — 266 tests (unit · component · integration · E2E
  over stdio + HTTP/SSE), plus opt-in `live_llm` and `deep_security` suites.
- **Validated end-to-end against real servers** — a public [leaderboard](./docs/leaderboard.md)
  of reference MCP servers, and a live authenticated production run.

---

## ✅ Shipped — v0.3: behavioral conformance (`0.3.0`)

The checks only a runner can perform: comparing a server's real behavior to its declared
contract. All merged. ([milestone](https://github.com/swarmproof/mcp-probe/milestone/2))

**Deeper behavioral checks**
- **Error-recovery affordance** — grades the *error payload an agent receives* (structured?
  retryable? actionable? no leaked internals?), not just whether the server crashed. [#25]
- **Context Efficiency** — *runtime* response size per tool + pagination hygiene, surfaced
  as a comparable per-server context-footprint number in the Cost headline. [#26]
- **Safety-Contract** (new 6th family) — verifies tool annotations are *true*: a write-named
  tool declaring `readOnlyHint` (bypasses host confirmation) hard-gates the grade. [#28]
- **Selection accuracy + over-triggering gate** — right-tool selection plus a false-fire
  probe for out-of-scope prompts no tool should handle. [#29]
- **Description-quality lints** — ambiguous params, no pagination, leaked low-level
  identifiers (offline, no model). [#30]

**Trust over time**
- **Capability-stability / breaking-change gate** — diffs the tool surface across versions;
  `--no-regressions` fails the PR on silent scope expansion or a breaking schema change. [#27]
- **`pass^k` reliability overlay** — `--reliability K` reports consistency across K runs
  (deterministic families short-circuit), distinct from peak accuracy. [#31]

**Spec conformance**
- **2026-07-28 stateless-conformance** — version-aware `C12` checks: `server/discover`,
  `tools/list` stability across two fresh connections, `_meta` enforcement. [#32]

**Experimental**
- **Spec-surface** (`--experimental`, zero rubric weight) — a reusable message-capture
  harness grades sampling safety, resource resolution, and elicitation safety. [#33]

---

## ✅ Shipped — v0.4: scale, trust & ecosystem (`0.5.0`)

- **Authorization least-privilege** — grades advertised OAuth metadata (OWASP MCP07):
  `A1` scope over-grant, `A2` audience hygiene, `A3` non-HTTPS auth. [#48]
- **Tasks lifecycle** — long-running tasks reach terminal states, honor cancellation, don't
  orphan (`T1`–`T4`), on the spec-surface harness. [#49]
- **Multi-model consensus legibility** — `--models a,b,c` reports inter-model agreement;
  `L7-model-disagreement` is a stronger ambiguity signal than one model's confusion. [#50]
- **Distributed load** — `--distributed N` fans the curve across a worker fleet for a
  fleet-wide percentile picture. [#51]
- **Registry / marketplace integration** — batch scoring + a freshness/staleness check on
  the `mcp-quality serve` API, with a worked GitHub Action + webhook. [#52]

---

## 🔭 Later

- **Cross-host distributed load** — a real multi-machine coordinator on top of the fleet
  aggregation layer (#51 built the in-process harness).
- **Live tasks probe** — activates the tasks lifecycle drive once the SDK's high-level
  server can emit tasks (#49 built the grader + harness).
- **`_meta` enforcement probe** — the last not-measured stateless signal (#32/#22).

---

*Issues live in the [tracker](https://github.com/swarmproof/mcp-probe/issues); changes land
in [`CHANGELOG.md`](./CHANGELOG.md).*
