# mcp-probe — ARCHITECTURE

> System design for the CI quality suite for MCP servers. Companion to `./PRD.md`.
> Python 3.11+, official MCP SDK, asyncio. Sections marked **⊕ Beyond original spec** extend the v1.0 SPEC.

---

## 1. System overview

mcp-probe is a **pipeline**: connect to a target → discover its surface → fan the discovered surface out to five independent **check-family engines** → merge their findings into a scored **Report** → render (terminal/HTML/JSON/badge) and gate. Two engines are LLM-free and deterministic (the CI-critical fast path); one is LLM-dependent (Legibility) and off the critical path; the rest sit in between.

```
                                   ┌───────────────────────────────────────────┐
   mcp-probe run "python srv.py"   │                 CLI / Config                │
   mcp-probe static ./srv.json ───▶│  (argparse + .mcp-probe.toml + env)         │
   mcp-probe badge / snapshot      └───────────────────────────────────────────┘
                                                     │  RunPlan
                                                     ▼
                        ┌──────────────────────────────────────────────┐
                        │            CONNECT + DISCOVER engine           │
                        │  Transport negotiation:                        │
                        │   stdio · Streamable-HTTP · legacy SSE         │
                        │  Handshake: legacy `initialize`  OR            │
                        │   2026-07-28 `server/discover` + _meta (⊕)     │
                        │  → ServerSurface{tools,resources,prompts,caps} │
                        └──────────────────────────────────────────────┘
                                                     │  ServerSurface (or loaded from JSON dump in `static`)
             ┌───────────────┬───────────────┬───────┴───────┬───────────────┬────────────────┐
             ▼               ▼               ▼               ▼               ▼                ▼
      ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────────┐  ┌───────────┐
      │  CONTRACT  │  │ LEGIBILITY │  │    COST    │  │PERFORMANCE │  │SECURITY-LITE │  │ SNAPSHOT  │
      │  engine    │  │  engine    │  │  engine    │  │  engine    │  │  engine      │  │  store    │
      │  [fast]    │  │  [llm]     │  │  [fast]    │  │  [net]     │  │ [fast]+[net] │  │  [fast]   │
      └────────────┘  └────────────┘  └────────────┘  └────────────┘  └──────────────┘  └───────────┘
             │               │               │               │               │                │
             │  each yields  │  Finding[] + FamilyScore(0-100) + trace events │                │
             └───────────────┴───────────────┼───────────────┴───────────────┘                │
                                              ▼                                                 │
                                 ┌──────────────────────────┐   ◀── baseline diff ─────────────┘
                                 │        SCORER             │
                                 │ weighted mean + hard-gates│
                                 │ → MCPQualityScore(A–F)    │
                                 └──────────────────────────┘
                                              │  Report
                    ┌─────────────────────────┼──────────────────────────┬──────────────────────┐
                    ▼                         ▼                          ▼                      ▼
             report-renderer            report-renderer              JSON emitter          badge emitter
             (terminal, oxblood)        (HTML, oxblood)          (--json, CI gate)        (SVG + shields)
                                                                       │
                                                        --fail-under B → exit code
                                                        --from-probe seed → stampede.yaml (⊕)
```

**Design stance:** engines are **pure functions of `ServerSurface` (+ optional live client)** → `(FamilyScore, list[Finding], list[TraceEvent])`. No engine mutates shared state; the Scorer and Renderer are the only aggregators. This makes every engine independently testable and the fast path trivially deterministic.

---

## 2. Core data model

