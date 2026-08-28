"""Cisco readiness adapter tests (issue #13, REQ-S6) — parse + family routing, and the
pipeline fold into Performance/Contract."""

from __future__ import annotations

import json

import pytest

from mcp_quality.config import ProbeConfig
from mcp_quality.models import FamilyScore, Finding, Severity
from mcp_quality.security.adapters import CiscoReadinessAdapter


def _readiness_json() -> str:
    return json.dumps({
        "results": [{
            "name": "fetch_data", "type": "tool", "severity": "MEDIUM",
            "findings": [
                {"analyzer": "readiness", "severity": "MEDIUM", "threat_summary": "no request timeout configured",
                 "details": [{"name": "timeout-missing", "description": "no timeout"}]},
                {"analyzer": "readiness", "severity": "LOW", "threat_summary": "errors are not handled",
                 "details": [{"name": "error-handling", "description": "unhandled errors"}]},
            ],
        }],
    })


def test_readiness_routes_to_perf_and_contract():
    findings = CiscoReadinessAdapter()._parse(_readiness_json())
    by_family = {f.family: f for f in findings}
    assert by_family["performance"].code.startswith("readiness-timeout")
    assert by_family["contract"].code.startswith("readiness-error")
    assert all(f.source == "cisco" for f in findings)


class _FakeReadiness:
    name = "fake-readiness"

    def available(self) -> bool:
        return True

    def scan(self, target: str):
        return [
            Finding("performance", "readiness-timeout", Severity.MEDIUM, "[readiness] no timeout", source="cisco"),
            Finding("contract", "readiness-error-handling", Severity.LOW, "[readiness] unhandled", source="cisco"),
        ]


async def test_pipeline_folds_readiness_into_families(monkeypatch):
    from mcp_quality import pipeline

    monkeypatch.setattr(
        "mcp_quality.security.adapters.DEFAULT_READINESS_ADAPTERS", [_FakeReadiness()], raising=True
    )
    families = {
        "contract": FamilyScore("contract", 100, "A"),
        "performance": FamilyScore("performance", 90, "A"),
    }
    pipeline._fold_readiness(ProbeConfig(deep_security=True, target="x"), families)
    assert any(f.code == "readiness-timeout" for f in families["performance"].findings)
    assert any(f.code == "readiness-error-handling" for f in families["contract"].findings)
    assert families["performance"].metrics["readiness_findings"] == 1


async def test_pipeline_skips_when_family_not_measured(monkeypatch):
    from mcp_quality import pipeline

    monkeypatch.setattr(
        "mcp_quality.security.adapters.DEFAULT_READINESS_ADAPTERS", [_FakeReadiness()], raising=True
    )
    # performance not measured (static) → its readiness finding is dropped, not attached
    families = {
        "contract": FamilyScore("contract", 100, "A"),
        "performance": FamilyScore.not_measured("performance", "static"),
    }
    pipeline._fold_readiness(ProbeConfig(deep_security=True, target="x"), families)
    assert families["performance"].findings == []
    assert any(f.code == "readiness-error-handling" for f in families["contract"].findings)


@pytest.mark.parametrize("text,family", [
    ("request timeout too low", "performance"),
    ("retries not configured", "performance"),
    ("no input validation", "contract"),
    ("missing error handling", "contract"),
])
def test_readiness_routing_heuristic(text, family):
    item = {"tool": "t", "severity": "low", "title": text, "id": text.split()[0]}
    assert CiscoReadinessAdapter()._normalize(item).family == family
