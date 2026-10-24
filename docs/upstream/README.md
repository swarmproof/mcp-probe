# Upstream requests — MCP Python SDK

Two drafts to file against **[`modelcontextprotocol/python-sdk`](https://github.com/modelcontextprotocol/python-sdk)**.
They unblock `mcp-quality` issues #75 (live tasks probe) and #76 (`_meta` enforcement) on
*first-class* SDK APIs instead of low-level workarounds — and both benefit any tool that
needs to build or conformance-test MCP servers.

> **Status: DRAFTS.** These are written for a human maintainer to review and file — filing to
> an external org's repo is the author's call, not something this project posts automatically.
> Before filing, re-read the repo's `CONTRIBUTING.md` and confirm there's no existing issue.

Grounded in `mcp` 2.3.0 internals (verified 2026-10-24).

---

## Draft 1 — Tasks extension (SEP-2663): high-level server ergonomics + a test fixture

**Type:** feature / DX · **Relates to:** SEP-2663 (tasks extension, on the roadmap)

### Summary
The task **types** (`CreateTaskResult`, `GetTaskRequest`, `CancelTaskRequest`, `TaskStatus`)
and the client levers (`CallToolRequestParams.task`, generic `send_request`) exist, and the
server-side `Extension` tier (`server/extension.py`: `MethodBinding`, `intercept_tool_call`)
can serve `tasks/get`/`tasks/cancel`. But there is **no high-level way for a server author to
mark a tool as task-producing** — `MCPServer.tool()` has no task option, `ServerSession` has
no task methods, and the high-level server advertises no `tasks` capability. Building a
task-emitting server today means dropping to the Extension/low-level tier by hand.

### Verified wall (we tried it — `mcp` 2.3.0)
A reference task server built on `Extension` ([`reference/task_server.py`](reference/task_server.py))
constructs, starts, and advertises the `tasks` capability — but **can't be driven end-to-end**:
- Tasks live only on the **modern `2026-07-28`** protocol (`MODERN_PROTOCOL_VERSIONS = ('2026-07-28',)`).
- The `initialize` handshake caps at **`2025-11-25`** (`LATEST_HANDSHAKE_VERSION`); the modern
  path needs `server/discover`, which isn't reachable for a high-level `MCPServer` (`discover()`
  fails), so a task-augmented `tools/call` under the negotiated 2025-11-25 session **hangs**.

So the gap is two-fold: (a) no high-level task ergonomic, **and** (b) no working high-level
**modern (2026-07-28) client+server path** to exercise tasks at all.

### Why it matters
- **Server authors** can't adopt long-running tasks without the advanced Extension API *and* a
  modern-protocol connection path that works end-to-end.
- **Conformance/quality tooling** (e.g. mcp-quality) can't drive a task lifecycle (terminal
  states, cancellation, orphaning) against the reference SDK — the checks exist (#49) but have
  no reachable server.

### Proposal
1. A high-level ergonomic to declare a task-producing tool, e.g. `@server.tool(task=True)` (or
   a `tasks=` helper), wiring the Extension machinery under the hood and advertising the
   `tasks` capability.
2. A working high-level **modern (2026-07-28) client+server path** (or docs showing the
   supported way to establish a modern session) so task methods are reachable.
3. Ship a small **reference/test task server** that emits a task and serves `tasks/get`/
   `tasks/cancel` — [`reference/task_server.py`](reference/task_server.py) is a starting point
   (it builds; it just needs #2 to be drivable).

### Acceptance
- A high-level server can expose a tool whose call returns a `CreateTaskResult` and whose task
  is pollable/cancellable, with tests.

### Alternatives considered
- Using the `Extension` API directly — works but is advanced/experimental and undocumented for
  this use; not reasonable to ask every server author (or test harness) to re-derive.

---

## Draft 2 — Client: allow sending a request without the auto-stamped `_meta` (conformance hook)

**Type:** feature (testing/conformance)

### Summary
On the stateless path the client **always** stamps required `_meta` onto every request —
`client/session.py` does `params.setdefault("_meta", {})[PROTOCOL_VERSION_META_KEY] = version`
in the handshake stamp, run unconditionally inside `send_request`. There is no supported way to
send a request with `_meta` omitted, so **a conformance test cannot verify that a server
correctly rejects a request missing required `_meta`** (a requirement of the 2026-07-28
stateless revision) without bypassing the SDK via raw-stream surgery.

### Why it matters
- Conformance tooling needs to probe server-side `_meta` enforcement; today it can't, honestly.
- It's a small, opt-in, test-oriented seam — no change to default behavior.

### Proposal
Add an opt-in to skip or override the stamp, scoped to testing, e.g.:
- `session.send_request(request, result_type, stamp=False)`, or
- a session-level `conformance`/`raw` mode that forwards params verbatim.

### Acceptance
- A caller can send a request with `_meta` omitted and observe the server's response, enabling
  a `_meta`-enforcement conformance check. Default behavior unchanged.

### Alternatives considered
- Writing a hand-crafted JSON-RPC frame straight to the transport stream — fragile,
  transport-specific, and brittle across SDK versions.

---

## What we do once these land
- Draft 1 → unblocks **#75**: build the task-emitting fixture on the high-level API, implement
  client `drive_task` (task-augment `call_tool` + `tasks/get`/`tasks/cancel`), and the already-
  shipped #49 grader/harness activates live.
- Draft 2 → unblocks **#76**: set `meta_enforced` from a real probe; the `C12-meta-unenforced`
  grader code (shipped in #32) starts producing a real signal.
