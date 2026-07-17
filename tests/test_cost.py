"""Cost engine component tests — leave-one-out attribution, the score curve anchors,
bloat findings, deterministic offline counting (TEST-PLAN §6 Cost, REQ-$1/$2)."""

from __future__ import annotations

import pytest

from mcp_probe.config import ProbeConfig
from mcp_probe.engines.cost import cost_score
from mcp_probe.tokens import HeuristicCounter, serialize_toolset

from .conftest import make_ctx


@pytest.mark.parametrize(
    "tokens,expected,tol",
    [(0, 100, 0), (2000, 100, 0), (8140, 71, 2), (55000, 8, 3)],
)
def test_cost_curve_anchors(tokens, expected, tol):
    # Anchored to ARCHITECTURE §7 (8.1k ≈ 71) and README (55k → single digits).
    assert cost_score(tokens) == pytest.approx(expected, abs=tol)


def test_cost_curve_monotonic_decreasing():
    scores = [cost_score(t) for t in range(2000, 60000, 2000)]
    assert all(a >= b for a, b in zip(scores, scores[1:], strict=False))


async def test_leave_one_out_attribution_is_deterministic():
    tools = [
        {"name": "a", "description": "short", "inputSchema": {"type": "object"}},
        {"name": "b", "description": "word " * 200, "inputSchema": {"type": "object"}},
    ]
    ctx = make_ctx(tools, config=ProbeConfig())
    from mcp_probe.engines.cost import CostEngine

    fs1 = await CostEngine(counter=HeuristicCounter()).run(ctx)
    fs2 = await CostEngine(counter=HeuristicCounter()).run(ctx)
    assert fs1.metrics["per_tool_tokens"] == fs2.metrics["per_tool_tokens"]  # deterministic
    # b is the verbose one → heavier marginal weight than a.
    per = fs1.metrics["per_tool_tokens"]
    assert per["b"] > per["a"]


async def test_bloat_finding_emitted():
    tools = [
        {"name": f"t{i}", "description": "word " * 700, "inputSchema": {"type": "object"}}
        for i in range(5)
    ]
    ctx = make_ctx(tools)
    from mcp_probe.engines.cost import CostEngine

    fs = await CostEngine(counter=HeuristicCounter()).run(ctx)
    assert any(f.code == "$2-bloat" for f in fs.findings)
    assert fs.score < 100


def test_heuristic_counter_deterministic():
    assert serialize_toolset(()) == "[]"
    c = HeuristicCounter()
    assert c.count("hello world foo") == c.count("hello world foo")
