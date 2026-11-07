---
name: mcp-quality
description: The quality suite for MCP servers. Verifies an MCP server's contract conformance, safety annotations, security surface, token cost, tool legibility and performance, and returns a pass/fail verdict with the fix for each blocker. Use when someone asks to check, grade, audit, verify, harden or review an MCP server, asks whether an MCP server is ready to ship or safe to expose, asks why agents pick the wrong tool or misuse it, or wants tool descriptions, schemas or annotations fixed. Drives the mcp-quality MCP server tools grade_server, explain_findings and propose_fixes.
---

# mcp-quality

mcp-quality connects to an MCP server, exercises its tools, and verifies the server across
six families: contract, cost, legibility, performance, security and safety. The result that
matters is the **verdict** (pass or fail) and the **fix for each blocker**. The letter grade
is a summary for a badge. Never stop at the grade,
and never report only a grade.

## The tools

All three are read-only. They connect, probe, and return results. They never edit files.
Applying a fix is your job, in the server's source.

| Tool | Returns | Inputs |
|------|---------|--------|
| `grade_server` | verdict, blockers with their fix, every finding, scores per family, the grade | `target` (a stdio launch command or an http(s) URL) **or** `tools` (a `tools/list` array, offline); optional `families`, `model` |
| `explain_findings` | only the findings, most severe first, each with its remediation | same |
| `propose_fixes` | rewritten tool descriptions for confusable or unclear tools (returned, not written) | same, plus `model` for the comprehension probe |

Default families: `contract`, `cost`, `legibility`, `security`, `safety`. `performance` is a
concurrent load test; include it only when the user asks about load, latency or concurrency.

## Procedure

1. **Locate the server.** Find how it starts (for example `python server.py`, `node dist/index.js`,
   `uvx some-server`) or the URL it listens on. If it cannot be launched here, use a
   `tools/list` dump as `tools`. Prefer a local or staging instance: the probe calls tools.
   Tools that look destructive are skipped by default, but do not point it at a production
   server with write tools unless the user confirms.
2. **Call `grade_server`** with `target` (or `tools`). Leave `families` unset unless the user
   named one.
3. **Read the verdict first.** If it passes, report that, plus any findings worth fixing.
   If it fails, list each blocker with its remediation. Each finding carries a code
   (for example `SC2-annotation-untrue`, `C13-silent-failure`, `L8-tool-overload`),
   the tool it concerns, and what to change.
4. **Fix it in the source.** Edit the tool definitions, schemas, annotations, descriptions or
   error handling exactly as the remediation states. Keep the change to what the finding names.
   Do not alter behaviour the user did not ask about.
5. **Re-check.** Call `grade_server` again. Repeat fix and re-check until the verdict passes
   and no high-severity finding remains. Stop after five rounds, or sooner if a finding cannot
   be fixed from this codebase, and say which and why.
6. **Descriptions.** When legibility findings name tools an agent confuses (the disambiguation
   matrix, `L2`/`L5` codes), call `propose_fixes` with a local model such as
   `ollama:qwen2.5-3b` and apply the rewrites that are accurate. Rewrite for the agent that
   reads them: what the tool does, when to use it, and when to use its neighbour instead.
7. **Report.** Verdict before and after, what you changed and in which files, and what
   remains open. Lead with the verdict and the fixes, not the grade.

## If the tools are missing

Tell the user to install mcp-quality for their agent:

- Claude Code: `/plugin marketplace add swarmproof/mcp-probe` then `/plugin install mcp-quality@mcp-quality`
- Any MCP client: add `{"command": "uvx", "args": ["mcp-quality", "mcp"]}` under `mcpServers`

Both need `uv` on the machine and Python 3.11 or newer. No API key is needed; the
comprehension probe behind `propose_fixes` needs a local model.
