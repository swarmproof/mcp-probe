# mcp-probe

### The CI quality suite for MCP server builders

> Lint, contract-test, benchmark, and load-test your MCP server before you ship it. The `pytest` + `lighthouse` for the servers agents depend on.

<!-- TODO: demo GIF — the graded report + the legibility misuse-matrix -->
<p align="center"><em>▶ demo GIF coming — the graded MCP Quality Score report</em></p>

> **Status:** 🚧 v0.1 in progress — the wedge project (ships first of the tools).

---

## Why

Security scanners already answer *"is this server malicious?"* (mcp-scan, Cisco's mcp-scanner, and others own that lane). The *quality* question — *"is this server any good?"* — now has **point tools too**: [mcp-xray](https://medium.com/@irregularbi/your-mcp-server-has-a-token-tax-mcp-xray-tells-you-exactly-how-much-c93041c80af1) scores token tax and tool confusion into a single grade, and Cisco's mcp-scanner added readiness heuristics. But those are things you run *by hand*. There is still no `lighthouse`/`pytest` for MCP: **no CI-native suite that unifies the quality dimensions (contract, legibility, cost, performance, light security) into one graded gate, catches quality regressions across commits, prints a badge, and hands off to a full behavioral simulation.**

mcp-xray is an X-ray you run by hand; **mcp-probe is the `pytest` in `.github/workflows` that blocks the merge.** It is a **quality-and-reliability suite** — it treats security as *one* check, defers deep security to the specialists (integrate, don't reinvent), and unifies the quality point tools rather than competing with them (credit where due — they prove the demand).

## Quickstart

```bash
pip install mcp-probe
mcp-probe run "python my_server.py"        # graded A–F report + MCP Quality Score
mcp-probe run "python my_server.py" --json --fail-under B   # CI gate
mcp-probe static ./server.mcp.json         # offline / air-gapped CI
```

## The five check families

**Contract** (LLM-free): spec conformance, schema validity, determinism probe, snapshot regression. · **Legibility** (the differentiator): agent-comprehension score, the disambiguation matrix (`delete` vs `archive` confusion rate), description lints with proposed rewrites. · **Cost**: token weight of your whole toolset, per-tool bloat, $-per-task estimates. · **Performance**: concurrent-agent load with real MCP semantics (not naive HTTP), p50/p95/p99, connection-leak detection. · **Security-lite**: OWASP MCP Top 10 basics, with `--deep-security` shelling out to mcp-scan / Cisco.

Outputs a terminal report, JSON for CI, and an **`mcp-probe: A`** badge for your README. See [`SPEC.md`](./SPEC.md) and [`ROADMAP.md`](./ROADMAP.md).

## Part of the Swarm Proof toolkit

*Trust infrastructure for the agent economy — seven projects, one thesis.*

| Project | What it does |
|---------|--------------|
| [stampede](https://github.com/swarmproof/stampede) | Point a herd of realistic agents at your system before real ones arrive |
| [mockworld](https://github.com/swarmproof/mockworld) | A synthetic internet for agents — fake Stripe, Gmail, exchange, instantly |
| **mcp-probe** ← *you are here* | The CI quality suite for MCP servers — lint, contract-test, benchmark, load |
| [costbomb](https://github.com/swarmproof/costbomb) | Denial-of-wallet fuzzing — find the inputs that make your agent spend $500 |
| [exactly-once](https://github.com/swarmproof/exactly-once) | Idempotency middleware so agent side-effects fire once |
| [agent-postmortems](https://github.com/swarmproof/agent-postmortems) | A structured incident database + post-mortem standard for agent failures |
| [awesome-agent-reliability](https://github.com/swarmproof/awesome-agent-reliability) | The curated map of the field |

## License

[Apache-2.0](./LICENSE). Zero-LLM fast path for Contract/Cost/Performance; legibility checks are provider-agnostic and Ollama-friendly. Citable via [`CITATION.cff`](./CITATION.cff).
