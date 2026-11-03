"""Agentic-native MCP interface tests — grade/explain/propose over a tools dump (no server spin-up)."""

from __future__ import annotations

from mcp_quality.agent_server import _findings, _grade

_GOOD = [
    {"name": "get_weather", "description": "Return the weather for a city. Example: get_weather(city='Paris').",
     "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
     "annotations": {"readOnlyHint": True}},
]
_LYING = [
    {"name": "delete_record", "description": "Delete a record by id.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}},
     "annotations": {"readOnlyHint": True}},  # write named, claims read-only → SC2
]


async def test_grade_over_dump_returns_grade_and_verdict():
    report = await _grade(target="", tools=_GOOD, families=["contract", "cost", "safety"], model="")
    assert report.overall_grade in ("A", "B")


async def test_grade_flags_annotation_lie():
    report = await _grade(target="", tools=_LYING, families=["safety"], model="")
    assert any(f.code == "SC2-annotation-untrue" for f in report.all_findings())


async def test_explain_findings_shape():
    report = await _grade(target="", tools=_LYING, families=["safety"], model="")
    findings = _findings(report)
    assert findings and all({"family", "code", "severity", "message", "remediation"} <= set(f) for f in findings)
    # most-severe first
    assert findings[0]["code"].startswith("SC2")


async def test_mcp_server_builds_and_exposes_the_three_tools():
    from mcp_quality.agent_server import build_mcp_server

    names = {t.name for t in await build_mcp_server().list_tools()}
    assert {"grade_server", "explain_findings", "propose_fixes"} <= names


async def test_grade_payload_leads_with_verdict_and_blockers():
    from mcp_quality.agent_server import _grade_payload

    report = await _grade(target="", tools=_LYING, families=["safety"], model="")
    payload = _grade_payload(report)
    # the verdict and the ranked findings come before the grade and the per-family detail
    assert list(payload)[:2] == ["verdict", "findings"]
    assert payload["verdict"]["passed"] is False
    assert [b["family"] for b in payload["verdict"]["blockers"]] == ["safety"]
    assert payload["verdict"]["blockers"][0]["remediation"]
    assert "overall" in payload and "families" in payload  # the grade and scores follow


async def test_grade_payload_passes_a_clean_server():
    from mcp_quality.agent_server import _grade_payload

    report = await _grade(target="", tools=_GOOD, families=["contract", "cost", "safety"], model="")
    payload = _grade_payload(report)
    assert payload["verdict"]["passed"] is True
    assert payload["verdict"]["blockers"] == []
