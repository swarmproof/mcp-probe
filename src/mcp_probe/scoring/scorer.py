"""The Scorer — the one place family sub-scores become an overall grade (ARCHITECTURE §1).

Rules (PRD §7), all versioned by ``RUBRIC_VERSION`` (ADR-008):

* Overall = **weighted mean** of the *measured* families' 0–100 sub-scores.
* Weights are opinionated and reflect what hurts agents at runtime (Cost is paid every
  turn, so it dominates). Not-measured families are dropped and the remaining weights
  **renormalized** — static/offline runs are scored on what they could measure, never
  penalised with zeros (ADR-006).
* **Hard gate:** if any measured family trips its gate (broken contract, critical
  security finding) *or* scores an F, the overall grade is capped at **C**. The numeric
  score is left intact so the report can show "score 95 but graded C because …".
"""

from __future__ import annotations

from dataclasses import dataclass

from mcp_probe import RUBRIC_VERSION
from mcp_probe.models import FamilyScore

# Default weights (PRD §7.1). Must sum to 1.0.
DEFAULT_WEIGHTS: dict[str, float] = {
    "cost": 0.30,
    "legibility": 0.25,
    "contract": 0.20,
    "performance": 0.15,
    "security": 0.10,
}

# Letter bands (PRD §7.2). Applied to the raw score: 90.0 → A, 89.x → B.
GRADE_BANDS: tuple[tuple[float, str], ...] = (
    (90.0, "A"),
    (80.0, "B"),
    (70.0, "C"),
    (60.0, "D"),
    (0.0, "F"),
)

# The best grade a hard-gated run may receive.
HARD_GATE_CAP = "C"
_GRADE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}


def grade_for_score(score: float) -> str:
    """Map a 0–100 score to a letter using :data:`GRADE_BANDS`."""
    for threshold, letter in GRADE_BANDS:
        if score >= threshold:
            return letter
    return "F"


def _cap_grade(grade: str, cap: str) -> str:
    """Return the worse of ``grade`` and ``cap`` (never *improves* a grade)."""
    return grade if _GRADE_ORDER[grade] <= _GRADE_ORDER[cap] else cap


@dataclass
class ScoreResult:
    overall_score: float | None
    overall_grade: str
    hard_gate: str | None  # family that tripped the gate, or None
    effective_weights: dict[str, float]  # renormalized over measured families
    rubric_version: str = RUBRIC_VERSION


class Scorer:
    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or DEFAULT_WEIGHTS

    def score(self, families: dict[str, FamilyScore]) -> ScoreResult:
        measured = {
            name: fam
            for name, fam in families.items()
            if fam.measured and fam.score is not None
        }

        if not measured:
            return ScoreResult(
                overall_score=None,
                overall_grade="not-measured",
                hard_gate=None,
                effective_weights={},
            )

        # Renormalize weights across only the measured families (ADR-006).
        raw = {name: self.weights.get(name, 0.0) for name in measured}
        total_w = sum(raw.values())
        if total_w <= 0:  # families with no configured weight → equal weighting fallback
            effective = {name: 1.0 / len(measured) for name in measured}
        else:
            effective = {name: w / total_w for name, w in raw.items()}

        overall = sum(
            (measured[name].score or 0.0) * effective[name] for name in measured
        )
        grade = grade_for_score(overall)

        # Hard-gate: explicit trip, or any measured family at F.
        gate_family = self._find_hard_gate(measured)
        if gate_family is not None:
            grade = _cap_grade(grade, HARD_GATE_CAP)

        return ScoreResult(
            overall_score=overall,
            overall_grade=grade,
            hard_gate=gate_family,
            effective_weights=effective,
        )

    @staticmethod
    def _find_hard_gate(measured: dict[str, FamilyScore]) -> str | None:
        # Explicit gates first (contract break / critical security) in canonical order,
        # then any family that scored an F.
        for name, fam in measured.items():
            if fam.hard_gate_tripped:
                return name
        for name, fam in measured.items():
            if fam.grade == "F":
                return name
        return None
