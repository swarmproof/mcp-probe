"""Multi-model consensus tests (issue #50) — agreement signal, deterministic, no live LLM."""

from __future__ import annotations

from mcp_quality.config import ProbeConfig
from mcp_quality.engines.legibility import LegibilityEngine
from mcp_quality.legibility.consensus import agreement_per_goal, consensus_report
from mcp_quality.models import ProbeContext

from .conftest import make_surface

_TOOLS = [
    {"name": "alpha", "description": "Alpha does the alpha thing.", "inputSchema": {"type": "object"}},
    {"name": "beta", "description": "Beta does the beta thing.", "inputSchema": {"type": "object"}},
]


class _FixedModel:
    """A model that always picks one tool — lets a test force agreement or divergence."""

    def __init__(self, pick: str, *, model_id: str, canonical: bool = False, seed: int = 42) -> None:
        self._pick = pick
        self.model_id = model_id
        self.seed = seed
        self.is_canonical = canonical
        self.call_count = 0

    def choose_tool(self, goal, tools, *, allow_none: bool = False) -> str:
        self.call_count += 1
        return self._pick

    def propose_rewrite(self, name, description, confusers) -> str:
        return ""


def _ctx(tmp_path, models=None, panel_specs=()):
    cfg = ProbeConfig(models=tuple(panel_specs), cache_dir=str(tmp_path))
    return ProbeContext(surface=make_surface(_TOOLS), config=cfg, client=None)


# -- pure agreement math -------------------------------------------------------

def test_agreement_unanimous():
    assert agreement_per_goal([["a", "a"], ["a", "a"]]) == [1.0, 1.0]


def test_agreement_split_two_models():
    # goal 0: a vs a (agree); goal 1: a vs b (split) → 0.5
    assert agreement_per_goal([["a", "a"], ["a", "b"]]) == [1.0, 0.5]


def test_agreement_majority_three_models():
    # two pick a, one picks b → 2/3
    assert agreement_per_goal([["a"], ["a"], ["b"]]) == [2 / 3]


def test_consensus_report_shape():
    rep = consensus_report(["m1", "m2"], [["a", "a"], ["a", "b"]],
                           [("g0", "a"), ("g1", "a")])
    assert rep["mean_agreement"] == 0.75
    assert rep["disagreement_rate"] == 0.5
    assert rep["divergent_goals"][0]["goal"] == "g1"
    assert rep["divergent_goals"][0]["picks"] == {"a": 1, "b": 1}


# -- engine integration (StubModel/fixed panel) --------------------------------

async def test_single_model_has_no_consensus_metric(tmp_path):
    from mcp_quality.legibility.model import StubModel
    fs = await LegibilityEngine(model=StubModel()).run(_ctx(tmp_path))
    assert "consensus" not in fs.metrics


async def test_unanimous_panel_no_disagreement_finding(tmp_path):
    panel = [_FixedModel("alpha", model_id="m1", canonical=True), _FixedModel("alpha", model_id="m2")]
    fs = await LegibilityEngine(panel=panel).run(_ctx(tmp_path))
    c = fs.metrics["consensus"]
    assert c["mean_agreement"] == 1.0 and c["disagreement_rate"] == 0.0
    assert not any(f.code == "L7-model-disagreement" for f in fs.findings)
    assert c["canonical"] is True  # a canonical model is in the panel


async def test_divergent_panel_fires_l7(tmp_path):
    panel = [_FixedModel("alpha", model_id="m1"), _FixedModel("beta", model_id="m2")]
    fs = await LegibilityEngine(panel=panel).run(_ctx(tmp_path))
    c = fs.metrics["consensus"]
    assert c["disagreement_rate"] == 1.0  # every goal split
    assert c["canonical"] is False  # no canonical model in the panel
    l7 = next((f for f in fs.findings if f.code == "L7-model-disagreement"), None)
    assert l7 is not None and l7.evidence["models"] == ["m1", "m2"]


async def test_panel_picks_cached_rerun_invokes_models_zero_times(tmp_path):
    panel = [_FixedModel("alpha", model_id="m1"), _FixedModel("beta", model_id="m2")]
    eng = LegibilityEngine(panel=panel)
    await eng.run(_ctx(tmp_path))
    after_first = panel[1].call_count
    assert after_first > 0  # the non-primary panel model was invoked on the first run
    await eng.run(_ctx(tmp_path))  # same surface/seed → panel-picks cache hit
    assert panel[1].call_count == after_first  # zero additional invocations (REQ-L6)
