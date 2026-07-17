"""Pipeline tests — engine orchestration, static not-measured handling, gate exit codes."""

from __future__ import annotations

from mcp_probe.config import ProbeConfig
from mcp_probe.connect.client import FakeClient, InvokeResult
from mcp_probe.connect.discover import surface_from_tools
from mcp_probe.exit_codes import ExitCode
from mcp_probe.pipeline import run_probe


def _surface(tools):
    return surface_from_tools(tools)


GOOD = [
    {"name": "get_x", "description": "Return x. Example: get_x().", "inputSchema": {"type": "object"},
     "annotations": {"readOnlyHint": True}},
]


async def test_static_run_scores_fast_path():
    cfg = ProbeConfig(families=("contract", "cost"), static_path="unused")
    outcome = await run_probe(cfg, surface=_surface(GOOD))  # client=None → static
    assert outcome.report.overall_grade in ("A", "B")
    assert outcome.exit_code == ExitCode.OK
    assert outcome.report.families["contract"].metrics["invocation_measured"] is False


async def test_live_run_with_injected_client():
    cfg = ProbeConfig(families=("contract", "cost"))
    client = FakeClient(results={"get_x": InvokeResult("get_x", False, {"x": 1})})
    outcome = await run_probe(cfg, surface=_surface(GOOD), client=client)
    assert outcome.report.families["contract"].metrics["invocation_measured"] is True
    assert client.calls  # tool was invoked


async def test_fail_under_gate_trips():
    # A bloated toolset scores low on cost; --fail-under A should fail.
    bloat = [
        {"name": f"t{i}", "description": "word " * 500, "inputSchema": {"type": "object"},
         "annotations": {"readOnlyHint": True}}
        for i in range(8)
    ]
    cfg = ProbeConfig(families=("cost",), fail_under="A")
    outcome = await run_probe(cfg, surface=_surface(bloat))
    assert outcome.report.overall_grade != "A"
    assert outcome.exit_code == ExitCode.GATE_FAILURE


async def test_pass_when_grade_meets_floor():
    cfg = ProbeConfig(families=("contract", "cost"), fail_under="B")
    outcome = await run_probe(cfg, surface=_surface(GOOD))
    assert outcome.exit_code == ExitCode.OK


async def test_engine_error_degrades_to_not_measured(monkeypatch):
    # If an engine raises, the run must not abort — that family becomes not-measured.
    from mcp_probe.engines.cost import CostEngine

    async def boom(self, ctx):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(CostEngine, "run", boom)
    cfg = ProbeConfig(families=("contract", "cost"))
    outcome = await run_probe(cfg, surface=_surface(GOOD))
    assert outcome.report.families["cost"].measured is False
    assert outcome.report.families["contract"].measured is True
