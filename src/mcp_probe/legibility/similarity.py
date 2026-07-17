"""Offline disambiguation shortlist (REQ-L2, static-ok).

A cheap lexical (token-overlap / Jaccard-style) similarity over tool descriptions
pre-selects likely-confusable pairs. This (a) focuses the LLM probe's budget on pairs
that actually look alike and (b) gives ``static`` mode a heuristic-only confusion signal
when no model is available. A learned-embedding pass can replace this later without
changing the interface.
"""

from __future__ import annotations

import re

from mcp_probe.models import ServerSurface

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def confusable_shortlist(
    surface: ServerSurface, *, threshold: float = 0.4, top_k: int = 10
) -> list[tuple[str, str, float]]:
    """Return (tool_a, tool_b, similarity) pairs above ``threshold``, most-similar first.
    Similarity blends name and description overlap."""
    tools = surface.tools
    pairs: list[tuple[str, str, float]] = []
    for i in range(len(tools)):
        for j in range(i + 1, len(tools)):
            a, b = tools[i], tools[j]
            desc_sim = _jaccard(_tokens(a.description or ""), _tokens(b.description or ""))
            name_sim = _jaccard(_tokens(a.name), _tokens(b.name))
            sim = 0.75 * desc_sim + 0.25 * name_sim
            if sim >= threshold:
                pairs.append((a.name, b.name, round(sim, 3)))
    pairs.sort(key=lambda p: p[2], reverse=True)
    return pairs[:top_k]
