# Coverage gaps — closing the research-to-product holes

> Does mcp-quality actually cover every pain point and KPI our research surfaced? This ranks
> the gaps between *what the research says matters* and *what we check today*, with a family,
> effort, value, and an explicit in/out-of-scope call for each. **Goal: deliver the value we
> aimed for — a server certified top-quality on the real pains — not build a new product.**

Effort: **S** = hours–1 day · **M** = 2–4 days · **L** = 1+ week.

---

## Already covered (for the record)

Legibility (tool confusion), Cost (token tax), Performance (concurrent load), Contract
(schema/determinism/regression/stateless), Security-lite (injection/secrets/authz),
Safety-Contract (annotation truthfulness), regression gate, badge, registry API. These map
cleanly to the research's core pains — **this part of the value is delivered.**

## The gaps, ranked

| # | Gap | KPI / evidence | Family | Effort | Value | Scope |
|---|-----|----------------|--------|--------|-------|-------|
| 1 | **Tool-count overload cliff** | accuracy 95%→71% past ~40–50 tools; <10–15 ideal | Legibility (offline) + Cost metric | **S** | **High** | ✅ IN |
| 2 | **Silent-failure depth** | top-3 failure: "fails without reporting" | Contract | **S–M** | **High** | ✅ IN |
| 3 | **Path-traversal surface (light)** | 82% of audited servers vulnerable; #1 CVE class | Security-lite | **S** | Med | ✅ IN (light) |
| 4 | **Client-compat lints (static subset)** | "works in Claude Code, breaks in Cursor" | Contract | **M** | **High** | ✅ IN (light) |
| 5 | **Overall quality verdict rollup** | 86% never leave the laptop | cross-family | **M** | Med | ◻ IN (rollup only) |
| 6 | **Full multi-client harness** | real behavior diff across hosts | new | **L** | High | ⏳ DEFER (own milestone) |
| 7 | **`_meta` enforcement probe** | stateless spec RC | Contract | S | Low | 🚫 OUT (SDK-blocked) |
| 8 | **Multi-tool task success / long-horizon** | LiveMCP-101 <60% | — | L | High | 🚫 OUT (→ stampede handoff) |

---

## Detail & implementation sketch

### 1. Tool-count overload cliff — ✅ IN (do first)
The single most-cited structural failure, and we don't check it. We measure token *weight*
but never flag *count* against the selection cliff.
- **Add** `L8-tool-overload` (zero-LLM, runs in the free path): count tools; banded finding
  (>15 info, >30 low, >50 medium) with remediation = namespace / split / dynamic tool-loading
  (RAG-MCP / tool-search). Surface `tool_count` + `overload_band` in metrics.
- **Why Legibility:** it predicts *selection* failure and runs offline. Cost also shows the count.
- P1: remediation teaches the senior move (dynamic loading / sub-servers), not just "too many."

### 2. Silent-failure depth — ✅ IN
Today C11 catches "accepts invalid input." The research's "silent failure" is broader: the
tool *returns success while having done nothing / errored internally*.
- **Add** `C13-silent-failure`: on a valid invocation, flag an error-shaped payload returned
  with `is_error=false` (stack traces, "exception"/"failed" strings in a success result), or an
  empty result where the schema promises content. Heuristic, low-FP, live-only.

### 3. Path-traversal surface (light) — ✅ IN (light)
Path traversal is the #1 CVE class; we only have a generic dangerous-cap lint.
- **Add** `S4-path-traversal-surface` (Security-lite, static): flag tools with path-like params
  (`path`/`file`/`dir`/`filename`) and no evident constraint, naming the traversal risk, mapped
  to OWASP. **Light by design** — a floor; deep analysis stays deferred to `--deep-security`
  (keeps our "add signal not noise" promise given YARA's 78% FP).

### 4. Client-compat lints (static subset) — ✅ IN (light)
"Works in Claude Code, breaks in Cursor" is a top pain nobody tests. Full behavioral diffing
is heavy (#6), but the common footguns are statically detectable.
- **Add** `C14-client-compat`: lint for known cross-client hazards — unbounded output size,
  non-standard content types, error shapes clients disagree on, reliance on optional annotations.
  Ships value now; the full harness is a later milestone.

### 5. Overall quality verdict rollup — ◻ IN (rollup only)
"86% never ship." Much of a server's readiness is *already measured* (load, contract, safety);
the gap is we don't **summarize it as a go/no-go**.
- **Add** a `verdict` rollup in the report: a boolean + the blocking reasons, composed
  from existing hard-gates + a few light readiness signals (timeout/retry/error-handling hints).
- Deep readiness heuristics (cold start, serverless statefulness) stay **deferred to Cisco**
  via `--deep-security` — don't reinvent. This rollup is what P1 most needs: one honest
  pass/fail answer with the fix for each blocker.

### 6. Full multi-client harness — ⏳ DEFER
Spawning real Claude Code / Cursor client behaviors to diff them is a genuine, differentiated
feature but a **1+ week milestone** with host-specific surface. Do the static lints (#4) now;
schedule the harness as its own milestone if #4 shows pull.

### 7. `_meta` enforcement — 🚫 OUT (for now)
Blocked on SDK/spec maturity; already a documented boundary. Revisit when the SDK exposes it.

### 8. Multi-tool task success / long-horizon — 🚫 OUT (hand off)
LiveMCP-101-style "can an agent actually complete a multi-tool task" is **behavioral
simulation = stampede's job**. mcp-quality already emits the `--from-probe` handoff seed; this
is the boundary between the two tools by design, not a gap to fill here.

---

## Recommended sequence

- **Wave 1 (days) — close the quantified gaps:** #1 tool-overload, #2 silent-failure,
  #3 path-traversal-light. After this, *every quantified pain in the research is covered.*
- **Wave 2 (≈1 week) — differentiated coverage:** #4 client-compat lints, #5 quality verdict
  rollup.
- **Later / boundaries:** #6 (own milestone), #7 (SDK-blocked), #8 (stampede handoff).

## Definition of "we deliver the value"
After Wave 1+2, mcp-quality can honestly claim: *every pain point and KPI our research
surfaced is either measured, gated, or an explicitly documented boundary* — and the report
ends with a single **quality verdict + the fix for each blocker** (P1).
