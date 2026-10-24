"""Reference task server for the upstream ask (SEP-2663) — NOT a working mcp-quality fixture.

Built on the SDK's `Extension` mechanism: a task-augmented `tools/call` (client sets
`params.task`) is intercepted → `CreateTaskResult`; `tasks/get` advances to terminal;
`tasks/cancel` → cancelled. It constructs, starts, and *advertises* the `tasks` capability.

**Where it walls (verified on `mcp` 2.3.0):** tasks live only on the **modern 2026-07-28**
protocol (`MODERN_PROTOCOL_VERSIONS = ('2026-07-28',)`), but the `initialize` handshake caps
at `2025-11-25` (`LATEST_HANDSHAKE_VERSION`). Reaching tasks needs the modern `server/discover`
client session — which isn't reachable for a high-level `MCPServer` here (`discover()` fails),
so a task-augmented call under the negotiated 2025-11-25 session hangs. That gap — *a working
high-level modern (2026-07-28) client+server path, plus task ergonomics* — is the upstream ask
(see ../README.md, Draft 1). Once it lands, this server drives the #49 grader live.
"""

from __future__ import annotations

import datetime as _dt
import secrets
from typing import Any

from mcp.server.extension import Extension, MethodBinding
from mcp.server.mcpserver import Context, MCPServer
from mcp.types import (
    CancelTaskRequestParams,
    CancelTaskResult,
    CreateTaskResult,
    GetTaskRequestParams,
    GetTaskResult,
    Task,
)


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


class TasksExtension(Extension):
    """Minimal in-memory tasks implementation over the Extension API."""

    identifier = "dev.swarmproof/tasks-fixture"

    def __init__(self) -> None:
        self._status: dict[str, str] = {}

    def methods(self) -> list[MethodBinding]:
        return [
            MethodBinding(method="tasks/get", params_type=GetTaskRequestParams, handler=self._get),
            MethodBinding(method="tasks/cancel", params_type=CancelTaskRequestParams, handler=self._cancel),
        ]

    def _fields(self, task_id: str, status: str) -> dict[str, Any]:
        now = _now()
        return {"task_id": task_id, "status": status, "created_at": now,
                "last_updated_at": now, "ttl": 60000}

    async def intercept_tool_call(self, params: Any, ctx: Any, call_next: Any) -> Any:
        if getattr(params, "task", None) is not None:  # task-augmented → emit a task
            task_id = secrets.token_hex(8)  # opaque handle (no T4-weak-handle noise)
            self._status[task_id] = "working"
            return CreateTaskResult(task=Task(**self._fields(task_id, "working")))
        return await call_next(ctx)

    async def _get(self, ctx: Any, params: GetTaskRequestParams) -> GetTaskResult:
        tid = params.task_id
        if self._status.get(tid) == "working":  # advance to a terminal state on first poll
            self._status[tid] = "completed"
        return GetTaskResult(**self._fields(tid, self._status.get(tid, "completed")))

    async def _cancel(self, ctx: Any, params: CancelTaskRequestParams) -> CancelTaskResult:
        tid = params.task_id
        self._status[tid] = "cancelled"
        return CancelTaskResult(**self._fields(tid, "cancelled"))


mcp = MCPServer("tasks-server", extensions=[TasksExtension()])


@mcp.tool(description="Run a job. Task-augment the call to run it as a long-running task.")
def slow_job(prompt: str, ctx: Context) -> str:  # inline when not task-augmented
    return f"done: {prompt}"


if __name__ == "__main__":
    mcp.run()
