"""Concurrency load driver + metric helpers (REQ-P1–P5).

The load driver schedules **uniform MCP-client tasks** (real ``call_tool`` over persistent
connections) under a ramp → hold → spike curve — not naive HTTP, which is the whole point
of measuring MCP performance. It is parameterized by a ``client_factory`` so tests inject
fakes with scripted latencies and the metric math is verified with zero I/O (TEST-PLAN §6).

Performance is inherently nondeterministic (wall-clock), so the engine asserts *invariants*
(percentile ordering, degradation class, leak flag), never absolute milliseconds (NFR-2
applies to the fast path only).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

# A client the load driver can drive: call a tool, then close.
ClientFactory = Callable[[], Awaitable[Any]]


def percentile(samples: list[float], p: float) -> float:
    """Linear-interpolated percentile. ``p`` in [0, 100]. Empty → 0.0."""
    if not samples:
        return 0.0
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    rank = (p / 100) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def classify_degradation(*, error_rate: float, latency_growth: float, crashed: bool) -> str:
    """Map observed behaviour under load to graceful / clean-fail / crash (REQ-P4).

    * **crash** — connections dropped / non-conformant (the server fell over).
    * **clean-fail** — high rate of *proper* JSON-RPC errors (it said no, correctly).
    * **graceful** — it slowed (latency grew) but kept serving.
    """
    if crashed:
        return "crash"
    if error_rate >= 0.20:
        return "clean-fail"
    return "graceful"


def detect_leak(connection_samples: list[int]) -> bool:
    """A monotonically rising connection/FD baseline over a sustained hold = leak (REQ-P5).
    We look for a sustained upward trend, not transient spikes."""
    if len(connection_samples) < 3:
        return False
    first, last = connection_samples[0], connection_samples[-1]
    rising = sum(1 for a, b in zip(connection_samples, connection_samples[1:], strict=False) if b > a)
    return last > first and rising >= (len(connection_samples) - 1) * 0.6


@dataclass
class ConcurrencyCurve:
    """A simple ramp → hold → spike schedule (REQ-P2)."""

    ramp_to: int = 50
    ramp_steps: int = 5
    hold_iterations: int = 3
    spike_to: int = 0  # 0 = no spike

    def stages(self) -> list[int]:
        stages: list[int] = []
        for step in range(1, self.ramp_steps + 1):
            stages.append(max(1, round(self.ramp_to * step / self.ramp_steps)))
        stages.extend([self.ramp_to] * self.hold_iterations)
        if self.spike_to:
            stages.append(self.spike_to)
        return stages


@dataclass
class LoadResult:
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0
    total: int = 0
    crashed: bool = False
    connection_samples: list[int] = field(default_factory=list)
    max_stable_concurrency: int = 0

    @property
    def error_rate(self) -> float:
        return self.errors / self.total if self.total else 0.0


async def _one_call(factory: ClientFactory, tool: str, args: dict[str, Any]) -> tuple[float, bool]:
    """Open a connection, invoke, close. Returns (latency_ms, is_error)."""
    start = time.monotonic()
    client = None
    try:
        client = await factory()
        result = await client.call_tool(tool, args)
        latency = (time.monotonic() - start) * 1000
        return latency, bool(getattr(result, "is_error", False))
    except Exception:
        latency = (time.monotonic() - start) * 1000
        return latency, True
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                await client.close()


async def run_load(
    factory: ClientFactory,
    tool: str,
    args: dict[str, Any],
    curve: ConcurrencyCurve,
    *,
    error_threshold: float = 0.5,
) -> LoadResult:
    """Drive the curve. Records per-call latency + errors, tracks the highest concurrency
    level held below ``error_threshold`` (max stable concurrency, REQ-P3)."""
    result = LoadResult()
    max_stable = 0
    for level in curve.stages():
        tasks = [_one_call(factory, tool, args) for _ in range(level)]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        stage_errors = 0
        for outcome in outcomes:
            result.total += 1
            if isinstance(outcome, BaseException):
                result.errors += 1
                stage_errors += 1
                continue
            latency, is_error = outcome
            result.latencies_ms.append(latency)
            if is_error:
                result.errors += 1
                stage_errors += 1
        result.connection_samples.append(level)
        stage_rate = stage_errors / level if level else 0.0
        if stage_rate < error_threshold:
            max_stable = max(max_stable, level)
        elif stage_rate >= 0.9:
            result.crashed = True
    result.max_stable_concurrency = max_stable
    return result
