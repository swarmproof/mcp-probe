"""Distributed load tests (issue #51) — fleet aggregation, invariants only, never ms."""

from __future__ import annotations

from mcp_quality.config import ProbeConfig
from mcp_quality.connect.client import InvokeResult
from mcp_quality.engines.performance import PerformanceEngine
from mcp_quality.perf.load import (
    ConcurrencyCurve,
    LoadResult,
    aggregate_results,
    percentile,
    run_distributed_load,
)

from .conftest import make_ctx

_RO = [{"name": "get_x", "description": "read", "inputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True}}]


class _FakeClient:
    def __init__(self, fail: bool = False) -> None:
        self._fail = fail

    async def call_tool(self, name, args):
        return InvokeResult(name, is_error=self._fail, content={"ok": True})

    async def close(self):
        return None


async def _healthy_factory():
    return _FakeClient(fail=False)


# -- pure aggregation ----------------------------------------------------------

def test_aggregate_pools_latencies_and_sums_counts():
    a = LoadResult(latencies_ms=[10, 20], errors=1, total=3, max_stable_concurrency=5)
    b = LoadResult(latencies_ms=[30], errors=0, total=2, max_stable_concurrency=4)
    agg = aggregate_results([a, b])
    assert agg.workers == 2
    assert sorted(agg.latencies_ms) == [10, 20, 30]
    assert agg.errors == 1 and agg.total == 5
    assert agg.max_stable_concurrency == 9  # fleet sustained = sum of per-worker stable


def test_aggregate_crash_is_any_worker():
    agg = aggregate_results([LoadResult(), LoadResult(crashed=True)])
    assert agg.crashed is True


def test_aggregate_connection_samples_summed_per_stage():
    a = LoadResult(connection_samples=[2, 4, 6])
    b = LoadResult(connection_samples=[1, 2, 3])
    assert aggregate_results([a, b]).connection_samples == [3, 6, 9]


# -- distributed driver --------------------------------------------------------

async def test_distributed_drives_all_workers_and_preserves_ordering():
    curve = ConcurrencyCurve(ramp_to=4, ramp_steps=2, hold_iterations=1)
    agg, per_worker = await run_distributed_load(_healthy_factory, "get_x", {}, curve, workers=3)
    assert agg.workers == 3 and len(per_worker) == 3
    # fleet did 3× the calls of a single worker
    assert agg.total == sum(w.total for w in per_worker)
    p50, p95, p99 = (percentile(agg.latencies_ms, p) for p in (50, 95, 99))
    assert p50 <= p95 <= p99  # the invariant — never an absolute-ms assertion


# -- engine integration --------------------------------------------------------

async def test_engine_distributed_reports_fleet_metrics():
    ctx = make_ctx(_RO, config=ProbeConfig(concurrency=4, distributed=3))
    fs = await PerformanceEngine(factory=_healthy_factory).run(ctx)
    m = fs.metrics
    assert m["workers"] == 3
    assert len(m["per_worker"]) == 3
    assert m["requested_concurrency"] == 12  # concurrency × workers
    assert m["p50_ms"] <= m["p95_ms"] <= m["p99_ms"]
    assert m["degradation"] == "graceful"  # healthy fleet


async def test_engine_single_host_fallback_unchanged():
    ctx = make_ctx(_RO, config=ProbeConfig(concurrency=4))  # distributed defaults to 0
    fs = await PerformanceEngine(factory=_healthy_factory).run(ctx)
    assert fs.metrics["workers"] == 1
    assert "per_worker" not in fs.metrics
    assert fs.metrics["requested_concurrency"] == 4
