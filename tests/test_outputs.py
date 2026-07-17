"""Output-layer tests — JSON contract shape + determinism, badge colours/SVG (TEST-PLAN
§7, E2E-9). The fast-path JSON must be byte-identical across runs (NFR-2)."""

from __future__ import annotations

import json

from mcp_probe import REPORT_SCHEMA
from mcp_probe.connect.discover import surface_from_tools
from mcp_probe.models import FamilyScore, Report
from mcp_probe.report import report_to_dict, report_to_json
from mcp_probe.report.badge import badge_color, badge_svg, shields_endpoint


def _report():
    surface = surface_from_tools(
        [{"name": "a", "description": "d", "inputSchema": {"type": "object"}}]
    )
    families = {
        "cost": FamilyScore("cost", 71.0, "C", metrics={"toolset_tokens": 8140}),
        "contract": FamilyScore("contract", 100.0, "A"),
    }
    return Report(
        overall_score=82.4,
        overall_grade="B",
        families=families,
        surface=surface,
        rubric_version="2026.07.1",
        tool_version="0.1.0",
        weights={"cost": 0.6, "contract": 0.4},
        meta={"elapsed_s": 0.12},
    )


def test_json_schema_shape():
    doc = report_to_dict(_report())
    assert doc["schema"] == REPORT_SCHEMA
    assert doc["overall"]["grade"] == "B"
    assert "provenance_hash" in doc
    assert doc["families"]["cost"]["metrics"]["toolset_tokens"] == 8140
    assert doc["families"]["cost"]["weight"] == 0.6


def test_json_is_byte_identical_without_meta():
    # Determinism guard: identical inputs → identical output (timing excluded).
    a = report_to_json(_report(), include_meta=False)
    b = report_to_json(_report(), include_meta=False)
    assert a == b


def test_meta_excluded_when_requested():
    doc = report_to_dict(_report(), include_meta=False)
    assert "meta" not in doc


def test_provenance_hash_is_stable():
    assert _report().provenance_hash() == _report().provenance_hash()


def test_provenance_hash_changes_with_score():
    r = _report()
    r2 = _report()
    r2.overall_score = 50.0
    assert r.provenance_hash() != r2.provenance_hash()


def test_badge_colours():
    assert badge_color("A") == "brightgreen"
    assert badge_color("F") == "red"
    assert badge_color("not-measured") == "lightgrey"


def test_badge_svg_contains_grade_and_rubric():
    svg = badge_svg("A", rubric_version="2026.07.1")
    assert "<svg" in svg
    assert "mcp-probe" in svg
    assert "2026.07.1" in svg


def test_shields_endpoint_payload():
    ep = shields_endpoint("B")
    assert ep == {"schemaVersion": 1, "label": "mcp-probe", "message": "B", "color": "green"}
    json.dumps(ep)  # must be serializable
