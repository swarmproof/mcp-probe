"""Performance engine ``[net]`` — concurrent load with real MCP semantics (REQ-P1–P6).

Reuses the concurrency-core shape (a Scheduler over a concurrency curve) but schedules
uniform MCP-client tasks issuing real ``call_tool`` over persistent connections — the gap
naive HTTP load tools (k6) can't fill. Reports p50/p95/p99, max stable concurrency, a
degradation grade, and connection-leak detection. Live-only: reported "not measured" in
static mode (ADR-006). Read-only: it drives a read-only tool, never a destructive one.
With ``--distributed N`` the curve is fanned across N concurrent workers for a fleet-wide
percentile picture that a single load loop can't reach (#51); 0/1 → single-host, unchanged.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from mcp_quality.contract.schema import synthesize_args
from mcp_quality.engines.base import EngineBase, clamp
from mcp_quality.models import FamilyScore, Finding, ProbeContext, Severity, ToolDef
from mcp_quality.perf.load import (
    ConcurrencyCurve,
    classify_degradation,
    detect_leak,
    percentile,
    run_distributed_load,
    run_load,
)

# p95 above this (ms) starts costing points.
P95_BUDGET_MS = 500.0


def _pick_read_only_tool(surface) -> ToolDef | None:
    """A representative tool to hammer — prefer an explicitly read-only one; never a
    destructive tool (we must not fire deletes 50× under load)."""
    from mcp_quality.engines.contract import _is_write

    read_only = [t for t in surface.tools if t.is_read_only]
    candidates = read_only or [t for t in surface.tools if not _is_write(t)]
    return candidates[0] if candidates else None


class PerformanceEngine(EngineBase):
    name = "performance"
    requires_live = True
    requires_llm = False
    deterministic = False  # live load timing varies run-to-run → reliability overlay reruns it

    def __init__(self, factory: Callable[[], Awaitable[Any]] | None = None) -> None:
        self._factory = factory

    async def run(self, ctx: ProbeContext) -> FamilyScore:
        if ctx.client is None and self._factory is None:
            return self.not_measured("requires a live server")

        tool = _pick_read_only_tool(ctx.surface)
        if tool is None:
            return self.not_measured("no read-only tool to load-test safely")

        args = synthesize_args(tool.input_schema, seed=getattr(ctx.config, "seed", 42))
        concurrency = int(getattr(ctx.config, "concurrency", 50))
        curve = ConcurrencyCurve(ramp_to=concurrency, ramp_steps=4, hold_iterations=3)
        factory = self._factory or self._default_factory(ctx)

        # #51: fan across N workers for a fleet-wide picture; 0/1 → single-host (unchanged).
        workers = int(getattr(ctx.config, "distributed", 0) or 0)
        per_worker: list[Any] | None = None
        if workers > 1:
            result, per_worker = await run_distributed_load(
                factory, tool.name, args, curve, workers=workers
            )
            effective_concurrency = concurrency * workers
        else:
            result = await run_load(factory, tool.name, args, curve)
            effective_concurrency = concurrency

        p50 = percentile(result.latencies_ms, 50)
        p95 = percentile(result.latencies_ms, 95)
        p99 = percentile(result.latencies_ms, 99)
        latency_growth = (p99 / p50) if p50 else 1.0
        degradation = classify_degradation(
            error_rate=result.error_rate, latency_growth=latency_growth, crashed=result.crashed
        )
        leak = detect_leak(result.connection_samples) and result.error_rate > 0.1

        findings = self._findings(tool.name, degradation, leak, result, effective_concurrency)
        score = self._score(p95, degradation, leak, result, effective_concurrency)

        from mcp_quality.scoring import grade_for_score

        metrics: dict[str, Any] = {
            "tool": tool.name,
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
            "p99_ms": round(p99, 1),
            "max_concurrency": result.max_stable_concurrency,
            "requested_concurrency": effective_concurrency,
            "error_rate": round(result.error_rate, 3),
            "degradation": degradation,
            "leak": leak,
            "calls": result.total,
            "workers": workers if workers > 1 else 1,
        }
        if per_worker is not None:
            metrics["per_worker"] = [
                {"max_stable": w.max_stable_concurrency, "error_rate": round(w.error_rate, 3),
                 "p95_ms": round(percentile(w.latencies_ms, 95), 1)}
                for w in per_worker
            ]
        return FamilyScore(
            family=self.name,
            score=score,
            grade=grade_for_score(score),
            findings=findings,
            metrics=metrics,
        )

    def _default_factory(self, ctx: ProbeContext) -> Callable[[], Awaitable[Any]]:
        from mcp_quality.connect.transport import connect

        async def factory() -> Any:
            client, _surface = await connect(ctx.config)
            return client

        return factory

    @staticmethod
    def _findings(tool, degradation, leak, result, concurrency) -> list[Finding]:
        findings: list[Finding] = []
        if degradation == "crash":
            findings.append(
                Finding(
                    family="performance",
                    code="P4-crash",
                    severity=Severity.HIGH,
                    tool=tool,
                    message=f"server crashed / dropped connections under load "
                    f"(stable only to ~{result.max_stable_concurrency} concurrent)",
                    remediation="add backpressure / connection limits; fail cleanly instead of crashing",
                )
            )
        elif degradation == "clean-fail":
            findings.append(
                Finding(
                    family="performance",
                    code="P4-clean-fail",
                    severity=Severity.MEDIUM,
                    tool=tool,
                    message=f"high error rate ({result.error_rate:.0%}) under load, but errors were clean",
                )
            )
        if leak:
            findings.append(
                Finding(
                    family="performance",
                    code="P5-leak",
                    severity=Severity.HIGH,
                    tool=tool,
                    message="connection/FD baseline rose under sustained load — likely a leak",
                    remediation="ensure connections/sessions are closed; check for unbounded pools",
                )
            )
        return findings

    @staticmethod
    def _score(p95, degradation, leak, result, concurrency) -> float:
        score = 100.0
        if degradation == "crash":
            score -= 45
        elif degradation == "clean-fail":
            score -= 20
        if leak:
            score -= 25
        if p95 > P95_BUDGET_MS:
            score -= min(25.0, (p95 - P95_BUDGET_MS) / P95_BUDGET_MS * 25.0)
        if result.max_stable_concurrency < concurrency:
            score -= 15 * (1 - result.max_stable_concurrency / max(1, concurrency))
        return clamp(score)
