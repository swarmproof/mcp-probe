# mcp-probe — RESEARCH

> Sharpened problem, thesis, and 2026 competitive landscape for **the CI quality suite for MCP servers**.
> Companion to `../SPEC.md`. This document does not restate the spec — it pressure-tests it against the live field and re-cuts the wedge where the field has moved.
>
> *Research window: web research conducted 2026-07-13. All external claims carry a source URL.*

---

## 0. TL;DR — what changed since the v1.0 spec, and the re-cut wedge

The v1.0 spec's central bet — *"security scanners answer 'is it malicious?'; nobody answers 'is it any good?' — quality is empty white space"* — was **correct in April 2026 and is now partially wrong**. Between the spec and today, two point tools moved into the quality lane:

1. **mcp-xray** (June 2026) ships exactly the two headline differentiators the spec claimed nobody had: **token-tax measurement** and **tool-confusion / behavioral correctness**, distilled to a **single 0–100 graded score**, with offline / API-backed / live modes. ([source](https://medium.com/@irregularbi/your-mcp-server-has-a-token-tax-mcp-xray-tells-you-exactly-how-much-c93041c80af1))
2. **Cisco mcp-scanner** added **Readiness Scanning** — 20 zero-dependency heuristic rules for production-readiness (timeouts, retries, error handling), no API keys. ([source](https://cisco-ai-defense.github.io/docs/mcp-scanner)) That is a *reliability/quality* check bolted onto a *security* tool.

**This does not kill the thesis — it sharpens it.** The correct 2026 framing is not "quality is empty" but:

> **The quality *dimensions* now have point tools; there is no CI-native *suite* that unifies them, gates on them, tracks regressions, and hands off to a full behavioral simulation.** mcp-xray is a graded X-ray you run by hand; Cisco readiness is a security add-on. Neither is `pytest` — neither is the thing you put in `.github/workflows/` that blocks a merge, snapshots your tool schemas, load-tests under 50 concurrent agents, and prints a badge. **mcp-probe is the suite and the gate, not another point score.**

The three genuinely-unserved lanes that make the wedge defensible:

| Lane | Who serves it today | mcp-probe's claim |
|---|---|---|
| **Performance / concurrent-agent load with real MCP semantics** | **Nobody.** k6 doesn't speak MCP; mcp-xray explicitly excludes load/perf; Cisco is static-only. | Own it outright. This is the clearest white space. |
| **Contract + snapshot regression in CI** | **Nobody.** No pytest-snapshot for tool schemas. | Own it outright. |
| **CI gate + badge + unified score across all five families** | **Nobody.** mcp-xray = manual score, no CI/badge/gate; Cisco = security CLI. | Own it — this is the "suite" wedge. |
| Token cost / legibility | **mcp-xray** (point tool) | Match on capability, win on *integration into the gate* + auto-fix + regression. Cite mcp-xray as prior art, differentiate on suite. |
| Deep security | mcp-scan, Cisco, agent-audit (crowded) | **Never compete** — integrate via `--deep-security`. |

---

## 1. Problem (sharpened)

### 1.1 The original problem statement holds

MCP servers ship with no equivalent of the web's quality tooling. Builders cannot answer, *before publishing*: are my tool descriptions legible enough that an agent picks the right tool; how many tokens does my toolset burn just to exist in context; what is p99 latency when 50 agents connect at once; did my last commit silently break a tool's contract; is there an obvious injection surface. Today these are found in production, by users, expensively.

### 1.2 What the 2026 data now proves (this problem is real and quantified)

The field has produced hard numbers that make the problem undeniable — use these in the launch essay:

- **Context tax is brutal and measured.** Seven MCP servers consume **67,300 tokens (33.7% of a 200k window)** before a user types anything; a typical Claude Code session with 5–10 MCPs burns **50,000–67,000 tokens** at rest. GitHub's server costs ~**55,000 tokens** (17,600 per-request by another measure) vs PostgreSQL's **35 tokens** — a ~1,500× spread that nobody is gating on. ([getunblocked autopsy](https://getunblocked.com/blog/mcp-token-budget-autopsy/), [dev.to 55k measurement](https://dev.to/kenimo49/your-mcp-server-eats-55000-tokens-before-your-agent-says-a-word-i-measured-the-real-cost-19l8), [AgentMarketCap context bloat](https://agentmarketcap.ai/blog/2026/04/08/mcp-context-bloat-enterprise-scale-tool-definitions-agent-context-budget))
- **Tool confusion is measurable and severe.** Frontier LLMs score **below 60% success** on LiveMCP-101's multi-tool queries; documented failure modes are *tool selection under noisy environments*, *dependency-chain compliance*, and *long-horizon planning* — i.e. exactly the legibility failures mcp-probe scores. ([LiveMCP-101, arXiv 2508.15760](https://arxiv.org/abs/2508.15760); [LiveMCPBench, arXiv 2508.01780](https://arxiv.org/abs/2508.01780) — 70 servers, 527 tools)
- **Registries do not curate quality.** The official registry "is not designed for end-user browsing and has no built-in curation, ratings, or governance"; many registries "make no attempt to evaluate quality… no ratings, reviews, or usage statistics." ([TrueFoundry](https://www.truefoundry.com/blog/best-mcp-registries), [official registry](https://registry.modelcontextprotocol.io/)) → the registry-scoring-API opportunity is real and open.
- **Security scanners are noisy** — an April 2026 audit of 33 servers / 433 tools found the YARA engine's **false-positive rate ~78%** (6 of 27 flags genuine). ([appsecsanta audit](https://appsecsanta.com/research/mcp-server-security-audit-2026)) → reinforces "defer deep security to specialists, don't reinvent, and add signal not noise."

### 1.3 Re-framed problem (one sentence)

> There is no tool you can drop into CI that answers, on every commit, *"is my MCP server good — legible, cheap, correct, fast, and not obviously unsafe — and did this commit make it worse?"* — and blocks the merge if the answer regresses.

The operative words the field's point tools miss are **CI**, **every commit**, **all five together**, **regression**, and **gate**.

---

## 2. 2026 competitive landscape

Two crisply-separated lanes. The SECURITY lane is crowded; the QUALITY lane is *forming but unconsolidated* — point tools exist, a suite does not.

### 2.1 SECURITY lane — crowded, do NOT compete (integrate)

| Tool | What it does | Engine / method | Relationship to mcp-probe |
|---|---|---|---|
| **mcp-scan** (Invariant Labs → Snyk-associated) | Config-level: tool poisoning, rug pulls, cross-origin escalation. De-facto standard. | Static config analysis + guardrails | **Integrate** via `--deep-security`. Cite as the security standard. ([Snyk/Invariant](https://invariantlabs.ai/)) |
| **Cisco mcp-scanner** | Malicious-code + threat scan; **3 engines** (YARA, LLM-as-judge, Cisco AI Defense); **Readiness Scanner** (20 heuristics: timeouts/retries/error handling); Vulnerable-Packages analyzer (pip-audit → CVE/PYSEC/GHSA); CLI **or REST API**; air-gapped static mode. | Multi-engine + heuristic static | **Integrate** for deep security. **Overlaps** on readiness → differentiate (see §4). ([GitHub](https://github.com/cisco-ai-defense/mcp-scanner), [docs](https://cisco-ai-defense.github.io/docs/mcp-scanner), [Cisco blog](https://blogs.cisco.com/ai/ciscos-mcp-scanner-introduces-behavioral-code-threat-analysis)) |
| **agent-audit** | Config lint + **OWASP MCP Top 10 mapping**. | Static lint | Adopt its OWASP mapping vocabulary in Security-lite; integrate if API stabilizes. |
| **mcp-scanner (academic)** | Comprehensive research scanner. | Mixed | Cite as prior art. |
| **Apigene / MCP-Marketplace scanners** | Registry-side scanning against OWASP MCP; surface security metadata per listing; "scanned 10,000+ servers." | Hosted scan | Distribution partners, not competitors — they scan *security*; offer them a *quality* score to surface. ([Apigene](https://apigene.ai/blog/mcp-marketplace), [MCP-Marketplace](https://mcp-marketplace.io/blog/how-safe-are-mcp-servers)) |

**Governing rule:** mcp-probe leads with *quality*, names every one of these as a friend, and shells out to them for the hard 20% of security. It never markets itself as a scanner.

### 2.2 QUALITY lane — forming, unconsolidated (this is the wedge)

| Tool | What it covers | Critical gaps (mcp-probe's opening) |
|---|---|---|
| **mcp-xray** ⭐ *the closest competitor* | Token tax (real Anthropic `count_tokens`), tool-confusion via golden-query behavioral probes, surface-bloat/merge candidates, schema hygiene, distraction metrics → **single 0–100 score**; offline/API/live modes; phase-swap aware; **prevents side effects during audit**. | **No load/perf. No contract testing. No security. No snapshot/regression. No CI/CD integration. No badge.** It is a *manual graded X-ray*, not a *gate*. ([source](https://medium.com/@irregularbi/your-mcp-server-has-a-token-tax-mcp-xray-tells-you-exactly-how-much-c93041c80af1)) |
| **Cisco Readiness Scanner** | 20 heuristic production-readiness rules (timeouts/retries/error handling), zero-dep static. | Static only; security-tool ergonomics; no legibility, no cost, no load, no regression, no unified quality score. |
| **MCP token-optimization tooling** (Tool Search, Code Mode, lazy loading) | *Fixes* bloat at runtime (85–96% token reduction via lazy schema loading / `execute_code`). | These are **runtime mitigations**, not pre-ship measurement/gates. mcp-probe *measures and gates*; it can *recommend* Tool Search / Code Mode as fixes. ([MCP.Directory](https://mcp.directory/blog/mcp-context-bloat-fix-2026-tool-search-code-mode-progressive-disclosure), [StackOne](https://www.stackone.com/blog/mcp-token-optimization/)) |
| **LiveMCP-101 / LiveMCPBench / MCP-Bench** (academic) | Benchmark *agents* over MCP tools; rigorous methodology for tool-selection scoring. | They benchmark the **agent**, not **your server**; not a dev tool, no CI, no per-server report. **Borrow their methodology** to make legibility scoring credible/citable. ([2508.15760](https://arxiv.org/abs/2508.15760), [2508.20453](https://arxiv.org/pdf/2508.20453)) |
| **AEO / "agent experience optimization" discourse** | Emerging vocabulary: discoverability, parsability, token efficiency, capability signaling; "CLEAR framework." | Discourse, not tooling. mcp-probe **operationalizes AEO** for MCP as the Legibility engine. ([addyosmani](https://addyosmani.com/blog/agentic-engine-optimization/), [Dashform](https://getaiform.com/blog/aeo-agent-experience-optimization-seo-successor-marketer-guide-2026)) |

### 2.3 Adjacent — agent-side testing (different target, do not confuse)

- **stampede** (sibling) — dynamic swarm simulator; mcp-probe is its static/CI little sibling (§6).
- **agentevals, LangWatch, IntellAgent** — evaluate the *agent*, not the server. Integrate as export targets, don't compete.

### 2.4 The one-slide competitive map

```
              tests the AGENT                     tests the SERVER
        ┌──────────────────────────┬───────────────────────────────────────┐
        │ agentevals, LangWatch,   │  SECURITY            QUALITY           │
 STATIC │ IntellAgent              │  mcp-scan            mcp-xray (token+   │
        │ LiveMCP-101 (benchmark)  │  Cisco mcp-scanner    confusion, score) │
        │                          │  agent-audit         Cisco readiness    │
        │                          │  (CROWDED)           (POINT TOOLS,      │
        │                          │                       NO SUITE) ◀────┐  │
        ├──────────────────────────┼──────────────────────────────────┼───┤
        │                          │  ── mcp-probe ──  the CI suite +   │   │
DYNAMIC │  stampede (swarm sim)    │  gate that UNIFIES quality + light  ───┘
        │                          │  security, adds LOAD + CONTRACT +   │
        │                          │  SNAPSHOT (nobody), and hands off   │
        │                          │  to stampede for full simulation    │
        └──────────────────────────┴───────────────────────────────────────┘
                                        ▲ white space mcp-probe owns:
                                          load/perf · contract+snapshot · the gate
```

---

## 3. Prior art (name it, borrow it, differentiate)

| Origin domain | Prior art | What mcp-probe borrows | What it changes |
|---|---|---|---|
| Web quality | **Lighthouse** | Multi-category graded report; a single memorable score; a badge culture. | Applies it to MCP; runs in CI as a gate, not just a Chrome panel. |
| Testing | **pytest / pytest-snapshot** | The snapshot-regression pattern; `--fail-under` gate ergonomics; plugin extensibility. | Snapshots *tool schemas + descriptions*, not text fixtures; diffs contracts. |
| Load | **k6 / Locust** | Concurrency curves, p50/p95/p99, ramp/hold/spike. | Speaks **MCP** (JSON-RPC, persistent SSE/Streamable-HTTP, `initialize`/`server/discover`), which k6 cannot. |
| Coverage/quality gates | **codecov / SonarQube** | Historical trend tracking; PR comment bots; the badge-in-README flywheel. | Tracks an *MCP Quality Score* over time; comments the score delta on PRs. |
| MCP quality (direct) | **mcp-xray** | Token-tax via real token counting; golden-query confusion probes; offline-dump mode. | Folds these into a 5-family **suite** with CI gate + regression + badge + load; adds auto-fix and the stampede handoff. |
| MCP security | **mcp-scan, Cisco, agent-audit** | OWASP MCP Top 10 mapping; air-gapped static mode. | Consumes them via `--deep-security`; never reimplements their research. |
| Agent benchmarking | **LiveMCP-101 / LiveMCPBench** | Methodology for scoring tool selection under noise; determinism/robustness concerns. | Turns a research benchmark into a per-server dev-time score with seeded, cached small models. |

---

## 4. Differentiation — the defensible moat, restated for the post-mcp-xray world

1. **Suite, not a score.** Five check families under one CI-native command with one `--fail-under` gate. mcp-xray gives a number; mcp-probe gives a *build status*. The analogy is **pytest** (a runner + a gate + an ecosystem), not a single linter.
2. **Two families literally nobody else has:**
   - **Performance** — concurrent-agent load with *real MCP semantics* (the acknowledged "k6 doesn't speak MCP" gap; even the stampede spec cites teams hand-rolling client loops). mcp-xray *explicitly excludes* this.
   - **Contract + snapshot regression** — spec conformance, schema validity, determinism probe, and a committed baseline so "this commit changed 3 tool descriptions and broke 1 contract" shows up in the PR. Nobody does snapshot-diffing of MCP contracts.
3. **The gate + the badge + the trend.** `--fail-under B`, a README badge (`mcp-probe: A`), and historical score tracking (v0.2). This is the distribution flywheel; a manual X-ray has none of it.
4. **Cooperation as a feature.** `--deep-security` runs mcp-scan / Cisco and *folds their findings into one report* — mcp-probe is the aggregator/orchestrator of the ecosystem, positioned above the point tools rather than beside them. It can equally wrap mcp-xray's token engine if that proves the best implementation (buy-vs-build in ARCHITECTURE).
5. **The upgrade path nobody can copy without the portfolio.** `stampede --from-probe` promotes a static probe target into a full behavioral swarm simulation. mcp-probe is the on-ramp to an entire trust-infrastructure toolkit (§6).
6. **Native author credibility.** The author builds MCP servers professionally; the legibility rubric encodes real builder pain, not theory.

**Honest weakness to own:** on *token cost + tool confusion in isolation*, mcp-xray is a credible, shipping competitor and may be more polished at launch. mcp-probe must not out-argue it on those two axes alone — it must make them table-stakes inside a suite whose *gate, regression, load, and badge* mcp-xray structurally lacks. (Buy-vs-build: consider wrapping/citing mcp-xray rather than re-deriving token counting — see ARCHITECTURE ADR-007.)

---

## 5. Users & jobs-to-be-done (expanded)

| # | Persona | Job-to-be-done | Trigger | Primary families | Success signal |
|---|---|---|---|---|---|
| **P1** | **MCP server builder** (primary) | "Gate my releases on MCP quality like I gate on tests and lint." | Pre-commit / PR / release | All five; Contract+Cost+Perf on the zero-LLM fast path | mcp-probe in `.github/workflows/`; badge in README |
| **P2** | **Team adopting a 3rd-party MCP server** | "Vet this server before I let my agents touch it." | Procurement / dependency add | Security-lite + `--deep-security`, Cost, Legibility | A go/no-go report; `--fail-under` in a vetting script |
| **P3** | **Registry / marketplace operator** | "Score every submitted server automatically, at scale, offline." | Server submission / re-index | `static` mode; Cost + Contract + Security-lite (deterministic) | Scoring API adopted; quality score shown per listing |
| **P4** ⊕ | **Platform / DevRel team** publishing many first-party servers | "One dashboard of quality scores across all our servers; alert on regressions." | Nightly / monorepo CI | All five + historical tracking | Score-trend dashboard; regression alerts |
| **P5** ⊕ | **AI reliability researcher** | "A reproducible, citable harness for MCP legibility/cost measurement." | Paper / study | Legibility (seeded), Cost | Cited via `CITATION.cff`; deterministic reruns |
| **P6** ⊕ | **Framework maintainer** (FastMCP, SDK authors) | "Ship an official mcp-probe check so our users get a score by default." | Framework release | All five | Official adapter / template shipped |

---

## 6. Ecosystem context — the Swarm Proof toolkit (fit + handoffs)

mcp-probe is **#3, the wedge** — smallest real tool, hottest ecosystem, ships **first** of the code tools (after the two presence repos). It is the **static/CI little sibling of stampede**.

**Shared primitives reused (vendor-first per portfolio decision, extract at stampede v0.2):**

| Primitive | Home (first build) | mcp-probe usage |
|---|---|---|
| **concurrency-core** (asyncio swarm scheduler) | stampede (Orchestrator) | Powers the Performance engine's concurrent-agent load with ramp/hold/spike curves. |
| **report-renderer** (HTML + terminal, oxblood-styled) | stampede (Observer) | Renders the graded MCP Quality Score report (terminal + HTML). |
| **trace-format** (OTel-compatible agent-trace schema) | stampede (Observer) | Legibility & Performance engines emit traces; enables the handoff below. |
| **persona-pack** (YAML agent temperaments) | stampede (Population Factory) | Legibility probes reuse a *minimal* persona (`naive`) for comprehension scoring; full packs are stampede's job. |

**The `stampede --from-probe` handoff (the flagship link).** stampede's `MCPTarget` adapter interface is `discover() -> ToolSet`, `invoke(tool, args, agent_ctx) -> Result`, `reset()`, driven by a committed `stampede.yaml`. mcp-probe already performs connect + discover and knows the transport/command. So a probe run can **emit a `stampede.yaml` seed + discovered ToolSet + trace baseline**, and `stampede --from-probe ./mcp-probe-report.json` boots a full behavioral simulation of the exact server mcp-probe just graded — "your server scored a B; now watch 200 agents actually use it." Contract in ARCHITECTURE §9.

**Cross-tool synergy:** mcp-probe's Cost engine and costbomb's denial-of-wallet fuzzing share the token-accounting substrate; a probe Cost finding ("this tool's output is unbounded") is a costbomb seed. mcp-probe emits trace-format that agent-postmortems can reference.

---

## 7. Gap analysis

### 7.1 Field gaps (product opportunities)

| Gap | Evidence | mcp-probe response | Family |
|---|---|---|---|
| No MCP-aware load tester | k6 doesn't speak MCP; teams hand-roll loops (stampede spec §1.1) | Performance engine on concurrency-core | Performance |
| No contract snapshot/regression | No pytest-snapshot for MCP contracts anywhere | Snapshot baseline + diff | Contract |
| No unified CI gate / badge | mcp-xray = manual; Cisco = security CLI | `--fail-under`, badge, PR comment | All |
| Registries don't score quality | official registry has no curation ([src](https://www.truefoundry.com/blog/best-mcp-registries)) | Registry scoring API (v0.2) | All (static) |
| Security scans are noisy | YARA 78% FP ([src](https://appsecsanta.com/research/mcp-server-security-audit-2026)) | Security-lite stays light + defers deep to specialists (add signal, not noise) | Security-lite |
| Token bloat unmeasured pre-ship | 67,300 tokens / 33.7% window ([src](https://getunblocked.com/blog/mcp-token-budget-autopsy/)) | Cost engine + gate; recommends Tool Search/Code Mode | Cost |
| No historical quality trend | codecov exists for coverage; nothing for MCP quality | Historical score tracking (v0.2) | All |

### 7.2 Spec gaps in the MCP protocol itself (must be handled by the connect/discover engine)

- ⊕ **The `initialize` handshake is being removed.** The **2026-07-28 spec RC (SEP-2575)** removes the `initialize`/`initialized` handshake; protocol version + client info + capabilities now ride in `_meta` on **every request**, and a new **`server/discover`** method fetches capabilities up front. The core is now **stateless**. **Backward-compat is preserved**: v2 servers still accept the legacy 2025-11-25 handshake. ([spec RC](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/), [analysis](https://fmind.medium.com/mcp-2026-07-28-stateless-core-enterprise-authorization-and-sdk-betas-2646a980d594))
  → **Implication:** the SPEC's "`initialize` handshake correctness" contract check must become **version-aware**: validate legacy handshake *and* the new `server/discover` + `_meta` path, and *flag servers that only speak one*. This is itself a valuable Contract check ("are you compatible with the July 2026 stateless core?").
- ⊕ **Transport churn: SSE is being phased out for Streamable HTTP.** Current SDKs still support SSE but maintainers expect to phase it out. → the connect engine must speak stdio + Streamable HTTP + (legacy) SSE, and Contract can flag SSE-only remotes as a forward-compat risk. ([spec RC](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/))
- ⊕ **Enterprise authorization** landed in the same RC → a future Security-lite check surface.

### 7.3 The awkward truth gap (address in launch messaging)

The v1.0 SPEC/README say "**None** answer 'is this server any good?'" — as of July 2026 that's overstated (mcp-xray, Cisco readiness exist). **Recommendation:** update public copy from *"nobody measures quality"* to *"quality has point tools; nobody has a **suite you gate CI on**."* Launching on the now-falsifiable "nobody" claim invites a well-actually from the mcp-xray author on HN. (This is a docs-only recommendation to the author; per constraints I am not editing README/SPEC.)

---

## 8. Open questions (for the author to decide)

1. **Buy vs build the token engine.** Wrap/cite **mcp-xray** (or its approach) for token-tax + confusion, or re-derive? Wrapping ships faster and turns a competitor into a dependency/ally; re-deriving keeps the suite self-contained. *Leaning: re-derive the measurement (it's not large — real `count_tokens` + leave-one-out), but publicly credit mcp-xray as prior art to avoid a positioning fight.* (ARCHITECTURE ADR-007.)
2. **Legibility determinism.** Small seeded models still drift across provider/version. Is a pinned local Ollama model (e.g. a small Qwen/Llama) the canonical scorer, with cloud models as opt-in? How is the golden-query set versioned and shipped?
3. **Score comparability.** If the rubric changes between versions, historical scores break. Version the rubric in the JSON (`rubric_version`) and the badge? (PRD requirement.)
4. **`server/discover` timing.** Do we require the new stateless path for an "A", or grade it as forward-compat bonus during the transition? Recommend: bonus now, required by the time the RC is final.
5. **Registry API trust.** If a registry scores servers via mcp-probe, how do we prevent gaming (e.g., a server that detects the probe and behaves differently)? Signed/randomized probe goals?
6. **Security-lite scope creep.** Cisco readiness overlaps our reliability checks. Do we cede readiness to `--deep-security` (Cisco) entirely, or keep a light built-in? Recommend: keep a light built-in (works offline, no Cisco dep) and let `--deep-security` supersede it when present.
7. **Is "MCP Quality Score" a defensible category name?** mcp-xray uses "0–100 score." We should own a *letter grade + named score* (A–F + "MCP Quality Score") to differentiate the vocabulary.

---

## 9. Sources

- mcp-xray (token tax / confusion / 0–100): https://medium.com/@irregularbi/your-mcp-server-has-a-token-tax-mcp-xray-tells-you-exactly-how-much-c93041c80af1
- Cisco mcp-scanner (repo): https://github.com/cisco-ai-defense/mcp-scanner · (docs): https://cisco-ai-defense.github.io/docs/mcp-scanner · (behavioral): https://blogs.cisco.com/ai/ciscos-mcp-scanner-introduces-behavioral-code-threat-analysis
- OWASP MCP Top 10: https://owasp.org/www-project-mcp-top-10/ · https://cycode.com/blog/owasp-mcp-top-10/ · https://www.practical-devsecops.com/owasp-mcp-top-10/ · cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html
- MCP security audit April 2026 (78% FP): https://appsecsanta.com/research/mcp-server-security-audit-2026
- Token cost autopsy / bloat: https://getunblocked.com/blog/mcp-token-budget-autopsy/ · https://dev.to/kenimo49/your-mcp-server-eats-55000-tokens-before-your-agent-says-a-word-i-measured-the-real-cost-19l8 · https://agentmarketcap.ai/blog/2026/04/08/mcp-context-bloat-enterprise-scale-tool-definitions-agent-context-budget
- Token optimization (Tool Search / Code Mode): https://mcp.directory/blog/mcp-context-bloat-fix-2026-tool-search-code-mode-progressive-disclosure · https://www.stackone.com/blog/mcp-token-optimization/
- MCP registries / curation gap: https://www.truefoundry.com/blog/best-mcp-registries · https://registry.modelcontextprotocol.io/ · https://apigene.ai/blog/mcp-marketplace · https://mcp-marketplace.io/blog/how-safe-are-mcp-servers
- MCP spec 2026-07-28 RC (stateless core, SEP-2575, server/discover): https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/ · https://fmind.medium.com/mcp-2026-07-28-stateless-core-enterprise-authorization-and-sdk-betas-2646a980d594
- Agent benchmarks (tool selection): https://arxiv.org/abs/2508.15760 (LiveMCP-101) · https://arxiv.org/abs/2508.01780 (LiveMCPBench) · https://arxiv.org/pdf/2508.20453 (MCP-Bench)
- AEO discourse: https://addyosmani.com/blog/agentic-engine-optimization/ · https://getaiform.com/blog/aeo-agent-experience-optimization-seo-successor-marketer-guide-2026
- BlueRock security stats (SSRF/auth): via https://www.truefoundry.com/blog/best-mcp-registries and https://mcp-marketplace.io/blog/how-safe-are-mcp-servers
