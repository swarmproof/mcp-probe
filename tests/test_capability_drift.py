"""Capability-stability / version-drift tests (issue #27)."""

from __future__ import annotations

from mcp_quality.config import ProbeConfig
from mcp_quality.connect.discover import surface_from_tools
from mcp_quality.exit_codes import ExitCode
from mcp_quality.models import FamilyScore
from mcp_quality.pipeline import run_probe
from mcp_quality.snapshot import build_snapshot, diff_against_baseline, write_snapshot

_FAMS = {"cost": FamilyScore("cost", 100.0, "A")}


def _diff(old_tools, new_tools):
    baseline = build_snapshot(surface_from_tools(old_tools), _FAMS)
    return diff_against_baseline(baseline, surface_from_tools(new_tools), _FAMS)


def _tool(name, *, read_only=None, destructive=None, props=None, required=None, desc="d"):
    ann = {}
    if read_only is not None:
        ann["readOnlyHint"] = read_only
    if destructive is not None:
        ann["destructiveHint"] = destructive
    schema = {"type": "object", "properties": props or {}}
    if required:
        schema["required"] = required
    return {"name": name, "description": desc, "inputSchema": schema, "annotations": ann}


def _kinds(diff):
    return {c["kind"] for c in diff.capability_changes}


def test_scope_expansion_read_only_lost():
    d = _diff([_tool("t", read_only=True)], [_tool("t", read_only=False)])
    assert "scope-expansion" in _kinds(d)
    assert d.has_regression


def test_scope_expansion_became_destructive():
    d = _diff([_tool("t", destructive=False)], [_tool("t", destructive=True)])
    assert "scope-expansion" in _kinds(d)
    assert d.has_regression


def test_breaking_new_required_field():
    d = _diff([_tool("t", props={"id": {"type": "string"}})],
              [_tool("t", props={"id": {"type": "string"}}, required=["id"])])
    assert "breaking-schema" in _kinds(d)
    assert d.has_regression


def test_breaking_removed_param():
    d = _diff([_tool("t", props={"a": {"type": "string"}, "b": {"type": "string"}})],
              [_tool("t", props={"a": {"type": "string"}})])
    assert any("removed param" in c["detail"] for c in d.capability_changes)
    assert d.has_regression


def test_breaking_type_change():
    d = _diff([_tool("t", props={"a": {"type": "string"}})],
              [_tool("t", props={"a": {"type": "integer"}})])
    assert any("type" in c["detail"] for c in d.capability_changes)


def test_additive_optional_param_is_not_a_regression():
    d = _diff([_tool("t", props={"a": {"type": "string"}})],
              [_tool("t", props={"a": {"type": "string"}, "b": {"type": "string"}})])
    assert d.capability_changes == []
    assert not d.has_regression


def test_removed_tool_is_a_regression():
    d = _diff([_tool("t1"), _tool("t2")], [_tool("t1")])
    assert d.removed_tools == ["t2"]
    assert d.has_regression


def test_added_tool_is_not_a_regression():
    d = _diff([_tool("t1")], [_tool("t1"), _tool("t2")])
    assert d.added_tools == ["t2"]
    assert not d.has_regression


async def test_no_regressions_gate_fails_on_scope_expansion(tmp_path):
    snap = tmp_path / "snapshot.json"
    write_snapshot(snap, build_snapshot(surface_from_tools([_tool("act", read_only=True)]), _FAMS))
    cfg = ProbeConfig(families=("cost",), no_regressions=True, snapshot_path=str(snap))
    outcome = await run_probe(cfg, surface=surface_from_tools([_tool("act", read_only=False)]))
    assert outcome.report.regression["capability_changes"]
    assert outcome.exit_code == ExitCode.GATE_FAILURE
