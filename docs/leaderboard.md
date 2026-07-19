# MCP Quality Leaderboard

> Scored with **mcp-probe 0.1.0** (rubric `2026.07.1`). Fast path (Contract + Cost) + Security-lite. Keyless, offline-deterministic. Servers requiring API keys are listed but not scored.

| # | Server | Grade | Score | Tools | Toolset tokens | Top confusion | Notes |
|---|--------|-------|-------|-------|----------------|---------------|-------|
| 1 | `server-memory` | **A** | 100 | 9 | 1,112 | — |  |
| 2 | `mcp-server-time` | **A** | 100 | 2 | 275 | — |  |
| 3 | `mcp-server-fetch` | **A** | 100 | 1 | 290 | — |  |
| 4 | `mcp-server-git` | **A** | 100 | 12 | 1,407 | — |  |
| 5 | `server-filesystem` | **A** | 99 | 14 | 1,901 | — |  |
| 6 | `server-everything` | **A** | 95 | 13 | 1,292 | — |  |
| 7 | `server-sequential-thinking` | **D** | 67 | 1 | 918 | — | hard-gate: contract |

### Not scored (require credentials)
`server-github`, `server-slack`, `server-brave-search`, `server-google-maps`, `server-postgres`

### Reading the grades
- A **contract hard-gate** usually means the determinism probe (REQ-C5) called a tool twice with identical args and got different results. For a *stateful* tool (e.g. sequential-thinking accumulates state) that's by-design — the fix is to declare the output volatile, not to change behaviour. mcp-probe flags undeclared nondeterminism; whether it's a defect is the author's call.
- **Toolset tokens** is the context tax every agent pays each turn just to see the tools — the single most actionable number here.

_Reproduce: `python scripts/leaderboard.py`. Grades reflect the servers' published tool surface at scan time; a lower grade is an invitation to a PR, not a verdict._