```python
# ---- discovery ----
@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str | None
    input_schema: dict            # JSON Schema
    output_schema: dict | None    # if declared
    annotations: dict             # readOnlyHint, destructiveHint, etc.

@dataclass(frozen=True)
class ServerSurface:
    tools: tuple[ToolDef, ...]
    resources: tuple[ResourceDef, ...]
    prompts: tuple[PromptDef, ...]
    server_info: dict             # name, version
    capabilities: dict            # negotiated caps
    protocol_version: str         # "2025-11-25" | "2026-07-28" | ...
    transport: Literal["stdio", "streamable-http", "sse"]
    surface_hash: str             # stable hash for snapshot/cache keys

# ---- findings & scoring ----
class Severity(Enum): INFO=0; LOW=1; MEDIUM=2; HIGH=3; CRITICAL=4

@dataclass
class Finding:
    family: str                   # "contract" | "legibility" | ...
    code: str                     # "C5-nondeterminism", "S1-owasp-mcp05", ...
    severity: Severity
    tool: str | None
    message: str
    remediation: str | None       # concrete fix, incl. proposed rewrite / Tool Search hint
    owasp_id: str | None          # for security findings
    source: Literal["builtin","mcp-scan","cisco","mcp-xray"] = "builtin"  # ⊕ provenance
    evidence: dict | None = None

@dataclass
class FamilyScore:
    family: str
    score: float                  # 0..100
    grade: str                    # A..F
    hard_gate_tripped: bool       # e.g. broken contract / critical sec
    findings: list[Finding]

@dataclass
class Report:
    overall_score: float
    overall_grade: str
    families: dict[str, FamilyScore]
    rubric_version: str           # NFR-7 — score comparability
    surface: ServerSurface
    meta: dict                    # timings, model+seed, tool version, provenance hash
```

Every engine implements one interface:

```python
class CheckEngine(Protocol):
    name: str
    requires_live: bool           # True → skipped/degraded in `static` mode
    requires_llm: bool            # True → off the CI-critical fast path
    async def run(self, ctx: ProbeContext) -> FamilyScore: ...

# ProbeContext carries: ServerSurface, an optional live MCPClient, config,
# the model provider (if any), the trace sink, and the loaded snapshot baseline.
```

Adding a sixth family (or a plugin) = implement `CheckEngine` and register it. (pytest-plugin ergonomics.)

---

## 3. Connect + Discover engine (transport + spec-version pipeline)

The single hardest correctness surface, because the MCP spec is mid-transition (RESEARCH §7.2).

**Transports** (via official MCP SDK, wrapped in a thin `MCPClient` façade):
- **stdio** — spawn `command`, speak JSON-RPC over stdin/stdout. Configurable startup timeout (servers may fetch deps on first run — Cisco uses 60 s default; we expose `--stdio-timeout`).
- **Streamable-HTTP** — the preferred remote transport (2026 spec direction).
- **legacy SSE** — still supported by SDKs; flagged by Contract as a forward-compat risk (REQ-C10).

**Handshake negotiation (⊕ version-aware):**

```
connect()
  ├─ try 2026-07-28 path:  send request with _meta{protocolVersion, clientInfo, capabilities}
  │                        then `server/discover`  → capabilities + surface
  │        success → protocol_version = "2026-07-28"; note "stateless-core OK"
  ├─ else fall back to legacy: `initialize` → `initialized` handshake, then tools/list …
  │        success → protocol_version = "2025-11-25"; Contract notes "legacy-only" (REQ-C2)
  └─ else → connection failure Finding (server unreachable / non-conformant)
```

The negotiated `protocol_version` and which paths succeeded become **Contract findings** — "your server only speaks the legacy handshake; the July 2026 stateless core is coming" is itself a graded check.

**Discovery** issues `tools/list`, `resources/list`, `prompts/list` (paginated), builds the immutable `ServerSurface`, computes `surface_hash` (canonical-JSON SHA-256 over tool names+schemas+descriptions) — the key for **both** snapshot diffing and legibility caching.

