# mcp-probe — DELIVERY PLAN

> How the wedge ships. mcp-probe is **#3 in the portfolio but the first *code* tool to launch** (after the two presence repos, #7 awesome-agent-reliability and #6 agent-postmortems). Portfolio window: **Weeks 2–6** (Phase B). Companion to `./PRD.md` and `./ARCHITECTURE.md`.
>
> Effort sizing assumes the author working evenings/weekends alongside Xerberus (honest capacity from the portfolio roadmap), so the plan is sequenced for **fastest credible launch**, not maximal scope.

---

## 1. Guiding constraints (what makes this ship fast)

1. **Fast path first.** Contract + Cost + Performance are LLM-free and deterministic. They are the smallest, most reliable, most demoable slice — build them first; they alone justify "pytest for MCP."
2. **Legibility is the headline but the hardest.** It is the launch differentiator and the riskiest (LLM cost/flakiness). Build it *third*, after the fast path proves the pipeline, so a slip there doesn't block a launchable tool.
3. **Vendor the shared primitives.** Don't wait on stampede to extract `concurrency-core`/`report-renderer`/`trace-format`. Copy minimal versions now (portfolio decision: vendor-first). mcp-probe can even be where `report-renderer`'s terminal path is first proven.
4. **Cooperate, don't build.** `--deep-security` is a shell-out adapter — days, not weeks. Never on the critical path to launch.
5. **The leaderboard is content, not scope.** Scoring 20 public servers is a *use* of v0.1, produced during launch week — no extra engineering.

---

## 2. Milestones

### v0.1 — "the gate" (launch) · target: end of portfolio Week 6

**Definition:** one command grades any MCP server across all five families, gates CI, prints a badge, snapshots for regression, and runs offline. Launch on HN.

Scope: REQ-C1–C8, REQ-L1–L6, REQ-$1–$4, REQ-P1–P6, REQ-S1–S5; NFR-1..11; badge; `static`; `--fail-under`; `--no-regressions`.

### v0.2 — "the flywheel" · target: ~Weeks 8–12 (parallel with exactly-once/stampede)

**Definition:** the tool starts generating distribution and stickiness.
Scope: Legibility **auto-fix PR** (REQ-L7), **registry scoring API** + hosted static scoring, **historical score tracking** + PR score-delta comment, Cost response-bloat + remediation hints (REQ-$5–$6), Contract error-path + forward-compat lint (REQ-C9–C10), Cisco readiness adapter (REQ-S6).

### v0.3 — "the on-ramp" · target: aligned with stampede v0.1 (Weeks 12–16)

**Definition:** mcp-probe becomes the front door to the whole toolkit.
Scope: **`stampede --from-probe` handoff** (the emit-stampede contract, ARCHITECTURE §9), multi-model consensus legibility (REQ-L8), distributed load (Ray), marketplace partnerships.

---

## 3. Work breakdown structure (v0.1)

Effort scale: **XS** ≤0.5d · **S** ~1d · **M** ~2–3d · **L** ~1wk (evening-scale days).

