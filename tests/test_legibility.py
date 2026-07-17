"""Legibility tests with the StubModel harness (TEST-PLAN §3, §6, E2E-3/E2E-4).

Never calls a real LLM. Asserts exact selection-rate + confusion matrix, proves caching
(second run invokes the model zero times), and checks the offline lints/similarity."""

from __future__ import annotations

from mcp_probe.config import ProbeConfig
from mcp_probe.engines.legibility import LegibilityEngine, build_goals
from mcp_probe.legibility.lints import lint_descriptions
from mcp_probe.legibility.model import StubModel
from mcp_probe.legibility.similarity import confusable_shortlist

from .conftest import make_ctx, make_surface

CONFUSABLE = [
    {"name": "delete_record", "description": "Remove a record by id.", "inputSchema": {"type": "object"}},
    {"name": "archive_record", "description": "Remove a record by id.", "inputSchema": {"type": "object"}},
]


# -- offline lints & similarity (no model) ------------------------------------

def test_lints_flag_missing_description_and_no_example():
    surface = make_surface([{"name": "t", "description": "", "inputSchema": {"type": "object"}}])
    codes = {f.code for f in lint_descriptions(surface)}
    assert "L3-missing-description" in codes


def test_similarity_shortlists_confusable_pair():
    surface = make_surface(CONFUSABLE)
    pairs = confusable_shortlist(surface, threshold=0.3)
    assert pairs
    assert {pairs[0][0], pairs[0][1]} == {"delete_record", "archive_record"}


async def test_no_model_scores_from_lints_only():
    ctx = make_ctx([{"name": "t", "description": "", "inputSchema": {"type": "object"}}])
    fs = await LegibilityEngine(model=None).run(ctx)
    assert fs.measured is True
    assert fs.metrics["selection_rate"] is None  # behavioural not measured
    assert fs.score < 100  # lint penalty applied


# -- behavioural probe with StubModel -----------------------------------------

def _confusion_stub(confuse_fraction_goals: set[str]) -> StubModel:
    """Stub that picks delete_record for a chosen subset of archive_record's goals."""
    goals = build_goals(make_surface(CONFUSABLE))
    archive_goals = [g for g, gold in goals if gold == "archive_record"]
    choices = {}
    for g in archive_goals:
        choices[g] = "delete_record" if g in confuse_fraction_goals else "archive_record"
    # delete_record's own goals resolve correctly
    for g, gold in goals:
        if gold == "delete_record":
            choices[g] = "delete_record"
    return StubModel(choices=choices, model_id="stub-qwen", seed=42)


async def test_disambiguation_matrix_reports_confusion(tmp_path):
    goals = build_goals(make_surface(CONFUSABLE))
    archive_goals = [g for g, gold in goals if gold == "archive_record"]
    # confuse 1 of 3 archive goals → 33% confusion
    stub = _confusion_stub({archive_goals[0]})
    ctx = make_ctx(CONFUSABLE, config=ProbeConfig(cache_dir=str(tmp_path)))
    fs = await LegibilityEngine(model=stub).run(ctx)
    tc = fs.metrics["top_confusion"]
    assert tc[0] == "archive_record" and tc[1] == "delete_record"
    assert tc[2] >= 0.30
    assert any(f.code == "L5-rewrite" for f in fs.findings)  # rewrite proposed
    assert fs.grade in ("B", "C", "D", "F")


async def test_caching_second_run_invokes_model_zero_times(tmp_path):
    stub = _confusion_stub(set())  # all correct
    ctx = make_ctx(CONFUSABLE, config=ProbeConfig(cache_dir=str(tmp_path)))
    await LegibilityEngine(model=stub).run(ctx)
    calls_after_first = stub.call_count
    assert calls_after_first > 0

    stub2 = _confusion_stub(set())
    stub2.model_id = "stub-qwen"  # same key → cache hit
    ctx2 = make_ctx(CONFUSABLE, config=ProbeConfig(cache_dir=str(tmp_path)))
    fs2 = await LegibilityEngine(model=stub2).run(ctx2)
    assert stub2.call_count == 0  # served from cache (REQ-L6)
    assert fs2.metrics["cache_hit"] is True


async def test_clean_server_high_selection_rate(tmp_path):
    tools = [
        {"name": "get_weather", "description": "Return weather for a city.", "inputSchema": {"type": "object"}},
        {"name": "list_cities", "description": "List known cities.", "inputSchema": {"type": "object"}},
    ]
    # stub always picks correctly
    goals = build_goals(make_surface(tools))
    choices = {g: gold for g, gold in goals}
    stub = StubModel(choices=choices)
    ctx = make_ctx(tools, config=ProbeConfig(cache_dir=str(tmp_path)))
    fs = await LegibilityEngine(model=stub).run(ctx)
    assert fs.metrics["selection_rate"] == 1.0
