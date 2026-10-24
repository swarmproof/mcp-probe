"""Cross-host distributed load tests (issue #74) — coordinator/worker fleet, invariants only."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mcp_quality.config import ProbeConfig
from mcp_quality.connect.client import InvokeResult
from mcp_quality.engines.performance import PerformanceEngine
from mcp_quality.perf.distributed import run_coordinated_load
from mcp_quality.perf.load import LoadResult, percentile

from .conftest import make_ctx

_RO = [{"name": "get_x", "description": "read", "inputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True}}]


def _scripted(latencies, max_stable=4) -> LoadResult:
    return LoadResult(latencies_ms=list(latencies), total=len(latencies), errors=0,
                      connection_samples=[2, 4], max_stable_concurrency=max_stable)


def _launcher(result_for):
    async def launcher(index, job):
        return result_for(index)
    return launcher


# -- serialization -------------------------------------------------------------

def test_loadresult_roundtrip():
    r = LoadResult(latencies_ms=[1.5, 2.5], errors=1, total=3, crashed=True,
                   connection_samples=[2, 4], max_stable_concurrency=4, workers=2)
    assert LoadResult.from_dict(r.to_dict()).to_dict() == r.to_dict()


# -- coordinator (fake launcher, no subprocess) --------------------------------

async def test_coordinator_aggregates_fleet():
    agg, per = await run_coordinated_load(
        {"target": "x", "tool": "t", "args": {}, "curve": {"ramp_to": 4}}, 3,
        launcher=_launcher(lambda i: _scripted([10.0, 20.0, 30.0], max_stable=4)))
    assert agg.workers == 3 and len(per) == 3
    assert agg.total == 9  # 3 workers × 3 calls, pooled
    assert agg.max_stable_concurrency == 12  # fleet sustained = sum of per-worker
    p50, p95, p99 = (percentile(agg.latencies_ms, p) for p in (50, 95, 99))
    assert p50 <= p95 <= p99  # invariant — never an absolute-ms assertion


async def test_coordinator_drops_failed_workers():
    agg, per = await run_coordinated_load(
        {"curve": {}}, 3, launcher=_launcher(lambda i: None if i == 1 else _scripted([10.0])))
    assert len(per) == 2 and agg.workers == 2  # the failed worker drops out


# -- engine integration --------------------------------------------------------

async def test_engine_process_fleet_metrics():
    ctx = make_ctx(_RO, config=ProbeConfig(concurrency=4, distributed_workers=3))
    eng = PerformanceEngine(launcher=_launcher(lambda i: _scripted([5.0, 6.0, 7.0], max_stable=4)))
    fs = await eng.run(ctx)
    m = fs.metrics
    assert m["worker_mode"] == "process" and m["workers"] == 3
    assert m["requested_concurrency"] == 12  # concurrency × surviving workers
    assert m["p50_ms"] <= m["p95_ms"] <= m["p99_ms"]


async def test_engine_falls_back_when_all_workers_fail():
    class _FakeClient:
        async def call_tool(self, name, args):
            return InvokeResult(name, is_error=False, content={"ok": True})

        async def close(self):
            return None

    async def factory():
        return _FakeClient()

    ctx = make_ctx(_RO, config=ProbeConfig(concurrency=4, distributed_workers=3))
    # every worker fails → honest fallback to a single in-process run via the factory
    fs = await PerformanceEngine(factory=factory, launcher=_launcher(lambda i: None)).run(ctx)
    assert fs.metrics["worker_mode"] == "single" and fs.metrics["workers"] == 1


# -- real multi-process e2e (spawns actual worker subprocesses) -----------------

@pytest.mark.e2e
async def test_e2e_real_worker_processes_against_good_server():
    server = Path(__file__).parent / "servers" / "good_server.py"
    job = {
        "target": f"{sys.executable} {server}",
        "transport": "stdio",
        "tool": "list_cities",
        "args": {},
        "curve": {"ramp_to": 3, "ramp_steps": 1, "hold_iterations": 1},
    }
    # default launcher → real `python -m mcp_quality.perf.worker` subprocesses
    agg, per = await run_coordinated_load(job, 2)
    assert len(per) == 2  # both worker processes reported
    assert agg.total > 0
    assert percentile(agg.latencies_ms, 50) <= percentile(agg.latencies_ms, 99)
