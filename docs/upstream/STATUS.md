# Upstream watch — awaiting maintainer replies

Tracking the `modelcontextprotocol/python-sdk` threads that unblock our deferred items.
Update "last checked" when you look; act per the playbook when a maintainer replies.

| Upstream thread | Unblocks | What we posted | State | Last checked |
|-----------------|----------|----------------|-------|--------------|
| [python-sdk #3715](https://github.com/modelcontextprotocol/python-sdk/issues/3715) (outbound request seam) | #76 `_meta` enforcement | `_meta` use-case comment + an offer of a small tested `send_request(stamp=False)` impl, asking if a PR is welcome | **awaiting reply** | 2026-10-24 |
| [python-sdk #2806](https://github.com/modelcontextprotocol/python-sdk/issues/2806) (SEP-2663 Tasks) | #75 live tasks drive | runnable reference task server + protocol-gating finding | **no maintainer reply; blocked on unmerged #3005** (see below) | 2026-11-26 |

## Playbook when they reply

**#3715 / the `_meta` seam:**
- "Open your own issue" → file a focused issue, get it assigned, then PR `meta-seam/meta-stamp-opt-out.patch`.
- "Fold into the middleware" → support in-thread; drop the standalone patch (their mutable-`meta` seam should allow *removal*).
- "PR welcome" → fork, apply the patch, open the PR with the prepared title/body, link the assigned issue.

**#2806 / tasks:** engage on the agreed shape; build the fixture + client `drive_task` once a task-emitting high-level server path is released. Grader/harness already shipped (#49).

State as of 2026-11-26:
- **Protocol gating — resolved on SDK `main`, unreleased.** [python-sdk #3776](https://github.com/modelcontextprotocol/python-sdk/pull/3776) (merged 2026-10-27) carries `capabilities.extensions` on legacy `initialize` handshakes, so the extension no longer requires the 2026-07-28 path. Latest release is v2.3.0 (2026-10-02), which predates it.
- **Task emission — still open.** The implementation is [python-sdk #3005](https://github.com/modelcontextprotocol/python-sdk/pull/3005) (SEP-2663 Tasks extension core): open, merge-conflicting, last updated 2026-07-31. A third-party rebase reports TS-client interop passing for augmented `tools/call`, `tasks/get`, `tasks/cancel` and legacy degradation.
- **Gap for #75:** #3005 defers background execution, so `working` → terminal and real cancellation are not exercised — the paths the T1/T3 lifecycle and T2 cancellation checks drive.
- **Unblock condition:** #3005 (or successor) merged and released, with background execution. SEP-3570 (moving Tasks into core) is under review and may change the API surface.

## Rules (don't break)
- **No unsolicited follow-ups / nudges** — their CONTRIBUTING discourages it, especially agent comments. Reply only when they do.
- **Never leak internal context** upstream (project name, roadmap, internal issue numbers, strategy).
- Engagement is **human-posted** (your account/voice), not agent-posted.
