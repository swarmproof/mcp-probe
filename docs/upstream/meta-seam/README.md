# Upstream patch (prepared, NOT submitted) — `send_request(stamp=False)` seam

Internal tracking of a ready upstream contribution to **`modelcontextprotocol/python-sdk`**
that would unblock our `_meta`-enforcement check (#76). **Not submitted** — see the submission
rules below. The patch itself (`meta-stamp-opt-out.patch`) is fully generic: it carries no
reference to this project, its issues, or any internal context.

## What it does
Adds an opt-in `stamp: bool = True` to `ClientSession.send_request`. When `stamp=False`, the
client skips the automatic protocol stamp, so the request's params go out **verbatim** — no
injected `_meta`, no protocol-version header. Default behavior is unchanged.

Why it's needed: the client auto-stamps required `_meta` on every request
(`params.setdefault("_meta", {})[…] = protocol_version`, run unconditionally in `send_request`),
so there is no supported way to send a request that *omits* `_meta` — which a conformance test
needs, to verify a server correctly rejects a request missing required `_meta` (2026-07-28).

## Verification (against the real repo, `main`)
Built and checked in a clean clone of `modelcontextprotocol/python-sdk`:
- `uv run pytest` — the new `tests/client/test_send_request_stamp_opt_out.py` (2 tests) passes;
  the existing `test_send_request_mcp_name.py` stamp suite stays green.
- `uv run ruff check` — clean. `uv run ruff format --check` — clean. `uv run pyright` — 0 errors.

## The generic PR (ready to paste) — title + body
> **Title:** Client: opt-in to send a request without the auto-stamped `_meta` (`send_request(stamp=False)`)
>
> **Body:**
> On the modern path the client stamps required `_meta` (and the protocol-version header) onto
> every request inside `send_request`, with no way to opt out. That makes one thing impossible:
> sending a request that *omits* `_meta` — which is exactly what a conformance test needs in
> order to verify a server correctly **rejects** a request missing required `_meta` (a
> 2026-07-28 requirement).
>
> This adds an opt-in `stamp: bool = True` to `send_request`; `stamp=False` sends params
> verbatim (no `_meta`, no protocol-version header). Default behavior is unchanged. Minimal,
> self-contained, with tests mirroring `test_send_request_mcp_name.py`. Relates to the outbound
> request-seam discussion in #3715.

## Submission rules (IMPORTANT — do not skip)
Their `CONTRIBUTING.md`: **unsolicited PRs are auto-closed.** A PR is reviewed only if it links
an issue that a maintainer has **assigned to you**, or that carries the **`help wanted`** label.
They are explicitly wary of agent-generated PRs and ask that nobody post "assign me" comments
(especially from an agent).

Correct path, human-driven:
1. Engage on the relevant issue (#3715, outbound request seam) **as a human** — confirm the use
   case, briefly describe this approach, and say you'd like to implement it.
2. Wait for a maintainer to assign it (or for a `help wanted` label).
3. Only then: fork, apply `meta-stamp-opt-out.patch`, push to the fork, open the PR with the
   title/body above, linking the assigned issue.

Until step 2 happens, this stays here, ready.
