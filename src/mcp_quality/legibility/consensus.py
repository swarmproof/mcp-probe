"""Multi-model consensus (#50) — agreement across a model panel as a confidence signal.

A single model's tool-selection reflects that model's quirks. When several models
independently pick the *same* tool for a goal, the selection score is trustworthy; when
they split, the surface is genuinely ambiguous — a stronger signal than one model's
confusion. This module is pure: it takes each model's per-goal picks and returns an
agreement report. The engine owns running the panel (and caching per model); the math here
is deterministic and testable with no model at all.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def agreement_per_goal(picks_per_model: list[list[str]]) -> list[float]:
    """Per goal, the fraction of models that agree with the modal (most-common) pick.
    1.0 = unanimous; with k models the floor is 1/k. Aligns picks by goal index."""
    if not picks_per_model:
        return []
    n_models = len(picks_per_model)
    n_goals = min(len(p) for p in picks_per_model)
    out: list[float] = []
    for i in range(n_goals):
        picks = [pm[i] for pm in picks_per_model]
        modal_count = Counter(picks).most_common(1)[0][1]
        out.append(modal_count / n_models)
    return out


def consensus_report(
    model_ids: list[str],
    picks_per_model: list[list[str]],
    goals: list[tuple[str, str]],
) -> dict[str, Any]:
    """Aggregate panel agreement: mean agreement, disagreement rate, and the most divergent
    goals (where the panel split on which tool wins)."""
    agr = agreement_per_goal(picks_per_model)
    mean_agreement = sum(agr) / len(agr) if agr else 1.0
    disagreement_rate = (sum(1 for a in agr if a < 1.0) / len(agr)) if agr else 0.0

    divergent: list[dict[str, Any]] = []
    for i, a in enumerate(agr):
        if a < 1.0:
            picks = [pm[i] for pm in picks_per_model]
            divergent.append({
                "goal": goals[i][0],
                "golden": goals[i][1],
                "picks": dict(Counter(picks)),
                "agreement": round(a, 3),
            })
    divergent.sort(key=lambda d: d["agreement"])  # worst (lowest agreement) first
    return {
        "models": list(model_ids),
        "goals_compared": len(agr),
        "mean_agreement": round(mean_agreement, 3),
        "disagreement_rate": round(disagreement_rate, 3),
        "divergent_goals": divergent[:5],
    }
