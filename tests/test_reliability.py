"""pass^k reliability overlay tests (issue #31) — the math, the short-circuit, the reruns."""

from __future__ import annotations

import pytest

from mcp_quality import pipeline
from mcp_quality.config import ProbeConfig
from mcp_quality.connect.discover import surface_from_tools
from mcp_quality.engines.base import EngineBase
from mcp_quality.models import FamilyScore
from mcp_quality.pipeline import run_probe
from mcp_quality.scoring.reliability import family_passed, pass_hat_k, reliability_metrics
from mcp_quality.trace import TraceSink

GOOD = [
    {"name": "get_x", "description": "Return x. Example: get_x().", "inputSchema": {"type": "object"},
     "annotations": {"readOnlyHint": True}},
]


def _surface(tools):
    return surface_from_tools(tools)


# -- pure pass^k math ----------------------------------------------------------

def test_pass_hat_k_all_pass_is_one():
    assert pass_hat_k(5, 5) == 1.0


def test_pass_hat_k_one_flake_drops_sharply():
    assert pass_hat_k(4, 5) == pytest.approx(0.8**5)  # a single flake in 5 → 0.33


def test_pass_hat_k_never_passes_is_zero():
    assert pass_hat_k(0, 3) == 0.0


def test_pass_hat_k_deterministic_single_trial():
    assert pass_hat_k(1, 1) == 1.0
    assert pass_hat_k(0, 1) == 0.0


def test_pass_hat_k_zero_trials_is_zero():
    assert pass_hat_k(1, 0) == 0.0


def test_reliability_metrics_shape():
    assert reliability_metrics(3, 4) == {
        "trials": 4, "passes": 3, "pass_rate": 0.75, "pass_hat_k": round(0.75**4, 4),
    }


def test_family_passed_predicate():
    assert family_passed(FamilyScore("x", 90.0, "A"))
    assert family_passed(FamilyScore("x", 62.0, "D"))
    assert not family_passed(FamilyScore("x", 10.0, "F"))
    assert not family_passed(FamilyScore.not_measured("x"))


# -- overlay behaviour (fake engines) -----------------------------------------

class _FlakyEngine(EngineBase):
    name = "flaky"
    deterministic = False
    calls = 0

    async def run(self, ctx):
        type(self).calls += 1
        passed = type(self).calls % 2 == 1  # calls 1,3 pass; 2,4 fail
        return FamilyScore("flaky", 100.0 if passed else 10.0, "A" if passed else "F")


class _DetEngine(EngineBase):
    name = "det"
    deterministic = True
    calls = 0

    async def run(self, ctx):
        type(self).calls += 1
        return FamilyScore("det", 100.0, "A")


async def test_nondeterministic_family_reruns_k_times(monkeypatch):
    _FlakyEngine.calls = 0
    monkeypatch.setitem(pipeline.ENGINE_REGISTRY, "flaky", _FlakyEngine)
    surface, trace = _surface(GOOD), TraceSink(run_id="t")
    cfg = ProbeConfig(families=("flaky",), reliability_k=4)

    ctx = pipeline._make_ctx(cfg, surface, None, trace, seed=42)
    primary = await pipeline._run_engine_once("flaky", ctx, None)  # trial #1 → pass
    families = {"flaky": primary}
    rel = await pipeline._run_reliability_overlay(cfg, surface, None, trace, families)

    # calls: 1 pass (primary) + 2 fail, 3 pass, 4 fail (reruns) → 2 passes of 4 trials
    assert _FlakyEngine.calls == 4
    assert families["flaky"].metrics["reliability"] == {
        "trials": 4, "passes": 2, "pass_rate": 0.5, "pass_hat_k": round(0.5**4, 4),
    }
    assert rel["k"] == 4 and rel["overall_pass_rate"] == 0.5


async def test_deterministic_family_short_circuits(monkeypatch):
    _DetEngine.calls = 0
    monkeypatch.setitem(pipeline.ENGINE_REGISTRY, "det", _DetEngine)
    surface, trace = _surface(GOOD), TraceSink(run_id="t")
    cfg = ProbeConfig(families=("det",), reliability_k=5)

    ctx = pipeline._make_ctx(cfg, surface, None, trace, seed=42)
    primary = await pipeline._run_engine_once("det", ctx, None)  # the only run
    families = {"det": primary}
    await pipeline._run_reliability_overlay(cfg, surface, None, trace, families)

    assert _DetEngine.calls == 1  # NO reruns despite reliability_k=5
    assert families["det"].metrics["reliability"] == {
        "trials": 1, "passes": 1, "pass_rate": 1.0, "pass_hat_k": 1.0,
    }


# -- end-to-end through the real pipeline --------------------------------------

async def test_fast_path_reliability_is_trivial_and_carried_in_meta():
    cfg = ProbeConfig(families=("contract", "cost"), reliability_k=3)
    outcome = await run_probe(cfg, surface=_surface(GOOD))
    rel = outcome.report.meta["reliability"]
    assert rel["k"] == 3
    assert rel["overall_pass_rate"] == 1.0 and rel["overall_pass_hat_k"] == 1.0
    # deterministic families ran exactly once (trials == 1), not three times.
    for fam in ("contract", "cost"):
        assert outcome.report.families[fam].metrics["reliability"]["trials"] == 1


async def test_k_of_one_adds_no_reliability_block():
    cfg = ProbeConfig(families=("contract", "cost"))  # reliability_k defaults to 1
    outcome = await run_probe(cfg, surface=_surface(GOOD))
    assert "reliability" not in outcome.report.meta
    assert "reliability" not in outcome.report.families["cost"].metrics


# -- CLI wiring ----------------------------------------------------------------

def test_cli_reliability_flag_parses():
    from mcp_quality.cli import build_parser

    args = build_parser().parse_args(["run", "some-cmd", "--reliability", "5"])
    assert args.reliability_k == 5
