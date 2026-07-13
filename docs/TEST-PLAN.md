# mcp-probe — TEST PLAN

> How we prove mcp-probe is correct, deterministic, and CI-safe. Companion to `./ARCHITECTURE.md` and `./PRD.md`.
> The tool's whole value proposition is *trustworthy grading in CI* — so its own test suite must be exemplary, and it must **dogfood** (mcp-probe runs on its own sample servers in its own CI).

---

## 1. Strategy & the test pyramid

```
                 ▲  fewer, slower, highest-fidelity
        ┌────────┴─────────┐
        │  E2E (§4)         │  probe real sample MCP servers end-to-end;
        │  ~8 scenarios     │  assert graded report + JSON + gate + badge
        ├──────────────────┤
        │  Integration (§5) │  connect/discover across transports & spec versions;
        │                   │  --deep-security adapters; snapshot round-trip
        ├──────────────────┤
        │  Component (§6)   │  each engine vs golden fixtures; scorer; renderer
        ├──────────────────┤
        │  Unit (§7)        │  token counting, schema validation, arg synthesis,
        │  many, fast       │  diffing, JSON-schema of the report, tokenizer
        └──────────────────┘
```

**Testability principle (from ARCHITECTURE ADR-001):** every engine is a pure function of `ServerSurface` (+ optional live client). So component tests feed a fixed `ServerSurface` and assert an exact `FamilyScore` — no network, no LLM, fully deterministic. Live/LLM behavior is isolated to integration/E2E with controlled fakes.

**Determinism doctrine:**
- **Fast path (Contract/Cost/Performance-scoring, Security-lite built-in):** byte-identical output for identical input. Enforced by golden-file tests (NFR-2).
- **Legibility:** deterministic *under a fixed (model, seed, goal-set)* via a stubbed/pinned model in tests; the cache guarantees rerun-equality (§4.3).
- **Performance latencies:** inherently nondeterministic → assert *invariants* (percentile ordering, leak detection, degradation classification), never absolute ms.

---

## 2. Test fixtures — the sample MCP servers

A `tests/servers/` matrix of tiny purpose-built MCP servers (each exercises specific checks). These double as the demo/leaderboard baselines.

| Fixture server | Designed to fail/expose | Expected grade signal |
|---|---|---|
| `good_server` | nothing — clean, lean, legible | **A** overall |
| `confusable_server` | `delete_record` vs `archive_record` near-identical descriptions | Legibility low; matrix shows high confusion |
| `bloated_server` | 40 tools, verbose schemas (~55k tokens) | Cost near-F; remediation hint emitted |
| `flaky_server` | a tool returning nondeterministic output undeclared | Contract determinism-probe flags it |
| `broken_contract_server` | a tool whose result violates its `output_schema` | Contract hard-gate → capped at C |
| `legacy_only_server` | speaks only 2025-11-25 `initialize` | Contract forward-compat finding |
| `stateless_server` | speaks 2026-07-28 `server/discover` + `_meta` | handshake check passes new path |
| `leaky_server` | leaks connections under sustained load | Performance leak finding |
| `crash_server` | crashes at ~50 concurrent connections | Performance degradation = "crash" |
| `injection_server` | hidden-instruction string in a description | Security-lite OWASP finding |
| `writes_server` | has a `delete_*` tool | skipped unless `--allow-writes` (NFR-9) |
| `dump.mcp.json` | a static tools/list export (no process) | `static` mode path |

All fixtures are pinned; regenerating them is a deliberate `--snapshot-update`-style action.

---

## 3. The stub model (Legibility determinism harness)

Tests never call a real LLM. A **`StubModel`** implements the model-layer protocol and returns deterministic tool choices from a fixture map `{(goal, tool_names): chosen_tool}`. This lets us:
- assert an exact selection-rate and confusion matrix for `confusable_server`,
- prove caching (second run must not invoke the model at all — assert call count == 0),
- prove seed-stability (same seed → same result).
A separate, **opt-in, network-gated** suite (`-m live_llm`) runs the real pinned Ollama model to catch drift, excluded from the default/CI run.

---

## 4. E2E scenarios (Given/When/Then)

> These are the acceptance backbone. Each runs against a fixture server and asserts the *user-visible* contract: terminal report + JSON + exit code + badge.

