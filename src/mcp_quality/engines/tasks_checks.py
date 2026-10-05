"""Tasks-lifecycle grading (#49) — pure, for the spec-surface family ``⊕ experimental``.

MCP's long-running **Tasks** let a server run work that outlives one request. A task that
never reaches a terminal state, ignores cancellation, or orphans a handle that keeps
emitting is a reliability hole an agent can't recover from. This module is pure: it grades
(a) the **declared** tasks capability (static — does a server that runs long ops even
support cancellation?) and (b) the **observed** lifecycle of a task driven through the
harness. The SDK access (creating/polling/cancelling a task) lives behind the client
façade; everything here is a pure function of the capability dict / observations, so it's
testable with no live task server (which the current SDK's high-level server can't be yet).
"""

from __future__ import annotations

import re
from typing import Any

from mcp_quality.connect.capture import TaskObservation
from mcp_quality.models import Finding, ServerSurface, Severity

# TaskStatus per the spec: working | input_required | completed | failed | cancelled.
TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})
# A task handle that's short or purely sequential is guessable/enumerable.
_WEAK_HANDLE = re.compile(r"^(?:\d+|task[-_]?\d+)$", re.I)


def tasks_capability(surface: ServerSurface) -> dict[str, Any] | None:
    """The declared ``tasks`` server capability, if any (else None → not measured)."""
    caps = surface.capabilities or {}
    tasks = caps.get("tasks")
    return tasks if isinstance(tasks, dict) else None


def grade_tasks_declaration(tasks: dict[str, Any]) -> list[Finding]:
    """Static: a server that can run requests as tasks but doesn't declare cancellation
    leaves an agent no way to stop long-running work it started."""
    findings: list[Finding] = []
    runs_tasks = bool(tasks.get("requests"))
    supports_cancel = bool(tasks.get("cancel"))
    if runs_tasks and not supports_cancel:
        findings.append(_f(
            "T2-cancel-undeclared", Severity.MEDIUM,
            "server runs requests as long-running tasks but declares no cancellation support",
            "declare (and implement) tasks/cancel so agents can stop work they started",
        ))
    return findings


def grade_task_lifecycle(observations: list[TaskObservation]) -> list[Finding]:
    """Grade observed task lifecycles: terminal-state, cancellation, orphaning, handle hygiene."""
    findings: list[Finding] = []
    for obs in observations:
        if not obs.reached_terminal:
            findings.append(_f(
                "T1-no-terminal-state", Severity.MEDIUM,
                f"task {obs.task_id!r} never reached a terminal state within the poll bound",
                "ensure every task transitions to completed/failed/cancelled",
            ))
        if obs.cancel_requested and not obs.cancelled:
            findings.append(_f(
                "T2-cancel-ignored", Severity.MEDIUM,
                f"task {obs.task_id!r} was cancelled but did not move to the cancelled state",
                "honor tasks/cancel — stop work and report the cancelled status",
            ))
        if obs.still_active_after_end:
            findings.append(_f(
                "T3-orphaned-task", Severity.MEDIUM,
                f"task {obs.task_id!r} kept emitting after a terminal/cancel state",
                "stop all work and emissions once a task reaches a terminal state",
            ))
        if obs.task_id and _WEAK_HANDLE.match(obs.task_id):
            findings.append(_f(
                "T4-weak-task-handle", Severity.LOW,
                f"task handle {obs.task_id!r} is sequential/guessable",
                "use an opaque, high-entropy task id so handles can't be enumerated",
            ))
    return findings


def _f(code: str, sev: Severity, message: str, remediation: str) -> Finding:
    return Finding(family="spec", code=code, severity=sev, message=message, remediation=remediation)
