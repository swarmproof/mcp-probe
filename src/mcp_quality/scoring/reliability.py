"""The pass^k reliability overlay — consistency, not peak accuracy (#31).

A server that passes 9 runs in 10 is a 10% incident rate in production. Accuracy answers
"can it work?"; reliability answers "will it work *every* time?" — the number a team
gating deploys on actually cares about. This module holds the *pure math*: whether a
single family run passed, and the pass^k projection over K trials. The pipeline owns the
reruns (it needs the engines and a live client); everything here is a pure function of
counts, so it is trivially testable and deterministic.
"""

from __future__ import annotations

from typing import Any

from mcp_quality.models import FamilyScore

# A run "passes" if the family was measured and did not fail outright. F (including a
# hard-gate that caps the score into the F band) is the failing grade; A–D count as a
# pass for consistency purposes — the overlay measures *repeatability*, not peak grade.
PASS_GRADES = frozenset({"A", "B", "C", "D"})


def family_passed(fs: FamilyScore) -> bool:
    """True when this single run counts as a success for reliability accounting."""
    return fs.measured and fs.grade in PASS_GRADES


def pass_hat_k(passes: int, trials: int) -> float:
    """The pass^k projection: (empirical per-call pass rate) ** trials — the probability
    that K independent calls all succeed. Collapses to 1.0 iff every trial passed and
    drops sharply otherwise (0.8 over 5 trials → 0.33), which is the whole point: a family
    that flakes even once is not safe to depend on K times in a row."""
    if trials <= 0:
        return 0.0
    rate = passes / trials
    return rate**trials


def reliability_metrics(passes: int, trials: int) -> dict[str, Any]:
    """The per-family reliability record attached to ``FamilyScore.metrics['reliability']``."""
    rate = passes / trials if trials else 0.0
    return {
        "trials": trials,
        "passes": passes,
        "pass_rate": round(rate, 4),
        "pass_hat_k": round(pass_hat_k(passes, trials), 4),
    }
