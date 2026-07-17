"""Scorer component tests — weighted-mean math, hard-gate, grade-band boundaries,
renormalization for not-measured families (TEST-PLAN §6 Scorer)."""

from __future__ import annotations

import pytest

from mcp_probe.models import FamilyScore
from mcp_probe.scoring import Scorer, grade_for_score


@pytest.mark.parametrize(
    "score,grade",
    [(100, "A"), (90, "A"), (89.9, "B"), (89, "B"), (80, "B"), (79.9, "C"), (70, "C"), (60, "D"), (59.9, "F"), (0, "F")],
)
def test_grade_band_boundaries(score, grade):
    # 90 → A, 89 → B (TEST-PLAN §6).
    assert grade_for_score(score) == grade


def _fam(name, score, *, hard_gate=False):
    return FamilyScore(name, score, grade_for_score(score), hard_gate_tripped=hard_gate)


def test_weighted_mean_all_families():
    families = {
        "cost": _fam("cost", 80),
        "legibility": _fam("legibility", 80),
        "contract": _fam("contract", 80),
        "performance": _fam("performance", 80),
        "security": _fam("security", 80),
    }
    result = Scorer().score(families)
    assert result.overall_score == pytest.approx(80.0)
    assert result.overall_grade == "B"
    assert result.hard_gate is None


def test_weights_renormalize_when_not_measured():
    # Only cost + contract measured → their weights (0.30, 0.20) renormalize to 0.6/0.4.
    families = {
        "cost": _fam("cost", 90),
        "contract": _fam("contract", 40),
        "performance": FamilyScore.not_measured("performance", "static"),
    }
    result = Scorer().score(families)
    # 90*0.6 + 40*0.4 = 54 + 16 = 70
    assert result.overall_score == pytest.approx(70.0)
    assert "performance" not in result.effective_weights
    assert result.effective_weights["cost"] == pytest.approx(0.6)


def test_hard_gate_caps_at_c_even_with_high_score():
    families = {
        "cost": _fam("cost", 100),
        "contract": _fam("contract", 95, hard_gate=True),  # broken contract
    }
    result = Scorer().score(families)
    assert result.overall_score > 90  # numeric score stays high
    assert result.overall_grade == "C"  # but grade is capped
    assert result.hard_gate == "contract"


def test_family_scoring_f_hard_gates():
    families = {"cost": _fam("cost", 100), "security": _fam("security", 30)}
    result = Scorer().score(families)
    assert result.overall_grade == "C"
    assert result.hard_gate == "security"


def test_all_not_measured():
    families = {"performance": FamilyScore.not_measured("performance")}
    result = Scorer().score(families)
    assert result.overall_score is None
    assert result.overall_grade == "not-measured"
