"""Performance tests — pure metric math + engine invariants with a scripted fake factory
(TEST-PLAN §6 Performance, E2E-6). Never asserts absolute ms — only invariants."""

from __future__ import annotations

import pytest

from mcp_probe.config import ProbeConfig
from mcp_probe.connect.client import InvokeResult
from mcp_probe.engines.performance import PerformanceEngine
from mcp_probe.perf.load import classify_degradation, detect_leak, percentile

from .conftest import make_ctx

# -- pure metric helpers ------------------------------------------------------

def test_percentile_ordering_invariant():
    samples = [float(x) for x in range(1, 101)]
    p50, p95, p99 = percentile(samples, 50), percentile(samples, 95), percentile(samples, 99)
    assert p50 <= p95 <= p99  # the invariant E2E-6 asserts


def test_percentile_known_values():
    assert percentile([10, 20, 30, 40, 50], 50) == pytest.approx(30)
    assert percentile([], 95) == 0.0
    assert percentile([42], 99) == 42


def test_classify_degradation():
    assert classify_degradation(error_rate=0.0, latency_growth=2.0, crashed=False) == "graceful"
    assert classify_degradation(error_rate=0.3, latency_growth=1.0, crashed=False) == "clean-fail"
    assert classify_degradation(error_rate=0.9, latency_growth=5.0, crashed=True) == "crash"


def test_detect_leak():
    assert detect_leak([1, 2, 3, 4, 5]) is True  # monotonically rising
    assert detect_leak([5, 5, 5, 5]) is False  # flat
    assert detect_leak([3, 1, 4, 1]) is False  # noisy, no trend


# -- engine with a scripted fake factory --------------------------------------

class _FakeClient:
    def __init__(self, fail: bool) -> None:
        self._fail = fail

    async def call_tool(self, name, args):
        return InvokeResult(name, is_error=self._fail, content={"ok": not self._fail})

    async def close(self):
        return None


def _factory_that_fails_above(threshold: int):
    state = {"open": 0}

    async def factory():
        state["open"] += 1
        # Simulate a server that errors once many connections are open.
        return _FakeClient(fail=state["open"] > threshold)

    return factory


async def test_engine_reports_invariants_and_degradation():
    tools = [{"name": "get_x", "description": "read", "inputSchema": {"type": "object"},
              "annotations": {"readOnlyHint": True}}]
    ctx = make_ctx(tools, config=ProbeConfig(concurrency=8))
    # fails after 4 concurrent → clean-fail/crash territory
    engine = PerformanceEngine(factory=_factory_that_fails_above(4))
    fs = await engine.run(ctx)
    m = fs.metrics
    assert m["p50_ms"] <= m["p95_ms"] <= m["p99_ms"]  # ordering invariant
    assert m["degradation"] in ("graceful", "clean-fail", "crash")
    assert m["error_rate"] > 0  # some calls failed


async def test_engine_healthy_server_scores_well():
    tools = [{"name": "get_x", "description": "read", "inputSchema": {"type": "object"},
              "annotations": {"readOnlyHint": True}}]
    ctx = make_ctx(tools, config=ProbeConfig(concurrency=6))

    async def healthy():
        return _FakeClient(fail=False)

    fs = await PerformanceEngine(factory=healthy).run(ctx)
    assert fs.metrics["degradation"] == "graceful"
    assert fs.score >= 80


async def test_performance_not_measured_without_live():
    tools = [{"name": "get_x", "description": "read", "inputSchema": {"type": "object"}}]
    ctx = make_ctx(tools, client=None)  # static
    fs = await PerformanceEngine().run(ctx)
    assert fs.measured is False
