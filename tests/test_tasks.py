"""Tasks-lifecycle conformance tests (issue #49) — spec-surface, experimental."""

from __future__ import annotations

from mcp_quality.config import ProbeConfig
from mcp_quality.connect.capture import TaskObservation
from mcp_quality.connect.client import FakeClient
from mcp_quality.engines.spec_surface import SpecSurfaceEngine
from mcp_quality.engines.tasks_checks import (
    grade_task_lifecycle,
    grade_tasks_declaration,
    tasks_capability,
)
from mcp_quality.models import ProbeContext

from .conftest import make_surface

_RO = {"name": "poll_job", "description": "Poll a job.", "inputSchema": {"type": "object"},
       "annotations": {"readOnlyHint": True}}


def _codes(findings):
    return {f.code for f in findings}


# -- capability detection ------------------------------------------------------

def test_tasks_capability_absent_is_none():
    assert tasks_capability(make_surface([_RO])) is None


def test_tasks_capability_present():
    surface = make_surface([_RO], capabilities={"tasks": {"requests": True, "cancel": True}})
    assert tasks_capability(surface) == {"requests": True, "cancel": True}


# -- static declaration conformance -------------------------------------------

def test_declaration_requests_without_cancel_flagged():
    assert "T2-cancel-undeclared" in _codes(grade_tasks_declaration({"requests": True, "cancel": False}))


def test_declaration_with_cancel_is_clean():
    assert grade_tasks_declaration({"requests": True, "cancel": True}) == []


def test_declaration_no_requests_is_clean():
    assert grade_tasks_declaration({"list": True}) == []


# -- lifecycle grading (pure) --------------------------------------------------

def test_lifecycle_clean_task_no_findings():
    obs = TaskObservation(task_id="a9f3c1e7b2", statuses=["working", "completed"], reached_terminal=True)
    assert grade_task_lifecycle([obs]) == []


def test_lifecycle_stuck_non_terminal():
    obs = TaskObservation(task_id="a9f3c1e7b2", statuses=["working", "working"], reached_terminal=False)
    assert "T1-no-terminal-state" in _codes(grade_task_lifecycle([obs]))


def test_lifecycle_cancel_ignored():
    obs = TaskObservation(task_id="a9f3c1e7b2", statuses=["working"], reached_terminal=True,
                          cancel_requested=True, cancelled=False)
    assert "T2-cancel-ignored" in _codes(grade_task_lifecycle([obs]))


def test_lifecycle_cancel_honored_is_clean():
    obs = TaskObservation(task_id="a9f3c1e7b2", statuses=["working", "cancelled"], reached_terminal=True,
                          cancel_requested=True, cancelled=True)
    assert grade_task_lifecycle([obs]) == []


def test_lifecycle_orphaned_task():
    obs = TaskObservation(task_id="a9f3c1e7b2", statuses=["working", "completed"], reached_terminal=True,
                          still_active_after_end=True)
    assert "T3-orphaned-task" in _codes(grade_task_lifecycle([obs]))


def test_lifecycle_weak_handle():
    assert "T4-weak-task-handle" in _codes(grade_task_lifecycle([
        TaskObservation(task_id="task-1", statuses=["completed"], reached_terminal=True)]))
    assert "T4-weak-task-handle" in _codes(grade_task_lifecycle([
        TaskObservation(task_id="42", statuses=["completed"], reached_terminal=True)]))


# -- engine integration --------------------------------------------------------

def _ctx(caps, *, tasks=None):
    surface = make_surface([_RO], capabilities=caps)
    return ProbeContext(surface=surface, config=ProbeConfig(), client=FakeClient(tasks=tasks))


async def test_engine_tasks_not_measured_without_capability():
    # no tasks capability, no other spec surface → whole family not measured
    fs = await SpecSurfaceEngine().run(_ctx({}))
    assert fs.measured is False


async def test_engine_grades_declaration_when_capability_present():
    # capability present but no live task drivable → declaration still graded, tasks measured
    fs = await SpecSurfaceEngine().run(_ctx({"tasks": {"requests": True, "cancel": False}}))
    assert "tasks" in fs.metrics["exercised"]
    assert any(f.code == "T2-cancel-undeclared" for f in fs.findings)


async def test_engine_drives_and_grades_lifecycle():
    # a server that ignores cancellation: the cancel probe returns cancel_requested but not cancelled
    obs = TaskObservation(task_id="deadbeef01", statuses=["working", "completed"],
                          reached_terminal=True, cancelled=False)
    fs = await SpecSurfaceEngine().run(
        _ctx({"tasks": {"requests": True, "cancel": True}}, tasks={"poll_job": obs}))
    assert fs.metrics["tasks_lifecycles_driven"] >= 1
    assert any(f.code == "T2-cancel-ignored" for f in fs.findings)  # from the cancel probe
