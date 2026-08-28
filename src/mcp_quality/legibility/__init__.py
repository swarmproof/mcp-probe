"""Legibility — the differentiator: do agents pick the *right* tool? (ARCHITECTURE §5)

Design goals: credible (LiveMCP-101-style single-decision probe), deterministic (seeded +
cached), cheap (small local models, off the CI-critical path), actionable (proposes
rewrites). The offline lints and lexical disambiguation run with no model; the behavioural
comprehension score needs a small model but is opt-in.
"""

from mcp_quality.legibility.lints import lint_descriptions
from mcp_quality.legibility.model import ModelProvider, StubModel, build_model
from mcp_quality.legibility.similarity import confusable_shortlist

__all__ = [
    "lint_descriptions",
    "ModelProvider",
    "StubModel",
    "build_model",
    "confusable_shortlist",
]
