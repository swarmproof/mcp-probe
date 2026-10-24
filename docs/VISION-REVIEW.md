# Vision review — has mcp-quality drifted?

> A candid re-read of the original vision against what shipped (`0.5.0`) and against what
> **agentic-era use (late 2026)** now expects. Written to align on the gap *before* choosing
> what to build next. This is an analysis, not a decision.

---

## TL;DR

- The **"CI quality suite → graded report"** shape is **not drift** — it is literally the frozen
  `SPEC.md` vision. We built to spec.
- Two things *are* wrong:
  1. **Framing drift (fixable now):** the value was consistently reduced to *"run a script →
     A–F."* The engine is deep (6 families, disambiguation matrix, auto-fix, reliability,
     consensus); the pitch made it sound like a linter.
  2. **The vision itself is dated (the real issue):** `SPEC.md` was written for *a human running
     a CLI in CI*. It predates the expectation that the **builder of an MCP server is now an
     agent**, and that the tool should be **agent-native, actionable, and loop-closing** — not a
     passive linter that emits a letter grade and waits for a person.
- The SPEC even *named* the right idea — **"AEO — Agent Experience Optimization"** (§2.1) — but we
  implemented it as a passive check family, not as an active optimization layer.

---

## 1. What the SPEC promised (frozen v1.0)

From `SPEC.md`:

- **Tagline:** "lint, contract-test, benchmark, and load-test your MCP server before you ship it.
  The `pytest` + `lighthouse` for the servers agents depend on." (§0)
- **Primary user:** MCP server **builders** — "gate my releases on MCP quality like I gate on
  tests and lint." (§1.4)
- **Outputs:** terminal A–F report, JSON for CI, README badge, offline `static` mode. (§2.2)
- **Richer-than-a-grade pieces that were in the vision:** agent-comprehension score, the
  **disambiguation matrix**, **proposed rewrites** — explicitly framed as **"AEO — agent
  experience optimization"** (§2.1) — plus the `stampede --from-probe` handoff (§3).
- **Interface assumption (implicit but total):** a **human** types a CLI command and reads the
  result. Every output in §2.2 is human-facing (terminal table, badge) or CI-facing (JSON exit
  code). There is **no** notion of an agent *calling* mcp-quality.

## 2. What we actually built (`0.5.0`)

Honest inventory — the engine is **not** basic:

- **6 scored families** (Contract, Cost, Legibility, Performance, Security-lite, Safety-Contract)
  + experimental spec-surface; one weighted **MCP Quality Score** with hard-gates.
- **Beyond the grade:** disambiguation matrix, auto-fix rewrites (`mcp-quality fix`), snapshot /
  capability-drift regression, pass^k reliability, multi-model consensus, distributed load,
  provenance-verifiable scores, a registry HTTP API (`serve`), OWASP authz lints,
  annotation-truthfulness (Safety-Contract), 2026-07-28 stateless conformance.
- **Interfaces:** CLI (`run`/`static`/`snapshot`/`badge`/`fix`/`compare`/`serve`), JSON report,
  SVG badge, a REST scoring API for registries.
- 268 tests, Python 3.11–3.13, MCP SDK v2, Apache-2.0, on PyPI.

**Verdict:** we delivered the SPEC — and then some. The depth is real. **What we did not do is
question whether the SPEC's *human-CLI-in-CI* interface is still the right primary shape.**

## 3. Where it matches, where it drifted

| Dimension | SPEC vision | Built | Assessment |
|-----------|-------------|-------|------------|
| Check depth | 5 families | 6 + experimental | ✅ exceeded |
| CI gate + badge | yes | yes | ✅ delivered |
| Actionable rewrites (AEO) | "propose rewrites" | `fix` subcommand | ⚠️ built as a *passive* CLI step, not an active loop |
| Primary interface | human CLI / CI | human CLI / CI | ❗ **matches spec — but the spec is dated** |
| Agent *consumes* the tool | (absent) | (absent) | ❗ **the gap** — never contemplated |
| Output value | A–F + findings | A–F + findings | ⚠️ grade over-indexed; remediation under-exposed |

## 4. The agentic-era gap (the core of the critique)

`SPEC.md` was written April–July 2026. Since then the ground shifted: **the entity building and
maintaining an MCP server is increasingly an agent** (Claude Code, Cursor, agent frameworks). The
vision has no answer for that reader.