**`static` offline mode:** skip connect; load a `tools/list` JSON dump (the shape registries/CI already produce) directly into `ServerSurface`. Engines with `requires_live=True` (Performance, live Legibility probes, `--deep-security`, determinism probe) are reported as **"not measured"** (mcp-xray's honest stance), never scored as zero.

---

## 4. The five check-family engines

### 4.1 Contract engine `[fast]`
- **Schema validity** (REQ-C3): validate each `input_schema`/`output_schema` as JSON Schema; resolve `$ref`; flag illegal/ambiguous constructs.
- **Arg synthesis + invocation** (REQ-C4): generate schema-valid args (JSON-Schema-faithful fuzzer with deterministic seed), invoke, validate result against `output_schema`.
- **Determinism probe** (REQ-C5): invoke twice; structural-diff results; subtract declared-volatile paths; flag undeclared nondeterminism.
- **Handshake/version** (REQ-C2) and **JSON-RPC framing** (REQ-C1): from the connect engine's negotiation record.
- **Hard-gate:** any conformance break (bad framing, schema-invalid tool, contract violation) trips the Contract hard-gate → overall capped at C.
- Read-only by default (NFR-9); write-classified tools (destructiveHint / heuristic) skipped unless `--allow-writes`.

### 4.2 Legibility engine `[llm]` — **the differentiator** (see §5, dedicated).

### 4.3 Cost engine `[fast]`
- **Toolset token cost** (REQ-$1): serialize the full toolset as it appears in an agent's context (per provider's tool-serialization format) and count tokens.
- **Per-tool weight** (REQ-$2): **leave-one-out** attribution (borrowed from mcp-xray) — recount with each tool removed; the delta is that tool's marginal weight. Robust to shared-prefix effects.
- **Token counting** (REQ-$4): authoritative via provider `count_tokens` when a key is present; deterministic offline tokenizer (e.g. `tiktoken`/local BPE) as the default fast-path counter so `static` stays offline & reproducible.
- **$-per-task** (REQ-$3): toolset tokens × configurable price points × a representative call pattern.
- **Remediation** (REQ-$6, v0.2): if toolset > threshold, emit "adopt Tool Search / lazy loading / Code Mode — projected saving ~N tokens (M%)" with the computed number.
- **Score:** budget-relative — a lean server (≤~2k toolset tokens) scores ~100; degrades toward single digits at GitHub-scale (~55k).

### 4.4 Performance engine `[net]` — reuses **concurrency-core**
- Built on stampede's **concurrency-core** (asyncio swarm scheduler) — mcp-probe is a *thin, adversarially-simple* consumer: instead of heterogeneous persona agents, it drives **uniform MCP clients** issuing real JSON-RPC calls over persistent connections.
- **Concurrency curve** (REQ-P2): ramp → hold → spike, configurable; records p50/p95/p99 per tool and overall.
- **Max stable concurrency** (REQ-P3): binary-search / step up until error-rate threshold breached.
- **Degradation grade** (REQ-P4): classify behavior under load — *graceful* (slows), *clean-fail* (proper JSON-RPC errors), or *crash* (connection drops / non-conformant).
- **Leak detection** (REQ-P5): monitor server FD/connection count (where observable) + client-side unclosed connections over a sustained hold; a rising baseline = leak Finding.
- **Determinism note:** Performance is inherently non-deterministic (wall-clock); its *findings* feed the score but the raw latencies are excluded from the byte-identical fast-path comparison (NFR-2 applies to fast path only).

### 4.5 Security-lite engine `[fast]` + `[net]` integration
- **Built-in `[fast]` (own the 80%):** injection-pattern lint in descriptions/resources (prompt-injection strings, hidden-instruction markers), secrets-in-config regex+entropy, dangerous-capability flags — each mapped to an **OWASP MCP Top 10** ID (REQ-S1–S3).
- **`--deep-security` `[net]` adapter (defer the 20%):** see §8.
- **Dedup + provenance** (REQ-S5): all findings carry `source` + `owasp_id`; the merger dedups builtin vs external findings on (owasp_id, tool) and prefers the higher-fidelity source.
- **Hard-gate:** a CRITICAL security finding caps overall at C.

---

## 5. The Legibility engine (the moat) — detailed design

Legibility is the differentiator and the riskiest engine (LLM cost + flakiness). Design goals: **credible** (methodology borrowed from LiveMCP-101), **deterministic** (seeded + cached), **cheap** (small local models, off the CI-critical path), **actionable** (proposes rewrites).