| WBS | Work item | Family/area | Effort | Depends on | DoD |
|---|---|---|---|---|---|
| **W0. Scaffolding** | | | | | |
| 0.1 | Package skeleton, CLI (`run`/`static`/`snapshot`/`badge`), config loader, exit codes | infra | S | — | `mcp-probe --help` works; CI stub green |
| 0.2 | Core data model (`ServerSurface`, `Finding`, `FamilyScore`, `Report`, `CheckEngine`) | infra | S | 0.1 | types + serialization round-trip tested |
| 0.3 | Vendor `report-renderer` (terminal path, oxblood) | shared | M | 0.2 | graded report renders in terminal |
| 0.4 | Vendor `trace-format` schema + sink | shared | XS | 0.2 | engines can emit trace events |
| **W1. Connect + Discover** | | | | | |
| 1.1 | `MCPClient` façade over official SDK — stdio transport | connect | M | 0.2 | connect+discover a sample stdio server |
| 1.2 | Streamable-HTTP + legacy SSE transports | connect | M | 1.1 | connect to an HTTP sample server |
| 1.3 | **Version-aware handshake** negotiation (legacy `initialize` ↔ 2026-07-28 `server/discover`) | connect | M | 1.1 | both paths negotiated; `protocol_version` set |
| 1.4 | `ServerSurface` build + `surface_hash` + `static` JSON loader | connect | S | 1.1 | offline dump → ServerSurface |
| **W2. Fast-path engines** | | | | | |
| 2.1 | Contract: schema validity, arg synthesis, invocation, output conformance | contract | M | 1.4 | grades a sample server's contracts |
| 2.2 | Contract: determinism probe + JSON-RPC framing + handshake findings | contract | S | 2.1 | flags an intentionally nondeterministic tool |
| 2.3 | Cost: toolset + per-tool leave-one-out token counting (offline tokenizer) | cost | M | 1.4 | reports token weights; matches hand count |
| 2.4 | Cost: `count_tokens` provider path + $-per-task | cost | S | 2.3 | authoritative counts when key present |
| 2.5 | Performance: vendor `concurrency-core`; MCP load driver; p50/95/99; max-concurrency; degradation; leak | perf | L | 1.2 | load curve → latency percentiles on sample |
| **W3. Legibility (differentiator)** | | | | | |
| 3.1 | Provider-agnostic small-model layer (Anthropic + OpenAI-compatible + Ollama) | legibility | M | 0.2 | one prompt runs on all three |
| 3.2 | Static lints (REQ-L3) + offline embedding disambiguation shortlist | legibility | M | 1.4 | flags vague/over-long descriptions |
| 3.3 | Comprehension probe + goal generation + golden labels | legibility | L | 3.1 | selection-rate on sample; seeded reproducible |
| 3.4 | Disambiguation matrix + confusion rates | legibility | M | 3.3 | `delete⇄archive` confusion reported |
| 3.5 | Rewrite proposer + cache keyed by (surface_hash,model,seed,goal-set) | legibility | M | 3.3 | rerun = cache hit, byte-identical |
| **W4. Security-lite** | | | | | |
| 4.1 | Built-in injection/secrets/dangerous-cap lints + OWASP mapping | security | M | 1.4 | findings carry OWASP IDs |
| 4.2 | `--deep-security` adapters (mcp-scan, Cisco) + normalize/dedup/provenance | security | M | 4.1 | folds external findings when installed |
| **W5. Scorer + outputs** | | | | | |
| 5.1 | Scorer: weighted mean + hard-gates + letter grades + `rubric_version` | scoring | M | 2.*,3.*,4.* | overall MCP Quality Score computed |
| 5.2 | JSON emitter + `--fail-under` + exit codes | outputs | S | 5.1 | CI gate fails/passes correctly |
| 5.3 | Snapshot store + diff + `--no-regressions` + `snapshot --update` | outputs | M | 5.1 | "commit broke a contract" surfaces |
| 5.4 | Badge emitter (SVG + shields JSON endpoint) | outputs | S | 5.1 | `mcp-probe: A` badge renders |
| 5.5 | HTML report view | outputs | S | 0.3,5.1 | shareable HTML report |
| **W6. Launch prep** | | | | | |
| 6.1 | README demo GIF (legibility matrix + token number), GH Action example | docs | S | 5.* | copy-paste CI snippet works |
| 6.2 | 20-server leaderboard run + writeup | content | M | 5.* | leaderboard table published |
| 6.3 | Launch essay: "Your MCP server scores a C" | content | M | 6.2 | draft ready |

**Critical path:** 0.1 → 0.2 → 1.1 → 1.4 → {2.1, 2.3} → 5.1 → 5.2 → launchable-fast-path. Legibility (W3) and Performance (2.5) run in parallel off 1.x and rejoin at 5.1.

---

## 4. Sequencing — the fast path to launch

```
Week 2  ├─ W0 scaffolding ──┬─ 1.1 stdio connect ── 1.4 surface/static
        │                   │
Week 3  │                   ├─ 2.1/2.2 Contract ─┐
        │                   ├─ 2.3/2.4 Cost ──────┤  (FAST PATH = demoable "pytest for MCP")
        │  1.2 HTTP/SSE ────┴─ 2.5 Performance ───┤   ◀── internal milestone: gradable score, zero-LLM
        │  1.3 version-aware handshake             │
Week 4  ├─ 3.1 model layer ─ 3.2 lints ─ 3.3 comprehension ─ 3.4 matrix ─ 3.5 cache   (LEGIBILITY)
        │  4.1 security-lite built-in                                                  (parallel)
Week 5  ├─ 5.1 scorer ─ 5.2 gate ─ 5.3 snapshot ─ 5.4 badge ─ 5.5 html
        │  4.2 --deep-security (if time; not launch-blocking)
Week 6  └─ 6.1 README/GIF ─ 6.2 leaderboard ─ 6.3 essay ─ ▶ SHOW HN
```

**Internal "shippable" gate (end Week 3):** the zero-LLM fast path grades a real server end-to-end with a JSON gate. This is the honest minimum that could launch *if* legibility slips — it's still "the first CI gate for MCP contracts/cost/perf." Legibility upgrades it from useful to remarkable.

