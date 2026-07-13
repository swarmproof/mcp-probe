# mcp-probe — PRD

> **The CI quality suite for MCP servers.** Lint, contract-test, benchmark, and load-test any MCP server before you ship it — the `pytest` + `lighthouse` for the servers agents depend on.
>
> Companion to `../SPEC.md` and `./RESEARCH.md`. Requirements are numbered (`REQ-*`, `NFR-*`) and testable. Items marked **⊕ Beyond original spec** extend the v1.0 SPEC.

---

## 1. Vision

Every MCP server, on every commit, gets a letter grade and an **MCP Quality Score** — legible, cheap, correct, fast, and not obviously unsafe — enforced in CI and advertised with a badge, the way web apps get a Lighthouse score and repos get a coverage badge. mcp-probe is the runner and the gate; the badge is the distribution flywheel; `stampede --from-probe` is the upgrade path when a static grade isn't enough.

**One line:** *security scanners tell you if your server is dangerous; mcp-probe tells you if it's good — and blocks the merge when it gets worse.*

---

## 2. Goals / Non-goals

### 2.1 Goals (v0.1)
- G1. Five check families — **Contract, Legibility, Cost, Performance, Security-lite** — runnable as one CLI command against any MCP server (stdio / HTTP transports).
- G2. A graded (A–F) per-family + overall **MCP Quality Score**, rendered in the terminal and as HTML.
- G3. Machine-readable JSON for CI, with a `--fail-under <grade>` gate.
- G4. Snapshot/regression mode: diff tool schemas + descriptions against a committed baseline.
- G5. A README badge (`mcp-probe: A`) as the distribution mechanism.
- G6. `static` offline mode (scan a pre-generated tools/list JSON — no live server).
- G7. A **zero-LLM fast path** (Contract + Cost + Performance) so the CI-critical path is cheap and deterministic.
- G8. `--deep-security` integration adapter (mcp-scan / Cisco mcp-scanner) folding external findings into the unified report.

