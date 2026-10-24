# Upstream watch — awaiting maintainer replies

Tracking the `modelcontextprotocol/python-sdk` threads that unblock our deferred items.
Update "last checked" when you look; act per the playbook when a maintainer replies.

| Upstream thread | Unblocks | What we posted | State | Last checked |
|-----------------|----------|----------------|-------|--------------|
| [python-sdk #3715](https://github.com/modelcontextprotocol/python-sdk/issues/3715) (outbound request seam) | #76 `_meta` enforcement | `_meta` use-case comment + an offer of a small tested `send_request(stamp=False)` impl, asking if a PR is welcome | **awaiting reply** | 2026-10-24 |
| [python-sdk #2806](https://github.com/modelcontextprotocol/python-sdk/issues/2806) (SEP-2663 Tasks) | #75 live tasks drive | runnable reference task server + protocol-gating finding | **awaiting reply** | 2026-10-24 |

## Playbook when they reply

**#3715 / the `_meta` seam:**
- "Open your own issue" → file a focused issue, get it assigned, then PR `meta-seam/meta-stamp-opt-out.patch`.
- "Fold into the middleware" → support in-thread; drop the standalone patch (their mutable-`meta` seam should allow *removal*).
- "PR welcome" → fork, apply the patch, open the PR with the prepared title/body, link the assigned issue.

**#2806 / tasks:** engage on the agreed shape; build the fixture + client `drive_task` once a working high-level modern (2026-07-28) client+server path lands. Grader/harness already shipped (#49).

## Rules (don't break)
- **No unsolicited follow-ups / nudges** — their CONTRIBUTING discourages it, especially agent comments. Reply only when they do.
- **Never leak internal context** upstream (project name, roadmap, internal issue numbers, strategy).
- Engagement is **human-posted** (your account/voice), not agent-posted.
