"""Quality verdict rollup tests (#67) — the pass/fail verdict over a scored Report.

Covers: a clean report → pass; a hard-gated / F family → blocker carrying remediation;
an unmeasured family → caveat (never a blocker, ADR-006); the JSON contract carries the
key; and the rollup stays deterministic (no wall-clock).
"""

from __future__ import annotations

from mcp_quality.connect.discover import surface_from_tools
from mcp_quality.models import FamilyScore, Finding, Report, Severity
from mcp_quality.report import quality_verdict, report_to_dict
from mcp_quality.report.render import render_terminal


def _report(families: dict[str, FamilyScore], *, grade: str = "A", hard_gate: str | None = None) -> Report:
    surface = surface_from_tools(
        [{"name": "a", "description": "d", "inputSchema": {"type": "object"}}]
    )
    return Report(
        overall_score=90.0,
        overall_grade=grade,
        families=families,
        surface=surface,
        rubric_version="2026.08.1",
        tool_version="0.5.0",
        weights={name: 1.0 / len(families) for name in families},
        hard_gate=hard_gate,
        meta={"elapsed_s": 0.1},
    )


def test_clean_report_passes():
    report = _report(
        {
            "contract": FamilyScore("contract", 100.0, "A"),
            "cost": FamilyScore("cost", 88.0, "B"),
        }
    )
    rollup = quality_verdict(report)
    assert rollup["passed"] is True
    assert rollup["blockers"] == []
    assert rollup["caveats"] == []


def test_hard_gated_family_is_a_blocker_with_remediation():
    fix = "Declare an outputSchema and return deterministic results for identical inputs."
    contract = FamilyScore(
        "contract",
        40.0,
        "F",
        hard_gate_tripped=True,
        findings=[
            Finding("contract", "C5-nondeterminism", Severity.CRITICAL, "non-deterministic output", remediation=fix),
            Finding("contract", "C2-schema", Severity.LOW, "minor", remediation="ignore me"),
        ],
    )
    report = _report({"contract": contract, "cost": FamilyScore("cost", 90.0, "A")}, grade="C", hard_gate="contract")
    rollup = quality_verdict(report)

    assert rollup["passed"] is False
    assert len(rollup["blockers"]) == 1
    blocker = rollup["blockers"][0]
    assert blocker["family"] == "contract"
    assert "hard gate" in blocker["reason"]
    # Remediation is pulled from the *most severe* finding, not the first.
    assert blocker["remediation"] == fix


def test_f_grade_without_explicit_gate_is_a_blocker():
    cost = FamilyScore(
        "cost",
        30.0,
        "F",
        findings=[Finding("cost", "T1-bloat", Severity.HIGH, "toolset too heavy", remediation="trim tools")],
    )
    report = _report({"cost": cost}, grade="C")
    rollup = quality_verdict(report)
    assert rollup["passed"] is False
    assert rollup["blockers"][0]["family"] == "cost"
    assert rollup["blockers"][0]["reason"] == "cost graded F"
    assert rollup["blockers"][0]["remediation"] == "trim tools"


def test_blocker_without_findings_has_null_remediation():
    report = _report({"contract": FamilyScore("contract", 40.0, "F")}, grade="F")
    blocker = quality_verdict(report)["blockers"][0]
    assert blocker["remediation"] is None


def test_unmeasured_family_is_a_caveat_not_a_blocker():
    report = _report(
        {
            "cost": FamilyScore("cost", 95.0, "A"),
            "performance": FamilyScore.not_measured("performance", "requires a live server (static mode)"),
            "legibility": FamilyScore.not_measured("legibility", "no model"),
        }
    )
    rollup = quality_verdict(report)
    assert rollup["passed"] is True
    assert rollup["blockers"] == []
    # Canonical family order: legibility before performance.
    assert rollup["caveats"] == ["legibility", "performance"]


def test_json_contains_verdict_key():
    report = _report({"contract": FamilyScore("contract", 100.0, "A")})
    doc = report_to_dict(report)
    assert "verdict" in doc
    assert doc["verdict"]["passed"] is True
    assert set(doc["verdict"]) == {"passed", "blockers", "caveats"}


def test_rollup_is_deterministic():
    def build() -> Report:
        return _report(
            {
                "contract": FamilyScore(
                    "contract", 40.0, "F", hard_gate_tripped=True,
                    findings=[Finding("contract", "C5", Severity.CRITICAL, "bad", remediation="fix it")],
                ),
                "performance": FamilyScore.not_measured("performance", "static"),
            },
            grade="C",
            hard_gate="contract",
        )

    assert quality_verdict(build()) == quality_verdict(build())


def test_terminal_renders_verdict():
    passing = _report({"contract": FamilyScore("contract", 100.0, "A")})
    assert "Verdict: PASS" in render_terminal(passing)

    gated = _report(
        {
            "contract": FamilyScore(
                "contract", 40.0, "F", hard_gate_tripped=True,
                findings=[Finding("contract", "C5", Severity.CRITICAL, "bad", remediation="declare schema")],
            ),
            "performance": FamilyScore.not_measured("performance", "static"),
        },
        grade="C",
        hard_gate="contract",
    )
    out = render_terminal(gated)
    assert "Verdict: FAIL" in out
    assert "1 blocker" in out
    assert "declare schema" in out
    assert "caveats (not measured): performance" in out
