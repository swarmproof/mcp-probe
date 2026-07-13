# mcp-probe — Design Specification & PRD
### The CI quality suite for MCP server builders
*The wedge project · v1.0 spec*

> **mcp-probe** — lint, contract-test, benchmark, and load-test your MCP server before you ship it. The `pytest` + `lighthouse` for the servers agents depend on.

---

## 1. PRD

### 1.1 The critical positioning insight (from research)

The security-scanning lane is **already contested** and I won't march into it head-on. As of April 2026 there are at least four security-focused MCP scanners: Invariant Labs' **mcp-scan** (config-level: tool poisoning, rug pulls, cross-origin escalation — the de facto standard, now Snyk-associated), **Cisco's mcp-scanner** (YARA + LLM-judge engines), **mcp-scanner** (an academic comprehensive tool), and **agent-audit** (config lint, OWASP MCP Top 10 mapping). Security alone is crowded.

**Every one of those tools answers "is this server *malicious/vulnerable*?"** The *quality* question — "is this server *any good*?" — is no longer untouched either: as of mid-2026 there are **point tools** for it. **mcp-xray** scores token-tax + tool-confusion into a single 0–100 grade (offline/live), and **Cisco's mcp-scanner** added a readiness analyzer (timeouts/retries/error-handling heuristics). Credit where due — they prove the demand.

**But those are graded X-rays you run by hand. There is still no `lighthouse`/`pytest` for MCP** — no CI-native *suite* that unifies the quality dimensions (contract, legibility, cost, performance, light security) into one graded gate, catches *quality regressions across commits*, prints a badge, and hands off to a full behavioral simulation. mcp-xray tells you your score; mcp-probe is the thing in `.github/workflows` that *blocks the merge* when the score regresses. That's the white space — a **suite and a gate**, not another point score. mcp-probe is a **quality-and-reliability suite** that treats security as *one* of several checks (deferring deep security to the specialists via integration, not reinvention) and unifies the quality point tools rather than competing with them.

This is a sharper, more defensible wedge than "another scanner" or "another score," and it's native to the author (professional MCP-server builder).

### 1.2 Problem

MCP servers are shipped with no equivalent of the web's quality tooling. Builders can't answer, before publishing: Are my tool descriptions clear enough that agents pick the right tool? How many tokens does my toolset burn just to exist in context? What's my p99 latency when 50 agents connect at once? Did my last commit silently break a tool's contract? Is there an obvious injection surface? Today these are found in production, by users, expensively.

### 1.3 Why now / why it wins

- MCP adoption is vertical (177k+ APIs; FastMCP 1M+ downloads/day) and its *quality* tooling is near-zero while its *security* tooling is nascent-but-crowded — quality is the open lane.
- "pytest/lighthouse for MCP" is an instantly graspable concept with a clear home (CI).
- Fastest of the big projects to ship → the wedge that establishes the author in the space before stampede lands.

### 1.4 Users & JTBD

1. **MCP server builders** — "Gate my releases on MCP quality like I gate on tests and lint." (Primary.)
2. **Teams adopting third-party MCP servers** — "Vet this server before I let my agents use it." (Overlaps security tools — where mcp-probe *integrates* mcp-scan rather than competing.)
3. **Registries / marketplaces** — "Score submitted servers automatically."

### 1.5 Goals & non-goals

**Goals (v0.1):** five check families — **Contract**, **Legibility**, **Cost**, **Performance**, **Security(-lite)** — run as CLI + CI, producing a graded report and a machine-readable JSON. Snapshot/regression mode. One-command run against any MCP server.

**Non-goals:** replacing dedicated security scanners (integrate mcp-scan/Cisco for deep security; own only quality + light security); being a runtime firewall (that's MCPGuard/Invariant Guardrails); scanning agents (that's stampede).

### 1.6 Success metrics

- North star: repos with `mcp-probe` in their CI workflow.
- Launch: 500+ stars in 30 days; adoption by ≥1 MCP registry for automated scoring within 6 months.
- The "MCP Quality Score" badge appears on server READMEs (the distribution flywheel).

---

## 2. ARCHITECTURE

### 2.1 The five check families

```
mcp-probe ──▶ connect (stdio / HTTP-SSE) ──▶ discover tools/resources/prompts
                                                │
   ┌───────────┬───────────────┬───────────────┼───────────────┬──────────────┐
   ▼           ▼               ▼               ▼               ▼              ▼
CONTRACT   LEGIBILITY        COST          PERFORMANCE      SECURITY-LITE   REPORT
schema     agent-           token-cost     concurrent-      injection       graded
validity,  comprehension    of toolset,    agent load,      surface,        report +
determinism scoring +       per-tool       p50/p95/p99,     secrets,        JSON +
of results  disambiguation  budget         SSE stability    integrates      badge
                                                            mcp-scan
```

