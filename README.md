<div align="center">

# mcp-quality

### The quality suite for MCP servers

**Lint, contract-test, benchmark, and load-test your MCP server before you ship it, from
your coding agent or your CI. One pass/fail verdict, with the fix for each blocker.**

[![CI](https://github.com/swarmproof/mcp-probe/actions/workflows/ci.yml/badge.svg)](https://github.com/swarmproof/mcp-probe/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mcp-quality.svg)](https://pypi.org/project/mcp-quality/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-quality.svg)](https://pypi.org/project/mcp-quality/)
[![License](https://img.shields.io/pypi/l/mcp-quality.svg)](./LICENSE)

</div>

---

Security scanners tell you whether an MCP server is *dangerous*. mcp-quality tells you
whether it is **good**. It connects to the server, exercises its tools, and verifies it across
six families: **Contract** (schemas, output shape, determinism, error recovery, spec
conformance), **Cost** (what the toolset costs on every turn), **Legibility** (can an agent
pick the right tool), **Performance** (under concurrent callers), **Security** (OWASP MCP
basics) and **Safety** (do the annotations tell the truth). The result is one **verdict**, pass
or fail, with the **fix for each blocker**. The letter grade is the badge, not the product.

## Tell your agent

> Check the MCP server in this repo with mcp-quality and fix what fails.

Your agent connects mcp-quality to the server, reads the verdict and the blockers, edits the
tool definitions, re-checks until it passes, and reports what changed. mcp-quality itself
never writes your files: it checks and proposes, your agent edits.

## Install, once

**Claude Code**, as a plugin (the MCP server plus the skill that runs the loop):

```
/plugin marketplace add swarmproof/mcp-probe
/plugin install mcp-quality@mcp-quality
```

**Cursor, Codex, Copilot, Gemini CLI, OpenCode** and the other agents the
[skills CLI](https://github.com/vercel-labs/skills) supports get the skill with:

```bash
npx skills add swarmproof/mcp-probe
```

then register the server in the agent's MCP config:

```json
{ "mcpServers": { "mcp-quality": { "command": "uvx", "args": ["mcp-quality", "mcp"] } } }
```

Needs [`uv`](https://docs.astral.sh/uv/) and Python 3.11+. No API key. The default checks
run without a model; the agent-comprehension probe behind `propose_fixes` uses a local one
(for example `ollama:qwen2.5-3b`).

## What it verifies

| Verified | Check | Family |
|---|---|---|
| tool annotations are true: a `delete_*` tool is not marked read-only | `SC2-annotation-untrue` | Safety |
| a successful result is a real result, not an error in disguise or an empty payload | `C13-silent-failure` | Contract |
| errors say what to change and whether to retry | `C11-error-unactionable` | Contract |
| an agent can tell neighbouring tools apart and picks the right one | the disambiguation matrix and `L2-confusion`, with a proposed rewrite | Legibility |
| the toolset stays below the tool-count selection cliff | `L8-tool-overload` | Legibility |
| the toolset's per-turn token cost and each tool's share of it | toolset token weight, per-tool share, $-per-task | Cost |
| the server behaves the same across MCP clients | `C14-client-compat` | Contract |
| path-like parameters are constrained | `S4-path-traversal-surface` | Security |
| the server conforms to the 2026-07-28 stateless revision | `C12-*` stateless conformance | Contract |
| latency, stable concurrency and connection hygiene under concurrent agents | p50/p95/p99, max stable concurrency, leak detection | Performance |

Per-family detail is under [The check families](#the-check-families).

## What the agent gets back

| Tool | Returns |
|------|---------|
| `grade_server` | the verdict and its blockers, each with the fix, then every finding and the per-family scores |
| `explain_findings` | only the findings, most severe first, each with its remediation |
| `propose_fixes` | rewritten descriptions for confusable or unclear tools (returned, never written) |

All three accept a live `target` (a stdio command or an http URL) or an offline `tools/list`
dump. They are read-only, and destructive tools are skipped unless allowed.

## Also a CI gate

The same engine runs from the command line. Its fast path is deterministic and needs no
model, key or network beyond your own server, so it can gate a merge.

```bash
pip install mcp-quality
mcp-quality run "python my_server.py" --fail-under B --no-regressions   # exit 1 on FAIL or regression
mcp-quality static ./server.mcp.json                                     # offline / air-gapped
mcp-quality badge "python my_server.py" --out badge.svg                   # README badge
```

```yaml
# .github/workflows/mcp-quality.yml
name: MCP Quality
on: [push, pull_request]
jobs:
  mcp-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install mcp-quality
      - run: mcp-quality run "python my_server.py" --fail-under B --no-regressions
```

Commit a baseline with `mcp-quality snapshot "…"` and `--no-regressions` fails the PR when
a commit silently breaks a tool or drops a score. Add `--legibility --model ollama:qwen2.5-3b`
for the disambiguation matrix, `--all` for every family, or `--deep-security` to fold in
mcp-scan / Cisco findings. `mcp-quality mcp` is the same server the plugin runs.

<details>
<summary><b>Table of contents</b></summary>

- [Tell your agent](#tell-your-agent)
- [Install, once](#install-once)
- [What it verifies](#what-it-verifies)
- [What the agent gets back](#what-the-agent-gets-back)
- [Also a CI gate](#also-a-ci-gate)
- [The check families](#the-check-families)
- [Where it fits](#where-it-fits)
- [Commands](#commands)
- [Leaderboard](#leaderboard)
- [Part of the Swarm Proof toolkit](#part-of-the-swarm-proof-toolkit)
- [Boundaries](#boundaries)
- [Contributing](#contributing)
- [Docs](#docs) · [License](#license)

</details>

## The check families

| Family | What it measures | Path |
|--------|------------------|------|
| **Contract** | JSON-RPC/handshake conformance, schema validity, output conformance, determinism & error-path/recovery probes, 2026-07-28 stateless-conformance, snapshot & version-drift regression | zero-LLM |
| **Cost** | token weight of your whole toolset, per-tool bloat (leave-one-out), runtime response bloat, Context Efficiency, $-per-task | zero-LLM |
| **Legibility** *(the differentiator)* | agent-comprehension score, the **disambiguation matrix**, selection accuracy + over-triggering, description lints — with proposed rewrites you can auto-PR | small model |
| **Performance** | concurrent-agent load with *real MCP semantics* (not naive HTTP), p50/p95/p99, max concurrency, connection-leak detection | live |
| **Security-lite** | injection / secrets / dangerous-capability lints mapped to the OWASP MCP Top 10; `--deep-security` integrates the specialists | zero-LLM + opt-in |
| **Safety-Contract** | are the tool annotations *true*? — a `delete_*` tool marked `readOnlyHint` (bypasses host confirmation), missing hints, retry-unsafe writes | zero-LLM |

### How the score works

A grading tool is only worth as much as the number it prints is trustworthy, so the rubric
is explicit and versioned — not a black box.

| Family | Contract | Cost | Legibility | Performance | Security-lite | Safety-Contract |
|--------|:--------:|:----:|:----------:|:-----------:|:-------------:|:---------------:|
| **Weight** | 20% | **30%** | 25% | 15% | 10% | 10% |

- **Weighted mean → letter grade.** Cost carries the most weight because it's paid on *every*
  turn. Weights are relative proportions; see [`docs/PRD.md` §7](./docs/PRD.md) for the rationale.
- **Only *measured* families count.** A family you didn't run (e.g. Legibility with no model) is
  dropped and the remaining weights are renormalized — never scored as `0` ([ADR-006](./docs/ARCHITECTURE.md)).
- **Hard-gate.** An **F in any family caps the overall grade at C** — no A-grade server with a
  broken contract or a lying annotation.
- **Deterministic & provenanced.** The fast path is **byte-identical** for identical input
  (golden-file tested). Legibility is deterministic only under a fixed `(model, seed, goal-set)`
  and is cached; performance is asserted as *invariants* (`p50 ≤ p95 ≤ p99`), never absolute ms.
  Every report and badge carries `rubric_version` (currently `2026.08.1`) so grades compare
  across releases.

### Reliability overlay — `--reliability K`

Accuracy asks *"can it work?"*; reliability asks *"will it work **every** time?"* — the
number a deploy gate actually cares about. `--reliability K` reruns the nondeterministic
families K times and reports **pass^k**: the projected probability all K runs pass. A
server that works 9 times in 10 is a 10% incident rate — pass^k over 5 runs is 59%, not an
A. Deterministic families (Contract, Cost, Safety) short-circuit to 100% with no reruns, so
the fast path stays free.

### Experimental — `--experimental` (spec-surface)

Beyond tools, MCP servers can talk back: `sampling/createMessage`, `elicitation/create`,
and advertised resources — the surfaces where a server can smuggle instructions into your
model, phish your user, or dangle links that don't resolve. `--experimental` adds a
**spec-surface** family that drives the read-only tools, captures those server-originated
messages, and grades them (sampling-injection, over-broad context, sensitive-form
elicitation, unresolvable resources). It's **opt-in and carries zero rubric weight** — it's
reported but never moves your grade while these spec surfaces are still stabilizing.

## Where it fits

mcp-quality doesn't compete with the security scanners or the point tools — it unifies the
*quality* question into a CI gate. Credit to [mcp-xray](https://ralforion.com/mcp-xray.html),
which pioneered token-tax + tool-confusion scoring (we borrow its leave-one-out method).

| The question you're asking | Reach for |
|----------------------------|-----------|
| "Is this server *dangerous*?" | mcp-scan, Cisco mcp-scanner |
| "What's its token tax / tool confusion?" *(run by hand)* | mcp-xray |
| **"Is this server *good* — gated in CI, every commit, with a badge?"** | **mcp-quality** |

## Commands

| Command | |
|---------|--|
| `mcp-quality run <cmd\|url>` | probe a live server (stdio / Streamable-HTTP / SSE) and grade it |
| `mcp-quality static <dump.json>` | score an offline `tools/list` dump (air-gapped CI) |
| `mcp-quality snapshot <target>` | write the regression baseline |
| `mcp-quality badge` | emit the grade badge (SVG + shields endpoint) |
| `mcp-quality fix --legibility` | apply proposed description rewrites (`--apply` / `--pr`) |
| `mcp-quality compare a.json b.json` | score-delta between two runs (sticky PR comment) |
| `mcp-quality serve` | hosted scoring API for registries (`[registry]` extra) |
| `mcp-quality mcp` | the MCP server the plugin runs (`grade_server` / `explain_findings` / `propose_fixes`) |

## Leaderboard

mcp-quality run against real public MCP servers ([full table](./docs/leaderboard.md)). The gate
is **dogfooded** — CI grades mcp-quality's own fixture servers every push: the good one must
pass `--fail-under B`, the bloated one must fail `--fail-under A`.

| Server | Grade | Toolset tokens |
|--------|:-----:|---------------:|
| `server-memory`, `mcp-server-time`, `mcp-server-fetch`, `mcp-server-git` | **A** | 275–1,407 |
| `server-filesystem` | **A** (99) | 1,901 |
| `server-everything` | **A** (95) | 1,292 |
| `server-sequential-thinking` | **D** (67) | 918 — contract hard-gate¹ |

<sub>¹ Its one tool is stateful, so the determinism probe (identical args → different results) flags *undeclared* nondeterminism. Fix = declare the output volatile. A lower grade is an invitation to a PR, not a verdict.</sub>

## Part of the Swarm Proof toolkit

*Trust infrastructure for the agent economy — seven projects, one thesis.*

| Project | What it does |
|---------|--------------|
| [stampede](https://github.com/swarmproof/stampede) | Point a herd of realistic agents at your system before real ones arrive |
| [mockworld](https://github.com/swarmproof/mockworld) | A synthetic internet for agents — fake Stripe, Gmail, exchange, instantly |
| **mcp-quality** ← *you are here* | The CI quality suite for MCP servers |
| [costbomb](https://github.com/swarmproof/costbomb) | Denial-of-wallet fuzzing — find the inputs that make your agent spend $500 |
| [exactly-once](https://github.com/swarmproof/exactly-once) | Idempotency middleware so agent side-effects fire once |
| [agent-postmortems](https://github.com/swarmproof/agent-postmortems) | A structured incident database + post-mortem standard for agent failures |
| [awesome-agent-reliability](https://github.com/swarmproof/awesome-agent-reliability) | The curated map of the field |

## Boundaries

Honest over impressive — what mcp-quality **doesn't** claim:

- **Legibility needs a model.** Without `--model`, Legibility runs offline description lints
  only and reports the comprehension probe as *not measured* (never a zero). Multi-model
  consensus (`--models`) is opt-in.
- **Some spec-surface checks degrade to "not measured"** until the ecosystem catches up: the
  live **tasks** lifecycle drive is inert until the MCP SDK's high-level server can emit
  tasks (the declared-capability check still runs), and stateless `_meta` enforcement isn't
  probed yet. Absent capabilities are *not measured*, never scored as `0` (ADR-006).
- **`--distributed` fans load across in-process workers**, not separate machines yet — a
  real cross-host coordinator is on the roadmap.
- **Security-lite is a floor, not a scanner.** It's one light check mapped to the OWASP MCP
  Top 10; defer deep analysis to the specialists via `--deep-security`.
- **Non-canonical scores are marked as such** — cloud/consensus model scores carry a flag;
  the canonical scorer is a pinned local model at temp 0.

## Contributing

Contributions are welcome — a low grade on a public server is an invitation to a PR, not a
verdict. Get set up:

```bash
git clone https://github.com/swarmproof/mcp-probe && cd mcp-probe
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -m "not live_llm" -q     # full suite
.venv/bin/ruff check src/ tests/          # lint
.venv/bin/mypy src/                        # types
```

A new check family is just a pure `CheckEngine` you register — see
[ARCHITECTURE.md](./docs/ARCHITECTURE.md) (ADR-001) and [CONTRIBUTING.md](./CONTRIBUTING.md)
for the full guide and the house conventions.

## Docs

[Demo](./docs/demo.md) · [Leaderboard](./docs/leaderboard.md) · [Architecture](./docs/ARCHITECTURE.md) ·
[Requirements (PRD)](./docs/PRD.md) · [Design decisions](./docs/DECISIONS.md) ·
[Roadmap](./ROADMAP.md) · [Changelog](./CHANGELOG.md) · [Contributing](./CONTRIBUTING.md) ·
[Security](./SECURITY.md) · [Code of Conduct](./CODE_OF_CONDUCT.md)

## License

[Apache-2.0](./LICENSE). Provider-agnostic and Ollama-friendly; the CI-critical path needs
no LLM. Citable via [`CITATION.cff`](./CITATION.cff).
