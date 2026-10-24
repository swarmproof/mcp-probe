"""Tool-count overload gate tests (issue #63) — the ~40–50 selection cliff."""

from __future__ import annotations

from mcp_quality.config import ProbeConfig
from mcp_quality.engines.legibility import LegibilityEngine
from mcp_quality.legibility.lints import lint_tool_overload, overload_band
from mcp_quality.models import ProbeContext, Severity

from .conftest import make_surface


def _tools(n: int):
    return [{"name": f"tool_{i}", "description": f"Does thing {i}. Example: tool_{i}().",
             "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": True}}
            for i in range(n)]


# -- band math -----------------------------------------------------------------

def test_overload_band_thresholds():
    assert overload_band(10) == "ok"
    assert overload_band(15) == "ok"
    assert overload_band(16) == "above-ideal"
    assert overload_band(31) == "degraded"
    assert overload_band(51) == "overloaded"


# -- the lint ------------------------------------------------------------------

def test_lean_toolset_is_silent():
    assert lint_tool_overload(make_surface(_tools(8))) is None
    assert lint_tool_overload(make_surface(_tools(15))) is None


def test_above_ideal_is_info():
    f = lint_tool_overload(make_surface(_tools(20)))
    assert f is not None and f.code == "L8-tool-overload" and f.severity == Severity.INFO
    assert f.evidence["tool_count"] == 20 and f.evidence["band"] == "above-ideal"


def test_degraded_is_low():
    f = lint_tool_overload(make_surface(_tools(40)))
    assert f.severity == Severity.LOW and f.evidence["band"] == "degraded"


def test_overloaded_is_medium_and_names_the_cliff():
    f = lint_tool_overload(make_surface(_tools(60)))
    assert f.severity == Severity.MEDIUM and f.evidence["band"] == "overloaded"
    assert "cliff" in f.message
    assert "dynamic" in f.remediation or "sub-server" in f.remediation


# -- engine integration (runs on the free, no-model path) ----------------------

async def test_engine_surfaces_overload_without_a_model():
    ctx = ProbeContext(surface=make_surface(_tools(60)), config=ProbeConfig(), client=None)
    fs = await LegibilityEngine().run(ctx)  # no model → lints-only path
    assert fs.metrics["tool_count"] == 60
    assert fs.metrics["overload_band"] == "overloaded"
    assert any(f.code == "L8-tool-overload" for f in fs.findings)


async def test_engine_clean_for_lean_toolset():
    ctx = ProbeContext(surface=make_surface(_tools(5)), config=ProbeConfig(), client=None)
    fs = await LegibilityEngine().run(ctx)
    assert fs.metrics["overload_band"] == "ok"
    assert not any(f.code == "L8-tool-overload" for f in fs.findings)
