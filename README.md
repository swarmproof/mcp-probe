<div align="center">

# mcp-quality

### The CI quality suite for MCP servers

**Lint, contract-test, benchmark, and load-test your MCP server before you ship it —
the `pytest` + `lighthouse` for the tools your agents depend on.**

[![PyPI](https://img.shields.io/pypi/v/mcp-quality.svg)](https://pypi.org/project/mcp-quality/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-quality.svg)](https://pypi.org/project/mcp-quality/)
[![CI](https://github.com/swarmproof/mcp-probe/actions/workflows/ci.yml/badge.svg)](https://github.com/swarmproof/mcp-probe/actions/workflows/ci.yml)
[![License](https://img.shields.io/pypi/l/mcp-quality.svg)](./LICENSE)

</div>

---

Security scanners tell you if your MCP server is *dangerous*. **mcp-quality tells you if
it's *good* — and blocks the merge when it gets worse.** It grades any server across five
dimensions into a single **MCP Quality Score**, runs deterministically in CI with no LLM
and no key, and prints a badge.

```console
$ mcp-quality run "python my_server.py" --legibility

  MCP Quality Score  67   Grade D    ⚠ hard-gate: 'legibility' capped the grade at C

  Cost         A   100   122 toolset tokens; $0.0004/task
  Legibility   F     0   50% right-tool selection; archive_record⇄delete_record 100%
  Contract     A   100   2 tools conform

  Disambiguation matrix  (row = correct tool · cell = % of times chosen)
  ┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┓
  ┃ correct ↓ / chose → ┃ delete ┃ archiv ┃
  ┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━┩
  │ delete_record       │   100% │      · │
  │ archive_record      │   100% │     0% │   ← agents pick delete when archive was right
  └─────────────────────┴────────┴────────┘
  ↳ proposed rewrite: "Move a record to the archive (reversible); use delete_record to remove permanently."
```

Two tools described *"Remove a record by id."* — a data-loss bug living in your tool
*descriptions*, invisible to every test you have. mcp-quality catches it and writes the fix.

## Quickstart

```bash
pip install mcp-quality

mcp-quality run "python my_server.py"                       # graded A–F report
mcp-quality run "python my_server.py" --json --fail-under B # CI gate (exit 1 if < B)
mcp-quality static ./server.mcp.json                        # offline / air-gapped
```

The zero-LLM **fast path** (Contract + Cost) is deterministic and needs no model, key, or
network beyond your server. Add `--legibility --model ollama:qwen2.5-3b` for the
disambiguation matrix, `--all` for every family, or `--deep-security` to fold in
mcp-scan / Cisco findings.

## Use it in CI

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
a commit silently breaks a tool or drops a score. `mcp-quality badge` emits an
`mcp-quality: A` SVG + shields.io endpoint for your README.

## The check families

| Family | What it measures | Path |
|--------|------------------|------|
| **Contract** | JSON-RPC/handshake conformance, schema validity, output conformance, determinism & error-path/recovery probes, 2026-07-28 stateless-conformance, snapshot & version-drift regression | zero-LLM |
| **Cost** | token weight of your whole toolset, per-tool bloat (leave-one-out), runtime response bloat, Context Efficiency, $-per-task | zero-LLM |
| **Legibility** *(the differentiator)* | agent-comprehension score, the **disambiguation matrix**, selection accuracy + over-triggering, description lints — with proposed rewrites you can auto-PR | small model |
| **Performance** | concurrent-agent load with *real MCP semantics* (not naive HTTP), p50/p95/p99, max concurrency, connection-leak detection | live |
| **Security-lite** | injection / secrets / dangerous-capability lints mapped to the OWASP MCP Top 10; `--deep-security` integrates the specialists | zero-LLM + opt-in |
| **Safety-Contract** | are the tool annotations *true*? — a `delete_*` tool marked `readOnlyHint` (bypasses host confirmation), missing hints, retry-unsafe writes | zero-LLM |

Overall score = a weighted, **versioned rubric**; measured families are renormalized, and
an F in any family hard-gates the grade to C.

### Reliability overlay — `--reliability K`

Accuracy asks *"can it work?"*; reliability asks *"will it work **every** time?"* — the
number a deploy gate actually cares about. `--reliability K` reruns the nondeterministic
families K times and reports **pass^k**: the projected probability all K runs pass. A
server that works 9 times in 10 is a 10% incident rate — pass^k over 5 runs is 59%, not an
A. Deterministic families (Contract, Cost, Safety) short-circuit to 100% with no reruns, so
the fast path stays free.

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

## Leaderboard

mcp-quality run against real public MCP servers ([full table](./docs/leaderboard.md)):

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

## Docs

[Demo](./docs/demo.md) · [Leaderboard](./docs/leaderboard.md) · [Architecture](./docs/ARCHITECTURE.md) ·
[Requirements (PRD)](./docs/PRD.md) · [Design decisions](./docs/DECISIONS.md) ·
[Roadmap](./ROADMAP.md) · [Changelog](./CHANGELOG.md) · [Contributing](./CONTRIBUTING.md)

## License

[Apache-2.0](./LICENSE). Provider-agnostic and Ollama-friendly; the CI-critical path needs
no LLM. Citable via [`CITATION.cff`](./CITATION.cff).