**A. Contract checks** (LLM-free, fast, deterministic):
- JSON-RPC / MCP spec conformance; `initialize` handshake correctness.
- Tool schema validity; params match declared types; results conform to declared shapes.
- Determinism probe: call the same tool twice with same args, flag undeclared nondeterminism.
- **Snapshot/regression:** hash tool descriptions + schemas; diff against committed baseline → "your last commit changed 3 tool descriptions and broke 1 contract." (The pytest-snapshot pattern, applied to MCP.)

**B. Legibility checks** (the differentiator — nobody does this):
- **Agent-comprehension score:** run small LLM agents against the toolset with representative goals; measure whether they pick the *right* tool. Low scores flag ambiguous descriptions.
- **Disambiguation matrix:** detects tool pairs agents confuse (the `delete_record` vs `archive_record` problem), reported with the confusion rate.
- **Description quality lints:** missing examples, vague params, undocumented failure modes, over-long descriptions that waste context.
- Proposes concrete rewrites. (This is the "AEO — agent experience optimization" concept, folded in as a check family.)

**C. Cost checks:**
- Token cost of the *entire toolset* in context (what every agent pays just to see your tools).
- Per-tool token weight; flags bloated descriptions.
- Estimated $-per-typical-task across a few model price points.

**D. Performance checks** (fixes the "k6 doesn't speak MCP" gap):
- Concurrent-agent load with real MCP client semantics (persistent SSE connections, JSON-RPC), not naive HTTP.
- p50/p95/p99 latency; max stable concurrent connections; graceful-degradation check (does it slow or crash under load?).
- File-descriptor / connection-leak detection over sustained load.

**E. Security-lite** (own the easy 80%, integrate for the hard 20%):
- Built-in: obvious injection patterns in descriptions, secrets in config, dangerous capability flags — mapped to the **OWASP MCP Top 10**.
- **Integration:** optional `--deep-security` shells out to mcp-scan / Cisco mcp-scanner and folds their findings into the unified report. (Cooperate with the incumbents; don't duplicate their research.)

### 2.2 Outputs

- **Terminal report:** graded (A–F) per family + overall **MCP Quality Score**, oxblood-styled via the shared renderer.
- **JSON** for CI gating (`--fail-under B`).
- **Badge** (`mcp-probe: A`) for READMEs — the distribution mechanism.
- **CI mode:** `static` subcommand scans pre-generated MCP JSON offline (matching how Cisco's scanner supports air-gapped CI), so no live server needed in the pipeline.

### 2.3 Tech stack

Python 3.11+; official MCP SDK; provider-agnostic small-model layer for legibility checks (cheap models, Ollama-friendly, cached); async load engine reusing stampede's concurrency core (shared primitive); shared trace + report renderer. Zero-LLM fast path for Contract/Cost/Performance so CI runs are cheap and deterministic.

### 2.4 Risks & mitigations

- **Crowded security perception** → messaging leads with *quality* ("lighthouse for MCP"), names the security tools as friends it integrates, never competes on their turf.
- **Legibility scoring is LLM-dependent (cost/flakiness)** → small cached models, seedable, and it's opt-in; Contract/Cost/Performance work with zero LLM for the CI-critical path.
- **"Why not just mcp-scan?"** → mcp-scan tells you if a server is *dangerous*; mcp-probe tells you if yours is *good* — different job, and mcp-probe runs mcp-scan for you on request.

---

## 3. ROADMAP

- **v0.1:** all five families (security-lite built-in + optional deep integration); CLI + CI + JSON + badge; snapshot regression. Launch on HN.
- **v0.2:** legibility auto-fix (proposes and PRs description rewrites); registry scoring API; historical score tracking.
- **v0.3:** `stampede --from-probe` handoff (a probe target upgrades to a full behavioral simulation); marketplace partnerships.

## 4. LAUNCH

"Show HN: mcp-probe – lighthouse for MCP servers (lint, benchmark, load-test in CI)." Lead the demo with the legibility misuse-matrix and the token-cost number — the two things no other tool shows — not with security (crowded) or RPS (boring). Pair with an essay: "Your MCP server has a quality score, and it's probably a C." Offer to run mcp-probe publicly on 20 popular MCP servers and publish the leaderboard — instant attention, instant credibility, instant content.