### 2.2 Non-goals
- N1. **Not** a dedicated security scanner — integrate mcp-scan/Cisco for deep security; own only quality + light security.
- N2. **Not** a runtime firewall / guardrail (that's MCPGuard / Invariant Guardrails).
- N3. **Not** an agent evaluator (that's agentevals) — mcp-probe tests the *server*, not the *agent*.
- N4. **Not** a dynamic behavioral simulator (that's stampede — mcp-probe hands off to it).
- N5. **Not** a hosted SaaS at v0.1 (the registry scoring API in v0.2 is the first hosted surface).
- N6. **Not** a general JSON-RPC load tester — MCP-semantics only.

---

## 3. Personas (see RESEARCH §5 for JTBD detail)

| ID | Persona | Cares most about | Runs it… |
|---|---|---|---|
| P1 | **Builder** (primary) | Gate + badge + regression | pre-commit, PR, release CI |
| P2 | **Adopter** | Security-lite + `--deep-security` + go/no-go | dependency vetting |
| P3 | **Registry operator** | `static` mode at scale, deterministic score | on submission / re-index |
| P4 ⊕ | **Platform/DevRel** | Score trend across many servers | nightly / monorepo CI |
| P5 ⊕ | **Researcher** | Determinism, citability | studies |
| P6 ⊕ | **Framework maintainer** | Default check for their users | framework release |

---

## 4. Functional requirements by check family

Convention: **[fast]** = zero-LLM deterministic path (CI-critical); **[llm]** = requires a small model; **[net]** = requires live server; **[static-ok]** = works in offline `static` mode.

### 4.1 Contract family (LLM-free, fast, deterministic)

| REQ | Requirement | Path | Tier |
|---|---|---|---|
| REQ-C1 | Validate JSON-RPC 2.0 framing of all server responses. | [fast][net] | v0.1 |
| REQ-C2 | **Version-aware handshake check** ⊕ — validate the legacy `initialize`/`initialized` handshake **and** the 2026-07-28 stateless path (`server/discover` + `_meta` per request); flag servers that speak only one. | [fast][net] | v0.1 |
| REQ-C3 | Validate every tool's input JSON Schema is well-formed and self-consistent (types, required, enums, `$ref` resolvable). | [fast][static-ok] | v0.1 |
| REQ-C4 | Invoke each tool with schema-valid synthesized args; assert the result conforms to the declared output shape (if declared). | [fast][net] | v0.1 |
| REQ-C5 | **Determinism probe** — call the same tool twice with identical args; flag undeclared nondeterminism (diff beyond declared volatile fields). | [fast][net] | v0.1 |
| REQ-C6 | Validate resources & prompts discovery (`resources/list`, `prompts/list`) shape conformance. | [fast][net] | v0.1 |
| REQ-C7 | **Snapshot baseline** — hash+serialize tool descriptions + schemas to a committed `.mcp-probe/snapshot.json`. | [fast][static-ok] | v0.1 |
| REQ-C8 | **Snapshot diff** — on rerun, diff against baseline; report added/removed/changed tools and *broken contracts* ("commit changed 3 descriptions, broke 1 contract"). | [fast][static-ok] | v0.1 |
| REQ-C9 | Error-path conformance — send malformed / out-of-schema requests; assert spec-compliant JSON-RPC error objects (correct codes), not crashes. | [fast][net] | v0.2 |
| REQ-C10 ⊕ | Forward-compat lint — flag SSE-only remotes and missing `server/discover` as transition risks. | [fast] | v0.2 |

### 4.2 Legibility family (the differentiator — [llm])

| REQ | Requirement | Path | Tier |
|---|---|---|---|
| REQ-L1 | **Agent-comprehension score** — run small seeded LLM agents against the toolset with representative goals; measure right-tool-selection rate. | [llm][net] | v0.1 |
| REQ-L2 | **Disambiguation matrix** — detect confusable tool pairs (the `delete_record` vs `archive_record` problem); report per-pair confusion rate. | [llm][static-ok*] | v0.1 |
| REQ-L3 | Description-quality lints — missing examples, vague params, undocumented failure modes, over-long descriptions wasting context. | [fast][static-ok] | v0.1 |
| REQ-L4 | **Determinism controls** — seedable models; pinned canonical local model; versioned golden-goal set; results reproducible run-to-run. | [llm] | v0.1 |
| REQ-L5 | **Proposed rewrites** — for each low-scoring description, emit a concrete rewrite suggestion (operationalizing AEO). | [llm] | v0.1 |
| REQ-L6 | Cache legibility results keyed by (schema-hash, model, seed, goal-set-version) to avoid re-paying LLM cost. | [llm] | v0.1 |
| REQ-L7 ⊕ | **Auto-fix PR** — open a PR that applies accepted rewrites to the server's tool descriptions. | [llm] | v0.2 |
| REQ-L8 ⊕ | Multi-model consensus legibility — score across ≥2 model families; flag descriptions only one family understands. | [llm] | v0.3 |

*REQ-L2 static-ok: a heuristic/embedding-similarity disambiguation pass runs offline; the behavioral confusion rate needs a live/LLM path.

### 4.3 Cost family ([fast], mostly)

| REQ | Requirement | Path | Tier |
|---|---|---|---|
| REQ-$1 | Token cost of the **entire toolset** in context (what every agent pays just to see your tools). | [fast][static-ok] | v0.1 |
| REQ-$2 | Per-tool token weight (leave-one-out attribution); flag bloated tools. | [fast][static-ok] | v0.1 |
| REQ-$3 | Estimated $-per-typical-task across configurable model price points. | [fast][static-ok] | v0.1 |
| REQ-$4 | Authoritative token counts via the provider's `count_tokens` where available; deterministic tokenizer fallback offline. | [fast] | v0.1 |
| REQ-$5 ⊕ | **Response bloat** — sample tool outputs and measure response token weight, not just schema weight (the second half of the "context tax"). | [net] | v0.2 |
| REQ-$6 ⊕ | **Remediation hints** — recommend Tool Search / lazy-loading / Code Mode when schema bloat exceeds a threshold, with the projected token saving. | [fast] | v0.2 |

### 4.4 Performance family ([net] — the k6-can't-do-this lane)

| REQ | Requirement | Path | Tier |
|---|---|---|---|
| REQ-P1 | Concurrent-agent load with **real MCP client semantics** (persistent SSE/Streamable-HTTP, JSON-RPC), not naive HTTP. | [net] | v0.1 |
| REQ-P2 | p50/p95/p99 latency per tool and overall, under a configurable concurrency curve (ramp / hold / spike). | [net] | v0.1 |
| REQ-P3 | Max stable concurrent connections before error-rate threshold breached. | [net] | v0.1 |
| REQ-P4 | Graceful-degradation check — does the server slow, error cleanly, or crash under load? | [net] | v0.1 |
| REQ-P5 | Connection / file-descriptor leak detection over sustained load. | [net] | v0.1 |
| REQ-P6 | Reuse stampede's **concurrency-core** — import its `Scheduler` / `Executor` **Protocol** (the binding contract) as the load engine. | [net] | v0.1 |
| REQ-P7 ⊕ | Cold-start / first-response latency measurement (matters for stdio servers that fetch deps on first run). | [net] | v0.2 |

### 4.5 Security-lite family ([fast] built-in; [net] integration)

| REQ | Requirement | Path | Tier |
|---|---|---|---|
| REQ-S1 | Built-in lint for obvious injection patterns in tool/resource descriptions, mapped to **OWASP MCP Top 10** IDs. | [fast][static-ok] | v0.1 |
| REQ-S2 | Secrets-in-config detection (hard-coded tokens/keys — OWASP MCP01). | [fast][static-ok] | v0.1 |
| REQ-S3 | Dangerous-capability flagging (shell/exec/file-write tools) with OWASP mapping. | [fast][static-ok] | v0.1 |
| REQ-S4 | **`--deep-security`** — shell out to mcp-scan and/or Cisco mcp-scanner; normalize + fold their findings into the unified report (dedup, attribute source, suppress obvious FPs). | [net] | v0.1 |
| REQ-S5 ⊕ | Findings dedup + provenance — every security finding carries `source: builtin|mcp-scan|cisco` and an OWASP ID; conflicting/duplicate findings merged. | [fast] | v0.1 |
| REQ-S6 ⊕ | Cisco **readiness** adapter — optionally fold Cisco's 20 readiness heuristics into the Performance/Contract families rather than re-deriving. | [net] | v0.2 |

---

## 5. Non-functional requirements

| NFR | Requirement | Target |
|---|---|---|
| NFR-1 | **Zero-LLM fast path** — Contract + Cost + Performance run with no model calls. | 100% of these families offline-capable |
| NFR-2 | **Determinism** — identical inputs → identical fast-path output; LLM path reproducible under a fixed seed+model+goal-set. | byte-identical fast-path JSON |
| NFR-3 | **CI runtime** — fast path on a 30-tool server. | < 30 s wall-clock (excl. load duration) |
| NFR-4 | **LLM cost** — a full legibility run on a 30-tool server with the default small model. | < $0.10, cached to ~$0 on rerun |
| NFR-5 | **CI ergonomics** — single binary/pip install; one command; non-zero exit on gate failure; GitHub Actions example in README. | `pip install mcp-probe` → `mcp-probe run` |
| NFR-6 | **Provider-agnostic** — any OpenAI-compatible endpoint + Anthropic SDK; Ollama-friendly; degrades to no-LLM. | ≥3 provider paths + Ollama |
| NFR-7 | **Determinism of the score** — rubric versioned in JSON (`rubric_version`) and badge so historical scores stay comparable. | rubric_version present in every report |
| NFR-8 | **Offline / air-gapped** — `static` mode needs no network. | full Contract+Cost+Security-lite offline |
| NFR-9 | **No side effects** — read-only by default; destructive tool invocation gated behind explicit `--allow-writes` (mirrors mcp-xray's no-side-effect stance). | writes blocked unless opted in |
| NFR-10 | **Spec-version awareness** — support 2025-11-25 (legacy handshake) and 2026-07-28 RC (stateless/`server/discover`). | both transports negotiated |
| NFR-11 | Python 3.11+; official MCP SDK; Apache-2.0. | — |

---

## 6. Complete feature set by tier

| Family | v0.1 (launch) | v0.2 | v0.3 |
|---|---|---|---|
| **Contract** | JSON-RPC conformance, version-aware handshake, schema validity, determinism probe, resources/prompts, snapshot baseline+diff | error-path conformance, forward-compat lint | contract fuzzing (schema-boundary inputs) |
| **Legibility** | comprehension score, disambiguation matrix, description lints, seeded determinism, proposed rewrites, caching | **auto-fix PR**, multi-goal-set | multi-model consensus |
| **Cost** | toolset token cost, per-tool weight, $-per-task, authoritative counts | response bloat, remediation hints (Tool Search/Code Mode) | budget diffing across commits |
| **Performance** | concurrent load, p50/95/99, max-concurrency, degradation, leak detection | cold-start latency, custom curves | distributed load (Ray backend) |
| **Security-lite** | injection lint, secrets, dangerous caps, `--deep-security`, dedup+provenance | Cisco readiness adapter, enterprise-authz lint | — |
| **Cross-cutting** ⊕ | graded report, JSON, `--fail-under`, badge, `static` mode | **registry scoring API**, **historical score tracking**, PR score-delta comment | **`stampede --from-probe` handoff**, marketplace partnerships |

---

## 7. The scoring & grading rubric

### 7.1 Family grades → overall MCP Quality Score

Each family produces a 0–100 sub-score; the overall score is a weighted mean, mapped to a letter grade. **Weights are opinionated and versioned** (`rubric_version`), and reflect what actually hurts agents at runtime.

| Family | Default weight | Rationale |
|---|---|---|
| **Cost** | **30%** | Paid every single turn, whether or not anything works (the mcp-xray insight). Biggest silent tax. |
| **Legibility** | **25%** | Wrong-tool selection is the #1 documented agent failure (LiveMCP-101 <60% success). |
| **Contract** | **20%** | A broken contract is a hard failure, but binary and rare once caught. |
| **Performance** | **15%** | Matters at scale; not all servers hit concurrency. |
| **Security-lite** | **10%** | Deliberately light — deep security is deferred to specialists; this is a floor, not the point. |

**A family scoring an F caps the overall at C** (no A-grade server with a broken contract or a critical security finding — a "hard-gate" override, reported explicitly).

### 7.2 Letter grade bands

| Score | Grade |
|---|---|
| 90–100 | **A** |
| 80–89 | **B** |
| 70–79 | **C** |
| 60–69 | **D** |
| < 60 | **F** |

### 7.3 Sub-score composition (illustrative, per family)

- **Cost** = f(toolset tokens vs budget, per-tool bloat outliers, $-per-task). E.g. ≤2k toolset tokens → 100; scales down; GitHub-scale (55k) → single digits.
- **Legibility** = right-tool-selection rate × (1 − mean confusion rate) − lint-penalty.
- **Contract** = fraction of tools passing schema+determinism+handshake, hard-gated by any conformance break.
- **Performance** = f(p95 under target concurrency vs threshold, degradation grade, leak = automatic penalty).
- **Security-lite** = 100 − Σ(severity-weighted OWASP findings); critical finding hard-gates.

### 7.4 CI gate semantics
- `--fail-under B` → exit non-zero if overall grade < B.
- `--fail-under-family Contract:A,Security:B` ⊕ → per-family gates.
- `--no-regressions` ⊕ → exit non-zero if any family dropped vs the committed snapshot, regardless of absolute grade.

---

## 8. Badge spec ⊕

- Static SVG (shields.io-compatible endpoint + self-hosted fallback), color-keyed to grade (A green → F red).
- Text: `mcp-probe: A` (grade) or `MCP Quality: 92` (score) — configurable.
- Generated by `mcp-probe badge --out badge.svg` and/or a JSON endpoint `{ "schemaVersion": 1, "label": "mcp-probe", "message": "A", "color": "brightgreen" }` for shields.io dynamic badges.
- Embeds `rubric_version` in a tooltip/title so a stale badge is detectable.
- **Anti-gaming:** badge generation records the score's provenance hash; the registry API (v0.2) can re-verify.

---

## 9. Success metrics

| Metric | Target |
|---|---|
| **North star** — repos with mcp-probe in their CI workflow | primary adoption-depth signal |
| Launch — GitHub stars in 30 days | 500+ |
| `mcp-probe: A` badges in the wild | steady climb; screenshot-worthy |
| Registry adoption for automated scoring | ≥1 registry within 6 months |
| Leaderboard reach — the "20 popular MCP servers scored" post | HN front page + inbound |
| Legibility determinism | reproducible score across reruns (test-enforced) |

---

## 10. Dependencies

- **External:** official MCP SDK (Python); a tokenizer + provider `count_tokens` (Anthropic SDK / OpenAI-compatible); Ollama (optional local model); mcp-scan and Cisco mcp-scanner CLIs (optional, `--deep-security`).
- **Internal (shared primitives, vendored — bound to stampede's authoritative contracts):** concurrency-core via its `Scheduler`/`Executor` **Protocol** (load engine); report-renderer rendering the shared **`RunReport`** model (oxblood); **trace-format = the OpenTelemetry GenAI semantic-conventions profile** (`gen_ai.*` + `swarmproof.*` extension), *not* a bespoke schema; persona-pack (`apiVersion: swarmproof.dev/persona/v1`) for the minimal `naive` legibility persona.
- **Downstream consumer:** stampede (`--from-probe`), costbomb (Cost substrate seeds).

---

## 11. Assumptions & constraints

- A1. Target servers are reachable via stdio or HTTP (Streamable-HTTP / legacy SSE); `static` mode covers the rest.
- A2. Legibility LLM calls are opt-in and off the CI-critical path; the gate can be satisfied by the fast path alone.
- A3. The MCP spec is mid-transition (2025-11-25 → 2026-07-28 RC); the tool must speak both and grade the transition, not assume either.
- A4. Shared primitives are vendored (not yet a shared package) per the portfolio decision; extract at ~stampede v0.2.
- C1. Read-only by default; no destructive invocation without `--allow-writes`.
- C2. Determinism of the fast path is a hard requirement — no wall-clock or network-order dependence in scoring.
- C3. Apache-2.0; provider-agnostic; must degrade to no-LLM.