### E2E-1 — Happy path: probe a clean server, get an A
- **Given** `good_server` and no LLM key configured (fast path only)
- **When** `mcp-probe run "python tests/servers/good_server.py" --json`
- **Then** exit code `0`; JSON `overall.grade == "A"`; all five families present; `contract.hard_gate == false`; `rubric_version` present; wall-clock < 30 s (NFR-3).

### E2E-2 — The gate fails a bad server
- **Given** `bloated_server`
- **When** `mcp-probe run "…bloated_server.py" --fail-under B`
- **Then** exit code `1`; report shows Cost grade ≤ D; a `$2-bloat` finding with a remediation string and a projected token saving.

### E2E-3 — Legibility disambiguation matrix (the headline)
- **Given** `confusable_server` and the `StubModel` (fixed seed, goal-set v1)
- **When** `mcp-probe run … --legibility`
- **Then** JSON `legibility.metrics.top_confusion == ["archive_record","delete_record", r]` with `r ≥ 0.30`; a proposed-rewrite finding exists for at least one of the pair; Legibility grade ≤ C.

### E2E-4 — Legibility determinism / caching
- **Given** E2E-3 just ran (cache warm)
- **When** the identical command runs again
- **Then** output JSON is byte-identical (modulo timing meta); `StubModel.call_count == 0` (served from cache); cache key includes the unchanged `surface_hash`.

### E2E-5 — Snapshot regression catches a silent break
- **Given** `good_server` snapshotted (`mcp-probe snapshot`), then a tool edited so its result violates its schema (simulating a bad commit → `broken_contract_server`)
- **When** `mcp-probe run … --no-regressions`
- **Then** exit code `1`; regression block lists the changed tool, `broken_contracts` non-empty, and a negative `score_delta` for Contract; message reads like "commit changed 1 tool and broke 1 contract."

### E2E-6 — Load-test correctness under real MCP semantics
- **Given** `leaky_server` and `crash_server`
- **When** `mcp-probe run … --performance --concurrency 100`
- **Then** for `leaky_server`: a leak finding (rising connection baseline); for `crash_server`: `performance.metrics.degradation == "crash"` and `max_concurrency < 100`; p95 ≤ p99 (percentile-ordering invariant) in both.

### E2E-7 — Offline `static` mode
- **Given** `dump.mcp.json` and no network
- **When** `mcp-probe static ./tests/servers/dump.mcp.json --json`
- **Then** exit `0`; Contract(schema)+Cost+Security-lite scored; Performance and live-Legibility reported as `"not measured"` (never `0`) (ADR-006); overall score computed from measured families only.

### E2E-8 — `--deep-security` integration folds external findings
- **Given** `injection_server` and a **fake `mcp-scan` on PATH** emitting a known JSON finding
- **When** `mcp-probe run … --deep-security`
- **Then** the report contains both a `source: "builtin"` and a `source: "mcp-scan"` finding; duplicates on `(owasp_id, tool)` are merged; when the fake scanner is absent, security still scores and notes "deep security: not measured" (no failure).

### E2E-9 ⊕ — Badge emission
- **Given** any completed run
- **When** `mcp-probe badge --out badge.svg`
- **Then** an SVG grade badge is written and a shields-compatible JSON endpoint payload validates against the shields schema; `rubric_version` embedded.

### E2E-10 ⊕ — `stampede --from-probe` handoff contract
- **Given** `confusable_server`
- **When** `mcp-probe run … --emit-stampede ./seed.json`
- **Then** `seed.json` validates against `swarmproof/probe-handoff@1`; `hotspots.confusable_tool_pairs` contains the delete/archive pair; `target` + `surface` are populated; a downstream schema-conformance check (stand-in for stampede) accepts it.

---

## 5. Integration tests