```
                      ServerSurface.tools
                             │
        ┌────────────────────┼─────────────────────────┐
        ▼                    ▼                          ▼
 ┌──────────────┐   ┌──────────────────┐      ┌────────────────────┐
 │ Static lints │   │  Goal generation │      │  Embedding pass     │
 │ (REQ-L3)     │   │  (from tool descs│      │  (offline           │
 │ [fast]       │   │   or seed set)   │      │   disambiguation)   │
 │ vague params,│   │   [llm, seeded]  │      │   cosine-similar    │
 │ no examples, │   └──────────────────┘      │   tool pairs → shortlist
 │ over-long    │            │                └────────────────────┘
 └──────────────┘            ▼                          │
                    ┌──────────────────┐                │
                    │ Comprehension    │◀──────shortlist┘
                    │ probe (REQ-L1)   │
                    │  small agent w/   │   For each goal:
                    │  `naive` persona  │   present toolset → which tool?
                    │  picks a tool     │   compare vs golden label
                    └──────────────────┘
                             │  per-goal (chosen, correct?, confused_with)
                             ▼
                 ┌───────────────────────────┐
                 │ Disambiguation matrix     │  N×N confusion counts
                 │ (REQ-L2)                  │  "34% chose delete when archive was right"
                 └───────────────────────────┘
                             │
                             ▼
                 ┌───────────────────────────┐
                 │ Rewrite proposer (REQ-L5) │  for low-scoring / confused tools:
                 │  [llm]                    │  emit a concrete better description
                 └───────────────────────────┘
                             │
                     LegibilityScore + Finding[] (+ rewrites) + cache write
```

**Small-model comprehension scoring (REQ-L1).**
- A minimal `naive` **persona** (reused from persona-pack) is given a natural-language goal and the toolset (names+descriptions only — no bodies), and must pick the single tool it would call. We measure **right-tool-selection rate**. This is a scoped, single-decision task — cheap and reliable on small models, unlike full task execution.
- **Goals** come from two sources: (a) an author-provided seed set, or (b) LLM-generated from each tool's own description (each tool implies ≥1 goal it *should* win). Goal-set is **versioned** (`goal_set_version`) so scores stay comparable (REQ-L4).

**Disambiguation matrix (REQ-L2).** An N×N matrix of "goal truly targets tool i, agent chose tool j." Off-diagonal mass = confusion. Reported as the screenshot-worthy artifact: `archive_record ⇄ delete_record: 34% confusion`. An **offline embedding pass** (cosine similarity of tool descriptions) pre-shortlists likely-confusable pairs so the LLM probe focuses its budget — and gives `static` mode a heuristic-only matrix.

**Determinism & caching (REQ-L4, REQ-L6) — the flakiness answer.**
- Canonical scorer is a **pinned local model** (e.g. a specific small Qwen/Llama via Ollama) at **temperature 0** with a **fixed seed**; cloud models are opt-in and marked non-canonical in the report.
- Cache key = `(surface_hash, model_id, seed, goal_set_version)`. A rerun with an unchanged surface is a **cache hit → ~$0, instant, byte-identical** — which also satisfies the "reproducible legibility score" test (TEST-PLAN).
- Because the key includes `surface_hash`, changing a tool description correctly invalidates only the affected cache entries.

**Seeding & the goal set.** Ships with a default goal set derived from the toolset; authors can commit `.mcp-probe/goals.yaml` for domain-specific goals. Golden labels (which tool *should* win a goal) are author-declared or inferred-and-confirmed.

**Rewrite proposer (REQ-L5 → auto-fix PR REQ-L7 v0.2).** For each low-scoring/confused tool, the LLM proposes a rewritten description that (re)establishes distinctness; v0.2 opens a PR applying accepted rewrites. This operationalizes AEO for MCP.

---

## 6. Snapshot / regression mechanism

- **Baseline:** `mcp-probe snapshot` writes `.mcp-probe/snapshot.json` = `{surface_hash, per-tool {name, description_hash, schema_hash}, family_scores, rubric_version}` — committed to the repo (the pytest-snapshot pattern for MCP).
- **Diff:** every `run` loads the baseline (if present) and reports **added / removed / changed** tools and **score deltas** per family. Changed tool → shows *what* changed (description vs schema) and whether a **contract broke**.
- **Gate:** `--no-regressions` ⊕ exits non-zero if any family score dropped or any contract broke vs baseline — independent of absolute grade. This is how "your last commit silently broke a tool" surfaces in the PR.
- **Update:** `mcp-probe snapshot --update` (like `pytest --snapshot-update`) after an intentional change.

---

## 7. JSON output schema for CI

`--json` emits a stable, versioned document (the machine contract; also what registries and the badge consume):

