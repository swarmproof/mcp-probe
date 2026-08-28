# Your MCP server has a quality score. I graded the popular ones to show you what it looks like.

*Draft — Show HN / blog launch essay for mcp-quality. Lead with the leaderboard and the
token number; not security (crowded) and not RPS (boring).*

---

Every web app gets a Lighthouse score. Every repo gets a coverage badge. MCP servers —
the tools your agents actually depend on — get nothing. You ship a server, an agent picks
the wrong tool or burns 9,000 tokens just to *read* your tool list, and you find out in
production, from a user, expensively.

So I built **mcp-quality**: a CI quality suite that grades any MCP server across five
dimensions into a single letter grade, gates your merge, and prints a badge. Then I
pointed it at seven popular public servers. Here's what a quality score actually looks
like.

## The leaderboard

```
Server                         Grade  Score  Tools  Toolset tokens
server-memory                    A     100     9     1,112
mcp-server-time                  A     100     2       275
mcp-server-fetch                 A     100     1       290
mcp-server-git                   A     100    12     1,407
server-filesystem                A      99    14     1,901
server-everything                A      95    13     1,292
server-sequential-thinking       D      67     1       918   ← contract hard-gate
```

Good news first: the official reference servers are **well built**. Lean tool surfaces,
clear descriptions, no secrets, no injection surface. If you were expecting a wall of
F's, that's not the honest result and I'm not going to fake it.

But two things in that table should stop you.

## 1. The token tax is invisible until something prints it

`server-filesystem` costs **1,901 tokens** — every turn, for every agent, before it does
anything. That's the price of *existing* in the context window. It's fine for one lean
server. Now add five servers to your agent. Add a server that wasn't careful — I have a
40-tool test fixture that clocks **8,792 tokens**, ~$0.026 per task at Sonnet prices,
paid whether or not anything works. That's the single most actionable number in agent
engineering and almost nobody measures it.

mcp-quality measures it per-tool, using leave-one-out attribution, and tells you *which*
tool to put on a diet:

```
$2-bloat  search_all  ~1,900 tokens  → tighten the schema, split the tool, or lazy-load
```

## 2. The failure that's one tool-pair away from every server

`server-sequential-thinking` scored a D. Not because it's badly written — because its one
tool is *stateful*, and mcp-quality's determinism probe called it twice with identical
arguments and got two different answers. That's undeclared nondeterminism. For that server
it's arguably by-design (the fix is to *declare* the output volatile, not to change
behaviour) — but the check is exactly right, and it's the kind of thing that silently
breaks agent retries.

The scarier one doesn't need a stateful tool. Give me any two tools with similar
descriptions and I'll show you an agent picking the wrong one. Here's a real run — two
tools, both described *"Remove a record by id."*, judged by a small local model:

```
Disambiguation matrix  (row = correct tool · cell = % of times chosen)
                       delete   archive
  delete_record         100%       ·
  archive_record        100%       0%     ← chose delete every time archive was right
```

`archive_record` was the right call and the model chose `delete_record` **100% of the
time**. That's a data-loss bug living in your tool *descriptions*, invisible to every test
you have — and mcp-quality not only catches it, it proposes the rewrite that fixes it.

## "Isn't this just mcp-xray?"

No, and credit where it's due: [mcp-xray](https://ralforion.com/mcp-xray.html) pioneered
scoring token-tax and tool-confusion into a single grade, and I borrowed its
leave-one-out token method outright. But mcp-xray is an **X-ray you run by hand**.
mcp-quality is the thing in `.github/workflows` that **blocks the merge**. Four things the
point tools don't do:

1. **Load-test** with real MCP semantics (persistent connections, JSON-RPC — not naive HTTP).
2. **Contract-test** — invoke tools, check output conformance, catch nondeterminism.
3. **Snapshot** — diff against a committed baseline so a commit that silently breaks a
   tool fails the PR.
4. **Gate + badge** — a letter grade with a `--fail-under B` exit code and an
   `mcp-quality: A` badge for your README.

Security? It's *one* of the five checks — a floor, mapped to the OWASP MCP Top 10 — and
for the deep stuff it shells out to the specialists (mcp-scan, Cisco) rather than
reinventing them. This is a quality suite that treats security as a citizen, not the
whole town.

## Try it

```bash
pip install mcp-quality
mcp-quality run "python my_server.py" --fail-under B
```

The zero-LLM fast path (contract + cost) runs deterministically in CI with no model and
no key. Add `--legibility --model ollama:qwen2.5-3b` for the disambiguation matrix, or
`--all` for everything.

Run it on your server. Tell me what grade you got — and if it's a C, open the report;
the fix is usually three sentences in a tool description.

*mcp-quality is Apache-2.0 and part of the [Swarm Proof](https://github.com/swarmproof)
toolkit — trust infrastructure for the agent economy.*
