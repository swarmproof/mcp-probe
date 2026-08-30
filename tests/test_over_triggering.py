"""Over-triggering + selection-accuracy tests (issue #29)."""

from __future__ import annotations

from mcp_quality.config import ProbeConfig
from mcp_quality.engines.legibility import (
    OUT_OF_SCOPE_PROMPTS,
    LegibilityEngine,
    build_goals,
)
from mcp_quality.legibility.model import StubModel, _match_name

from .conftest import make_ctx, make_surface

TOOLS = [
    {"name": "get_weather", "description": "Return weather for a city.", "inputSchema": {"type": "object"}},
    {"name": "list_cities", "description": "List known cities.", "inputSchema": {"type": "object"}},
]


def _correct_choices():
    return {g: gold for g, gold in build_goals(make_surface(TOOLS))}


# -- _match_name allow_none -----------------------------------------------------

def test_match_name_declines_on_none():
    tools = [("get_weather", "x"), ("list_cities", "y")]
    assert _match_name("NONE", tools, allow_none=True) == ""
    assert _match_name("no tool fits here", tools, allow_none=True) == ""
    assert _match_name("nothing relevant", tools, allow_none=True) == ""  # unmatched → no fire
    assert _match_name("get_weather", tools, allow_none=True) == "get_weather"  # real fire
    assert _match_name("unparseable", tools, allow_none=False) == "get_weather"  # forced-choice fallback


# -- over-triggering probe ------------------------------------------------------

async def test_no_over_triggering_when_tools_decline(tmp_path):
    # unscripted out-of-scope prompts → StubModel declines (allow_none) → 0 false fires
    stub = StubModel(choices=_correct_choices())
    fs = await LegibilityEngine(model=stub).run(
        make_ctx(TOOLS, config=ProbeConfig(cache_dir=str(tmp_path))))
    assert fs.metrics["false_fire_rate"] == 0.0
    assert not any(f.code == "L6-over-triggering" for f in fs.findings)


async def test_over_triggering_detected_and_penalized(tmp_path):
    choices = _correct_choices()
    choices[OUT_OF_SCOPE_PROMPTS[0]] = "get_weather"  # fires on an unrelated prompt
    stub = StubModel(choices=choices)
    fs = await LegibilityEngine(model=stub).run(
        make_ctx(TOOLS, config=ProbeConfig(cache_dir=str(tmp_path))))
    assert fs.metrics["false_fire_rate"] == round(1 / len(OUT_OF_SCOPE_PROMPTS), 3)
    l6 = next((f for f in fs.findings if f.code == "L6-over-triggering"), None)
    assert l6 is not None
    assert fs.score < 100  # the false fire pulled the score down


async def test_selection_accuracy_metric_present(tmp_path):
    stub = StubModel(choices=_correct_choices())
    fs = await LegibilityEngine(model=stub).run(
        make_ctx(TOOLS, config=ProbeConfig(cache_dir=str(tmp_path))))
    assert fs.metrics["selection_accuracy"] == 1.0
    assert fs.metrics["false_fire_rate"] == 0.0