```json
{
  "schema": "mcp-probe/report@1",
  "rubric_version": "2026.07.1",
  "tool_version": "0.1.0",
  "target": { "transport": "stdio", "command": "python my_server.py",
              "protocol_version": "2026-07-28", "surface_hash": "sha256:…" },
  "overall": { "score": 82, "grade": "B", "hard_gate": null },
  "families": {
    "cost":        { "score": 71, "grade": "C", "weight": 0.30,
                     "metrics": { "toolset_tokens": 8140, "usd_per_task": 0.021 },
                     "findings": [ { "code": "$2-bloat", "tool": "search_all",
                                     "severity": "medium", "message": "…",
                                     "remediation": "split into 2 tools; ~1.9k tokens saved" } ] },
    "legibility":  { "score": 78, "grade": "C", "weight": 0.25,
                     "metrics": { "selection_rate": 0.83, "top_confusion": ["archive_record","delete_record",0.34] },
                     "model": "ollama:qwen2.5-3b", "seed": 42, "goal_set_version": "1",
                     "findings": [ … ] },
    "contract":    { "score": 100, "grade": "A", "weight": 0.20, "hard_gate": false, "findings": [] },
    "performance": { "score": 88, "grade": "B", "weight": 0.15,
                     "metrics": { "p95_ms": 240, "p99_ms": 610, "max_concurrency": 120,
                                  "degradation": "graceful", "leak": false } },
    "security":    { "score": 90, "grade": "A", "weight": 0.10, "hard_gate": false,
                     "findings": [ { "code": "S1", "owasp_id": "MCP05", "source": "builtin", … } ] }
  },
  "regression": { "baseline": "sha256:…", "changed_tools": ["search_all"],
                  "broken_contracts": [], "score_delta": { "cost": -4 } },
  "provenance_hash": "sha256:…"
}
```

Exit codes: `0` pass · `1` gate failure (`--fail-under` / `--no-regressions`) · `2` probe error (unreachable / non-conformant).

---

## 8. `--deep-security` integration adapter

A normalizing shell-out layer, **not** a reimplementation (RESEARCH §2.1). Cooperate with incumbents.

```
SecurityLite.run()
  ├─ builtin fast checks (always)                    → Finding[](source=builtin)
  └─ if --deep-security:
        ├─ discover installed scanners on PATH (mcp-scan, mcp-scanner/cisco)
        ├─ invoke each with the same target (or the tools/list dump in static)
        │     e.g. `mcp-scanner --analyzers security,readiness --server-url … --json`
        ├─ parse each tool's native JSON  → normalize to Finding(source=…, owasp_id=…)
        ├─ suppress obvious FPs (the YARA 78%-FP problem) via a confidence filter
        └─ merge + dedup on (owasp_id, tool); prefer higher-fidelity source
```

- Adapters are pluggable (`SecurityAdapter` protocol: `available() -> bool`, `scan(target) -> list[Finding]`). Ships with `McpScanAdapter`, `CiscoAdapter`; Cisco's **readiness** analyzer can optionally feed the Performance/Contract families (REQ-S6).
- Missing scanner → reported "not measured", never a failure (graceful degradation, NFR-8).

---

## 9. `stampede --from-probe` handoff contract ⊕

The flagship ecosystem link (RESEARCH §6). mcp-probe already did connect+discover; stampede's `MCPTarget` needs exactly that plus a `stampede.yaml`.

**Contract:** `mcp-probe run … --emit-stampede ./stampede.seed.json` writes a handoff document; `stampede --from-probe ./stampede.seed.json` consumes it and boots a full simulation of the same server.

```json
{
  "schema": "swarmproof/probe-handoff@1",
  "target": { "type": "mcp", "transport": "stdio", "command": "python my_server.py",
              "protocol_version": "2026-07-28" },
  "surface": { "surface_hash": "sha256:…", "tools": [ /* discovered ToolDef[] */ ] },
  "probe_report_ref": "./mcp-probe-report.json",
  "hotspots": {
    "confusable_tool_pairs": [ ["archive_record","delete_record",0.34] ],
    "expensive_tools": ["search_all"],
    "slow_tools": ["export_dataset"],
    "nondeterministic_tools": ["get_status"]
  },
  "suggested_stampede_yaml": {
    "target": { "type": "mcp", "transport": "stdio", "command": "python my_server.py" },
    "population": { "size": 200, "mix": { "naive": 0.5, "expert": 0.2, "adversarial": 0.05 } }
  },
  "trace_baseline": "./probe.trace.jsonl"
}
```