| ID | Area | Assertion |
|---|---|---|
| INT-1 | stdio transport | connect + discover `good_server` over stdio; `ServerSurface` fully populated. |
| INT-2 | Streamable-HTTP | same against an HTTP fixture. |
| INT-3 | legacy SSE | connect over SSE; Contract emits forward-compat finding. |
| INT-4 | version-aware handshake | `legacy_only_server` → `protocol_version=="2025-11-25"` + finding; `stateless_server` → `"2026-07-28"` via `server/discover`. |
| INT-5 | stdio slow start | server that sleeps 5 s before responding still connects under default timeout; a >60 s server needs `--stdio-timeout`. |
| INT-6 | deep-security adapters | fake mcp-scan and fake Cisco JSON both normalize to `Finding` with correct `owasp_id`+`source`; FP-suppression filter drops a low-confidence YARA-style flag. |
| INT-7 | snapshot round-trip | `snapshot` then `run` on unchanged server → zero diff; `--update` rewrites baseline. |
| INT-8 | provider layer | one legibility prompt runs against Anthropic-shaped, OpenAI-compatible-shaped, and Ollama-shaped stubs identically. |

---

## 6. Component tests (per engine, golden fixtures, no net/LLM)

- **Contract:** schema-validity on malformed/valid schemas; arg synthesis produces schema-valid args; output-conformance pass/fail; determinism probe on a fixed fake client returning same/different results.
- **Cost:** leave-one-out attribution sums correctly; toolset token count matches a hand-computed golden number for a fixture; offline tokenizer is deterministic; $-per-task math.
- **Legibility (with StubModel):** exact selection-rate; exact N×N confusion matrix; static lints fire on vague/over-long descriptions; embedding shortlist selects the confusable pair.
- **Performance:** given a fake target with scripted latencies, percentile computation is correct (p50/p95/p99); degradation classifier maps scripted behaviors to graceful/clean-fail/crash; leak detector fires on a rising connection count.
- **Security-lite:** each lint maps to the correct OWASP MCP ID; secret-entropy detector precision/recall on a labeled fixture.
- **Scorer:** weighted-mean math; **hard-gate** (F family / critical security → overall capped at C); grade-band boundaries (89→B, 90→A); `rubric_version` stamped.
- **Renderer:** terminal + HTML snapshot tests (golden output).

---

## 7. Unit tests

Report-JSON validates against its own published JSON Schema; `surface_hash` stability (reordering tools doesn't change canonical hash; editing a description does); diff algorithm add/remove/change classification; exit-code mapping; config precedence (flags > file > env > default); badge color mapping.

---

## 8. Determinism & reproducibility acceptance criteria

| Criterion | How verified |
|---|---|
| Fast path is byte-identical across runs | golden-file test on `good_server` JSON (timing fields excluded) |
| Legibility reproducible under fixed (model, seed, goal-set) | E2E-4 + StubModel call-count assertion |
| Cache correctness | changing one description invalidates only its cache entries (surface_hash-scoped) |
| `static` never zeroes unmeasured checks | E2E-7 asserts `"not measured"` sentinel, not `0` |
| Rubric comparability | report always carries `rubric_version`; regression refuses cross-rubric silent comparison (INT-7 variant) |
| No side effects by default | `writes_server`'s destructive tool is not invoked unless `--allow-writes` (audited via a call-log spy) |

---

## 9. CI gates (mcp-probe's own pipeline — dogfooding)

The repo's GitHub Actions workflow must:
1. Run unit + component + integration + E2E (with StubModel) on every PR — **all green required to merge**.
2. **Dogfood:** run `mcp-probe run` against `good_server` and `bloated_server`; assert the former passes `--fail-under B` and the latter fails (proving the gate works on real invocation).
3. Enforce coverage floor on the scoring + connect + diff logic (the correctness-critical core) — e.g. ≥90% on `scorer/`, `connect/`, `snapshot/`.
4. Determinism guard: run the fast path twice, `diff` the JSON — must be identical.
5. `mcp-probe static ./dump.mcp.json` must run in an offline job (no network egress) and succeed.
6. Publish mcp-probe's own badge from its own score (the badge flywheel starts at home).
7. `live_llm`-marked tests run only on a nightly/opt-in job (not on PRs), to catch model drift without flaking the merge path.

---

## 10. Acceptance criteria (ties to Definition of Done)

v0.1 is test-accepted when: **all §4 E2E scenarios pass**, the §8 determinism criteria hold, the §9 CI gates are enforced on the repo itself, and coverage floors in §9.3 are met. Any E2E failure, any nondeterminism in the fast path, or any hard-gate miscomputation is a **release blocker**.