```
   WHAT WE BUILT (human-CLI-in-CI)        WHAT AGENTIC USE EXPECTS (late 2026)
   ──────────────────────────────         ──────────────────────────────────
   human types `mcp-quality run …`   →     an agent calls mcp-quality AS A TOOL
   reads an oxblood terminal table   →     consumes structured, executable guidance
   gets a letter grade A–F           →     gets "edit param X desc → Y, because Z"
   fixes by hand, re-runs            →     grade → fix → re-grade, autonomously, in-loop
   "lint before you ship"            →     "continuously optimize the server for agents"
```

Four concrete things missing for agent-native use:

1. **No MCP interface.** mcp-quality is not itself exposed *as an MCP server*, so a coding agent
   can't call `grade_server` / `explain_findings` / `optimize_descriptions` as tools. This is the
   single biggest gap — it meets agents nowhere.
2. **Findings aren't agent-executable.** `L2-confusion` + prose remediation is written for a human
   to read, not for an agent to *apply* deterministically.
3. **No closed loop.** `run` and `fix` are separate human-invoked steps; there's no single
   "optimize until grade ≥ B, then report the delta" primitive an agent can drive.
4. **The framing is a scoreboard, not a coach.** "You got a C" serves a human dashboard; an agent
   wants the exact edits that make it an A, applied and verified.

> The SPEC named **Agent Experience Optimization** and then shipped a linter. The compelling 2026
> product is AEO *as a service an agent uses*, not a grade a human reads.

## 5. Why this matters now (competitive pressure)

The quality lane has filled in since our research (`RESEARCH.md`, July 2026):

- **mcp-xray** — token-tax + tool-confusion → 0–100 score (manual). Matches us on two axes.
- **MCP Eval Pro / mcp-bench-report** (new) — positions as the *"first comprehensive evaluation
  framework"* with visual reports. Collides with our "suite" claim.
- **MCP Inspector** (official) — now has a scriptable `--cli` mode → owns the low-end CI smoke check.
- **Benchmarks** (MCPBench, agent-eval, MCP-Atlas) — measure agent task-completion; non-gateable.

On "measure quality + emit a report," we are **no longer differentiated enough**. The defensible,
uncrowded ground is exactly what the gap above describes: **deterministic + behavioral-conformance
+ agent-native optimization loop.** Nobody is there yet.

## 6. Options to close the gap

**Option A — Reframe only (docs/narrative, ~days).** Keep the product; stop calling it a linter.
Lead with AEO, the matrix, auto-fix, the delta. Cheapest; fixes the *framing* drift but not the
*interface* gap. Risk: still "a CLI that emits a grade" when an agent looks at it.

**Option B — Agent-native layer on the existing engine (the recommended core, ~1 milestone).**
- Expose mcp-quality **as an MCP server** (`mcp-quality serve --mcp`): tools like `grade_server`,
  `explain_findings`, `propose_optimizations`, `apply_and_verify`.
- Make findings **agent-executable** (structured, with exact before/after edits).
- A **closed optimize loop**: `grade → remediate → re-grade → delta` as one callable action.
- Keep CLI/CI/badge as one surface, not the only one.
- Reframe narrative to **Agent Experience Optimization**.

**Option C — Re-platform as an optimization *service* (largest).** B, plus a hosted/continuous
mode: a server registers once and is continuously re-graded and auto-PR'd as the spec/ecosystem
evolves. Highest ceiling, highest cost; depends on adoption.

## 7. Recommendation

- **Do A immediately** (it's nearly free and stops the bleeding on framing).
- **Commit to B as the next milestone** — it's the smallest change that turns a *deep engine behind
  a human CLI* into an *agent-native optimization layer*, and it lands squarely on the one piece of
  uncrowded, defensible ground (deterministic + behavioral + agentic). The engine already exists;
  this is primarily a new **interface + loop**, not new checks.
- **Hold C** until B shows pull.

## 8. Open questions for the author

1. **Primary user going forward:** the human builder in CI, or the *agent* building the server? (B
   assumes "both, agent-first.")
2. **Is "Agent Experience Optimization" the category we want to own** (vs. "MCP quality suite")?
3. **MCP-server-of-itself**: is mcp-quality-as-an-MCP-server the right agent interface, or is a
   different SDK/handoff the better fit?
4. **Scope of the loop:** do we auto-apply fixes (agent-driven) or always propose-and-confirm?
5. **Does this change the Swarm Proof positioning** (probe → stampede handoff) at all?
