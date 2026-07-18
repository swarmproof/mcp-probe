"""Snapshot store tests — build/diff, regression detection, rubric guard (TEST-PLAN §5 INT-7)."""

from __future__ import annotations

from mcp_probe import RUBRIC_VERSION
from mcp_probe.connect.discover import surface_from_tools
from mcp_probe.models import FamilyScore
from mcp_probe.snapshot import build_snapshot, diff_against_baseline


def _surface(desc="original"):
    return surface_from_tools(
        [{"name": "a", "description": desc, "inputSchema": {"type": "object"}}]
    )


def _families(contract_score=100, hard_gate=False):
    return {
        "contract": FamilyScore("contract", contract_score, "A" if contract_score >= 90 else "F", hard_gate_tripped=hard_gate),
        "cost": FamilyScore("cost", 100, "A"),
    }


def test_unchanged_surface_has_no_regression():
    surface = _surface()
    fams = _families()
    snap = build_snapshot(surface, fams)
    diff = diff_against_baseline(snap, surface, fams)
    assert not diff.has_regression
    assert diff.changed_tools == []


def test_changed_description_is_detected():
    base = build_snapshot(_surface("original"), _families())
    diff = diff_against_baseline(base, _surface("edited"), _families())
    assert diff.changed_tools == ["a"]


def test_score_drop_is_a_regression():
    base = build_snapshot(_surface(), _families(contract_score=100))
    diff = diff_against_baseline(base, _surface(), _families(contract_score=80))
    assert diff.score_delta["contract"] < 0
    assert diff.has_regression


def test_broken_contract_is_a_regression():
    base = build_snapshot(_surface(), _families(contract_score=100))
    diff = diff_against_baseline(
        base, _surface(), _families(contract_score=60, hard_gate=True)
    )
    assert diff.has_regression


def test_rubric_mismatch_refuses_score_comparison():
    base = build_snapshot(_surface(), _families())
    base["rubric_version"] = "1999.01.0"  # simulate an older rubric
    diff = diff_against_baseline(base, _surface(), _families(contract_score=10))
    assert diff.rubric_mismatch
    assert diff.score_delta == {}  # scores not compared across rubrics


def test_snapshot_records_current_rubric():
    snap = build_snapshot(_surface(), _families())
    assert snap["rubric_version"] == RUBRIC_VERSION
