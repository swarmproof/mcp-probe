"""Cost engine component tests — leave-one-out attribution, the score curve anchors,
bloat findings, deterministic offline counting (TEST-PLAN §6 Cost, REQ-$1/$2)."""

from __future__ import annotations

import pytest

from mcp_quality.config import ProbeConfig
from mcp_quality.engines.cost import cost_score
from mcp_quality.tokens import HeuristicCounter, serialize_toolset

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
    from mcp_quality.engines.cost import CostEngine

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
    from mcp_quality.engines.cost import CostEngine

    fs = await CostEngine(counter=HeuristicCounter()).run(ctx)
    assert any(f.code == "$2-bloat" for f in fs.findings)
    assert fs.score < 100


def test_heuristic_counter_deterministic():
    assert serialize_toolset(()) == "[]"
    c = HeuristicCounter()
    assert c.count("hello world foo") == c.count("hello world foo")


async def test_authoritative_token_count_opt_in(monkeypatch):
    # With token_model set and the Anthropic call "succeeding" (monkeypatched), the engine
    # uses the authoritative total, clears the estimate note, and rescales per-tool weights.
    import mcp_quality.engines.cost as cost_mod

    monkeypatch.setattr(cost_mod, "anthropic_toolset_tokens", lambda tools, model: 9999)
    tools = [
        {"name": "a", "description": "short", "inputSchema": {"type": "object"}},
        {"name": "b", "description": "word " * 100, "inputSchema": {"type": "object"}},
    ]
    ctx = make_ctx(tools, config=ProbeConfig(token_model="anthropic:claude-sonnet-5"))
    fs = await cost_mod.CostEngine(counter=HeuristicCounter()).run(ctx)
    assert fs.metrics["toolset_tokens"] == 9999
    assert fs.metrics["counter"].startswith("anthropic:count_tokens/")
    assert fs.metrics["counter_note"] is None  # authoritative → no estimate caveat
    # per-tool weights rescaled to the authoritative total, still ordered b > a
    per = fs.metrics["per_tool_tokens"]
    assert per["b"] > per["a"]


async def test_falls_back_to_estimate_when_authoritative_unavailable(monkeypatch):
    # token_model set but the call returns None (no key / failure) → offline estimate, labeled.
    import mcp_quality.engines.cost as cost_mod

    monkeypatch.setattr(cost_mod, "anthropic_toolset_tokens", lambda tools, model: None)
    tools = [{"name": "a", "description": "x", "inputSchema": {"type": "object"}}]
    ctx = make_ctx(tools, config=ProbeConfig(token_model="anthropic:claude-sonnet-5"))
    fs = await cost_mod.CostEngine(counter=HeuristicCounter()).run(ctx)
    assert fs.metrics["counter"] == "heuristic"
    assert "estimate" in fs.metrics["counter_note"]


async def test_remediation_hint_on_heavy_toolset():
    # A big toolset should emit the $6 lazy-loading hint with a projected saving (REQ-$6).
    tools = [
        {"name": f"t{i}", "description": "word " * 200, "inputSchema": {"type": "object"}}
        for i in range(40)
    ]
    from mcp_quality.engines.cost import CostEngine

    fs = await CostEngine(counter=HeuristicCounter()).run(make_ctx(tools))
    hint = next((f for f in fs.findings if f.code == "$6-remediation"), None)
    assert hint is not None
    assert hint.evidence["deferrable_tokens"] > 0
    assert "Tool Search" in hint.message


async def test_no_remediation_hint_on_lean_toolset():
    tools = [{"name": "get_x", "description": "Return x.", "inputSchema": {"type": "object"}}]
    from mcp_quality.engines.cost import CostEngine

    fs = await CostEngine(counter=HeuristicCounter()).run(make_ctx(tools))
    assert not any(f.code == "$6-remediation" for f in fs.findings)


async def test_response_bloat_not_measured_by_default():
    tools = [{"name": "get_x", "description": "Return x.", "inputSchema": {"type": "object"}}]
    from mcp_quality.engines.cost import CostEngine

    fs = await CostEngine(counter=HeuristicCounter()).run(make_ctx(tools))
    assert fs.metrics["response_tokens"] == "not measured"


async def test_response_bloat_sampled_when_opted_in():
    from mcp_quality.connect.client import FakeClient, InvokeResult
    from mcp_quality.engines.cost import CostEngine

    tools = [
        {"name": "get_small", "description": "read", "inputSchema": {"type": "object"},
         "annotations": {"readOnlyHint": True}},
        {"name": "get_big", "description": "read",
         "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
         "annotations": {"readOnlyHint": True}},
    ]
    client = FakeClient(results={
        "get_small": InvokeResult("get_small", False, content={"ok": 1}),
        "get_big": InvokeResult("get_big", False, content=[], structured={"rows": ["word " * 400] * 5}),
    })
    ctx = make_ctx(tools, client=client, config=ProbeConfig(response_bloat=True))
    fs = await CostEngine(counter=HeuristicCounter()).run(ctx)
    rt = fs.metrics["response_tokens"]
    assert isinstance(rt, dict) and rt["get_big"] > rt["get_small"]
    # get_big has a `limit` param → boundable → $5, not $7
    assert any(f.code == "$5-response-bloat" and f.tool == "get_big" for f in fs.findings)


async def test_unbounded_big_response_flags_no_pagination():
    # #26: a big response with NO pagination param is worse → $7-no-pagination.
    from mcp_quality.connect.client import FakeClient, InvokeResult
    from mcp_quality.engines.cost import CostEngine

    tools = [{"name": "list_all", "description": "read", "inputSchema": {"type": "object"},
              "annotations": {"readOnlyHint": True}}]
    client = FakeClient(results={
        "list_all": InvokeResult("list_all", False, content=[], structured={"rows": ["word " * 400] * 6}),
    })
    ctx = make_ctx(tools, client=client, config=ProbeConfig(response_bloat=True))
    fs = await CostEngine(counter=HeuristicCounter()).run(ctx)
    f = next((x for x in fs.findings if x.code == "$7-no-pagination"), None)
    assert f is not None and f.tool == "list_all"
    assert f.evidence["boundable"] is False
    assert "projected saving" in f.remediation


async def test_context_efficiency_metric_static():
    from mcp_quality.engines.cost import CostEngine

    tools = [{"name": "get_x", "description": "Return x.", "inputSchema": {"type": "object"}}]
    fs = await CostEngine(counter=HeuristicCounter()).run(make_ctx(tools))
    ce = fs.metrics["context_efficiency"]
    assert ce["response_tokens"] == "not measured"
    assert ce["context_footprint"] == ce["schema_tokens"] == fs.metrics["toolset_tokens"]


async def test_context_efficiency_includes_response_when_sampled():
    from mcp_quality.connect.client import FakeClient, InvokeResult
    from mcp_quality.engines.cost import CostEngine

    tools = [{"name": "get_x", "description": "read", "inputSchema": {"type": "object"},
              "annotations": {"readOnlyHint": True}}]
    client = FakeClient(results={"get_x": InvokeResult("get_x", False, content=[], structured={"v": "word " * 50})})
    ctx = make_ctx(tools, client=client, config=ProbeConfig(response_bloat=True))
    fs = await CostEngine(counter=HeuristicCounter()).run(ctx)
    ce = fs.metrics["context_efficiency"]
    assert isinstance(ce["response_tokens"], dict)
    assert ce["context_footprint"] == ce["schema_tokens"] + ce["response_tokens"]["mean"]