---

## 5. Effort summary

| Milestone | Aggregate effort (evening-days) | Calendar (honest capacity) |
|---|---|---|
| v0.1 fast path (W0–W2 + scorer/outputs subset) | ~12–15 | Weeks 2–3.5 |
| v0.1 legibility + security + full outputs | ~10–12 | Weeks 4–5 |
| v0.1 launch prep | ~4–5 | Week 6 |
| **v0.1 total** | **~26–32** | **Weeks 2–6** |
| v0.2 | ~15–20 | Weeks 8–12 |
| v0.3 | ~12–15 | Weeks 12–16 (with stampede) |

---

## 6. Definition of Done (v0.1)

- [ ] `pip install mcp-probe && mcp-probe run "python sample_server.py"` prints a graded A–F report + MCP Quality Score in the terminal.
- [ ] `--json` emits the versioned schema (ARCHITECTURE §7); `--fail-under B` sets exit code correctly.
- [ ] Fast path (Contract+Cost+Performance) runs with **no LLM**, deterministically, in < 30 s on a 30-tool server (NFR-3).
- [ ] Legibility produces a seeded, cached, reproducible selection-rate + disambiguation matrix; rerun is a cache hit.
- [ ] `mcp-probe static ./server.mcp.json` runs offline; live-only checks report "not measured".
- [ ] `mcp-probe snapshot` + `--no-regressions` detects a broken contract / dropped score.
- [ ] `mcp-probe badge` emits a grade badge + shields JSON endpoint.
- [ ] `--deep-security` folds mcp-scan/Cisco findings when installed; degrades cleanly when not.
- [ ] README: <90-second demo GIF above the fold, ≤10-line quickstart, GH Action snippet, sibling links.
- [ ] Test suite green (see TEST-PLAN); CI runs mcp-probe on its own sample servers (dogfood).
- [ ] `CITATION.cff` current; Apache-2.0; 3–5 seeded `good-first-issue`s.

---

## 7. Launch checklist

**Pre-launch (Week 5–6)**
- [ ] Score 20 popular public MCP servers; build the leaderboard table (grade + the token number + top confusion pair per server).
- [ ] Draft essay "Your MCP server has a quality score, and it's probably a C" — lead with the leaderboard + one brutal token number (e.g. 55k tokens before hello).
- [ ] Record the demo GIF: the **disambiguation matrix** and the **token-cost number** (the two things mcp-xray/Cisco show partially and nobody shows *in a CI gate*). Do **not** lead with security (crowded) or RPS (boring).
- [ ] Positioning copy: "quality has point tools; this is the **suite you gate CI on**" — pre-empt the "isn't this mcp-xray?" comment by crediting mcp-xray and naming the four things it doesn't do (load, contract, snapshot, gate/badge).
- [ ] GitHub Action + badge live on mcp-probe's own repo (dogfood the badge).

**Launch day**
- [ ] "Show HN: mcp-probe — lighthouse for MCP servers (lint, benchmark, load-test in CI)."
- [ ] Publish the leaderboard post + essay simultaneously; cross-link from awesome-agent-reliability.
- [ ] Notify the 20 leaderboard server authors (respectfully — "you scored a B, here's why + a PR-able fix").
- [ ] Seed sibling cross-links (stampede "coming: `--from-probe`", org README).

**Post-launch (first 30 days → 500-star target)**
- [ ] Respond to every HN thread, especially the mcp-xray/Cisco comparison (own it graciously).
- [ ] Land the first external repo with mcp-probe in CI (the north-star metric) — offer PRs to willing leaderboard authors.
- [ ] Open the registry-scoring conversation with ≥1 registry (TrueFoundry/Apigene/official) for v0.2.
- [ ] Track badges-in-the-wild; retweet each new one.

---

## 8. Risks to the schedule

| Risk | Likelihood | Mitigation |
|---|---|---|
| Legibility LLM flakiness/cost eats time | High | Pin local model + cache early (3.5 before polishing 3.3); fast path can launch without it. |
| Spec transition churn (2026-07-28 RC moves) | Med | Version-aware connect isolates it to W1.3; grade both, require neither for launch. |
| Shared primitives not ready from stampede | Med | Vendor minimal versions; mcp-probe proves the terminal renderer first. |
| mcp-xml/Cisco ship a competing "suite/gate" before us | Med | Speed is the moat — ship the fast path by Week 3; the portfolio handoff (stampede) is uncopyable. |
| `--deep-security` scanner APIs unstable | Low | Not launch-blocking; adapters degrade to "not measured". |
