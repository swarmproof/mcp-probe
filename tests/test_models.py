"""Core model unit tests — surface_hash stability, Finding round-trip (TEST-PLAN §7)."""

from __future__ import annotations

from mcp_probe.connect.discover import surface_from_tools
from mcp_probe.models import Finding, Severity


def _tools(order: list[str]):
    return [{"name": n, "description": f"desc {n}", "inputSchema": {"type": "object"}} for n in order]


def test_surface_hash_is_order_independent():
    a = surface_from_tools(_tools(["x", "y", "z"]))
    b = surface_from_tools(_tools(["z", "y", "x"]))
    assert a.surface_hash == b.surface_hash  # reordering must not change the hash


def test_surface_hash_changes_on_description_edit():
    a = surface_from_tools(_tools(["x"]))
    edited = [{"name": "x", "description": "DIFFERENT", "inputSchema": {"type": "object"}}]
    b = surface_from_tools(edited)
    assert a.surface_hash != b.surface_hash  # editing a description must change it


def test_finding_round_trip():
    f = Finding(
        family="security",
        code="S1",
        severity=Severity.HIGH,
        message="hidden instruction",
        tool="do_thing",
        owasp_id="LLM01:2025",
        source="builtin",
        evidence={"span": [1, 2]},
    )
    d = f.to_dict()
    assert d["severity"] == "high"
    back = Finding.from_dict("security", d)
    assert back.code == "S1"
    assert back.severity == Severity.HIGH
    assert back.owasp_id == "LLM01:2025"
    assert back.evidence == {"span": [1, 2]}


def test_severity_parse():
    assert Severity.parse("critical") == Severity.CRITICAL
    assert Severity.parse(4) == Severity.CRITICAL
    assert Severity.parse(Severity.LOW) == Severity.LOW


def test_read_only_and_destructive_hints():
    surface = surface_from_tools(
        [
            {"name": "r", "description": "d", "inputSchema": {}, "annotations": {"readOnlyHint": True}},
            {"name": "d", "description": "d", "inputSchema": {}, "annotations": {"destructiveHint": True}},
        ]
    )
    assert surface.tool("r").is_read_only
    assert surface.tool("d").is_destructive
