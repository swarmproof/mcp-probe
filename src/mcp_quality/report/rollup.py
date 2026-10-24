"""The overall quality verdict rollup — one honest pass/fail over a scored :class:`Report` (#67).

Readers need a single "does this pass, and what's blocking it" more than they need five
sub-scores. This derives that verdict **without re-scoring**: it reuses the hard-gate /
F-grade signals the Scorer already computed and the remediations the engines already
attached. It is a pure, read-only projection of the Report (ADR-001), so it is
deterministic — no wall-clock, no network — and unit-testable against a fixed Report.

The rule (PRD §7 hard-gate doctrine):

* A **measured** family is a *blocker* when it trips its hard gate or grades **F**.
* An **unmeasured** family is a *caveat*, never a blocker (ADR-006) — static/offline runs
  are reported on what they could measure, never punished for what they couldn't.
* ``passed`` is True iff there are no blockers.
"""

from __future__ import annotations

from typing import Any

from mcp_quality.config import ALL_FAMILIES
from mcp_quality.models import Finding, Report


def _ordered_families(report: Report) -> list[str]:
    """Canonical family order first (stable diffing), then any extra families sorted."""
    extra = sorted(n for n in report.families if n not in ALL_FAMILIES)
    return [n for n in (*ALL_FAMILIES, *extra) if n in report.families]


def _top_remediation(findings: list[Finding]) -> str | None:
    """The fix to surface for a blocking family: the remediation on the most severe finding
    that carries one. Ties break on finding order (engine-emitted, stable)."""
    with_fix = [f for f in findings if f.remediation]
    if not with_fix:
        return None
    return max(with_fix, key=lambda f: f.severity).remediation


def _blocker_reason(family: str, grade: str, hard_gate_tripped: bool) -> str:
    if hard_gate_tripped:
        return f"{family} tripped a hard gate (broken contract / critical finding)"
    return f"{family} graded {grade}"


def quality_verdict(report: Report) -> dict[str, Any]:
    """Compute the pass/fail verdict rollup. See the module docstring for the rule.

    Returns ``{"passed": bool, "blockers": [...], "caveats": [...]}`` where each blocker is
    ``{"family", "reason", "remediation"}`` and ``caveats`` lists the unmeasured families.
    """
    blockers: list[dict[str, Any]] = []
    caveats: list[str] = []

    for name in _ordered_families(report):
        fam = report.families[name]
        if not fam.measured:
            caveats.append(name)
            continue
        if fam.hard_gate_tripped or fam.grade == "F":
            blockers.append(
                {
                    "family": name,
                    "reason": _blocker_reason(name, fam.grade, fam.hard_gate_tripped),
                    "remediation": _top_remediation(fam.findings),
                }
            )

    return {"passed": not blockers, "blockers": blockers, "caveats": caveats}