- **Why it's clean:** both tools share `trace-format`, `persona-pack`, and the `MCPTarget` shape (`discover()/invoke()/reset()`). mcp-probe fills stampede's discovery + a *prior* on where to look (confusable pairs become stampede's misuse-map focus; expensive tools become costbomb seeds).
- **Narrative:** "your server scored a B — now watch 200 agents actually use it." The static grade motivates the dynamic sim; the dynamic sim explains the static grade.

---

## 10. Shared-primitive reuse (vendor-first)

| Primitive | Reuse | Coupling note |
|---|---|---|
| **concurrency-core** | Performance engine's load driver | Vendored; extract to `agent-reliability-core` at ~stampede v0.2. mcp-probe uses only the scheduler + concurrency-curve API, not persona logic. |
| **report-renderer** | terminal + HTML report (oxblood) | Vendored; mcp-probe registers a `QualityScoreReport` view. |
| **trace-format** | Legibility + Performance emit; handoff baseline | Consume the schema, don't fork it — the handoff depends on cross-tool trace compatibility. |
| **persona-pack** | minimal `naive` persona for Legibility probe | Consume one persona; full packs stay stampede's concern. |

---

## 11. Architecture Decision Records (ADR-style)

| ADR | Decision | Rationale | Alternatives rejected |
|---|---|---|---|
| **ADR-001** | Engines are pure functions of `ServerSurface`; Scorer/Renderer are the only aggregators. | Independent testing; trivial fast-path determinism; plugin extensibility. | Shared mutable pipeline state (harder to test/parallelize). |
| **ADR-002** | Zero-LLM fast path (Contract+Cost+Performance) is the CI default; Legibility is opt-in. | CI must be cheap, fast, deterministic (NFR-1..3). | LLM-in-the-critical-path (flaky, costly, blocks merges). |
| **ADR-003** | Version-aware connect: negotiate 2026-07-28 stateless path, fall back to legacy handshake, grade the result. | Spec is mid-transition; forward-compat is itself a check. | Assume one spec version (breaks on half the ecosystem). |
| **ADR-004** | Canonical Legibility scorer = pinned local model, temp 0, fixed seed, cached by `surface_hash`. | Determinism + near-zero rerun cost answers the flakiness risk. | Cloud model as canonical (nondeterministic, costly, version-drift). |
| **ADR-005** | `--deep-security` shells out and normalizes; never reimplements scanners. | Cooperate with incumbents; avoid the crowded lane; dedup their noise. | Building our own YARA/LLM-judge engine (duplicative, 78%-FP trap). |
| **ADR-006** | `static` mode reports live-only checks as "not measured", never 0. | Honest scores (mcp-xray precedent); enables air-gapped registry scoring. | Zeroing unmeasured checks (punishes offline use, gameable). |
| **ADR-007** | Re-derive token counting (real `count_tokens` + leave-one-out) rather than depend on mcp-xray, but credit it as prior art. | Keeps the suite self-contained; the measurement is small; avoids a positioning fight. | Wrapping mcp-xray (adds a dependency + a competitor in the critical path). *Revisit if mcp-xray exposes a clean lib API.* |
| **ADR-008** | Rubric + goal-set are versioned in every report/badge. | Score comparability over time (NFR-7); honest historical tracking. | Unversioned scores (silently incomparable across releases). |
| **ADR-009** | Read-only by default; destructive invocation behind `--allow-writes`. | Safety (NFR-9); matches mcp-xray's no-side-effect stance. | Invoking freely (probing a `delete_*` tool nukes real data). |

---

## 12. Failure modes & handling

| Failure | Handling |
|---|---|
| Server unreachable / non-conformant | Exit 2; Contract records the failure; other live engines "not measured". |
| stdio server slow first-run (dep download) | `--stdio-timeout` (default 60 s, Cisco-parity); retry once. |
| No LLM provider configured | Legibility "not measured"; fast path still produces a gradable score. |
| No model determinism (cloud drift) | Report marks score non-canonical; recommend the pinned local model. |
| `--deep-security` scanner absent | "not measured"; no failure. |
| Rubric changed vs baseline | Regression diff notes `rubric_version` mismatch; refuses silent comparison. |
| Destructive tool encountered | Skipped unless `--allow-writes`; noted in Contract. |
