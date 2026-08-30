"""The run pipeline — connect → discover → engines → score → report → gate.

This is the deterministic control flow ARCHITECTURE §1 describes. Engines run
concurrently (they are independent pure functions), then the Scorer and Renderer — the
only aggregators — turn their FamilyScores into a graded Report. The live transport is
imported lazily so ``static`` mode carries no SDK dependency (NFR-8).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from mcp_quality import RUBRIC_VERSION, __version__
from mcp_quality.config import LIVE_FAMILIES, ProbeConfig
from mcp_quality.connect import surface_from_dump
from mcp_quality.connect.client import MCPClientProtocol
from mcp_quality.engines import ENGINE_REGISTRY
from mcp_quality.exit_codes import ExitCode
from mcp_quality.models import FamilyScore, ProbeContext, Report, ServerSurface
from mcp_quality.scoring import Scorer
from mcp_quality.scoring.scorer import _GRADE_ORDER
from mcp_quality.snapshot import diff_against_baseline, load_snapshot
from mcp_quality.trace import TraceSink


@dataclass
class RunOutcome:
    report: Report
    exit_code: ExitCode


async def run_probe(
    config: ProbeConfig,
    *,
    client: MCPClientProtocol | None = None,
    surface: ServerSurface | None = None,
) -> RunOutcome:
    """Execute a full probe. Callers may inject a ``client`` and/or ``surface`` (tests,
    or a caller that already connected); otherwise the pipeline resolves them from config."""
    started = time.monotonic()
    trace = TraceSink(run_id=config.target or config.static_path or "static")

    owns_client = False
    if surface is None:
        if config.static_path:
            surface = surface_from_dump(config.static_path)
        else:
            client, surface = await _connect(config)
            owns_client = True

    reliability: dict[str, Any] | None = None
    try:
        families = await _run_engines(config, surface, client, trace)
        # Reliability overlay: rerun the nondeterministic families and attach pass^k. Runs
        # while the client is still open (live families rerun too), before the finally.
        if getattr(config, "reliability_k", 1) > 1:
            reliability = await _run_reliability_overlay(config, surface, client, trace, families)
    finally:
        if owns_client and client is not None:
            await client.close()

    # REQ-S6: fold Cisco readiness findings into Performance/Contract (reliability signals,
    # not security). Opt-in via --deep-security; best-effort; never changes the score.
    if getattr(config, "deep_security", False):
        _fold_readiness(config, families)

    scorer = Scorer()
    result = scorer.score(families)

    report = Report(
        overall_score=result.overall_score,
        overall_grade=result.overall_grade,
        families=families,
        surface=surface,
        rubric_version=RUBRIC_VERSION,
        tool_version=__version__,
        weights=result.effective_weights,
        hard_gate=result.hard_gate,
        meta={
            "elapsed_s": round(time.monotonic() - started, 3),
            "mode": "static" if client is None else "live",
            "families_run": sorted(families),
            **({"reliability": reliability} if reliability is not None else {}),
        },
    )

    _apply_snapshot(config, report, surface, families)
    exit_code = _decide_exit(config, report)
    return RunOutcome(report=report, exit_code=exit_code)


async def _connect(config: ProbeConfig) -> tuple[MCPClientProtocol, ServerSurface]:
    # Lazy import: pulls in the MCP SDK only for live runs.
    from mcp_quality.connect.transport import connect

    return await connect(config)


def _make_ctx(
    config: ProbeConfig,
    surface: ServerSurface,
    client: MCPClientProtocol | None,
    trace: TraceSink,
    *,
    seed: int,
) -> ProbeContext:
    # Build the legibility model provider from config (None → lints-only legibility). The
    # seed is threaded here so the reliability overlay can vary it across trials.
    from mcp_quality.legibility.model import build_model

    return ProbeContext(
        surface=surface,
        config=config,
        client=client,
        model=build_model(getattr(config, "model", None), seed=seed),
        trace=trace,
    )


async def _run_engine_once(
    name: str, ctx: ProbeContext, client: MCPClientProtocol | None
) -> FamilyScore:
    """Run a single engine, degrading to not-measured rather than aborting the run."""
    engine_cls = ENGINE_REGISTRY.get(name)
    if engine_cls is None:
        return FamilyScore.not_measured(name, "engine not available in this build")
    engine = engine_cls()
    # static mode: a live-only family can't be scored — report not-measured (ADR-006).
    if client is None and name in LIVE_FAMILIES and engine.requires_live:
        return FamilyScore.not_measured(name, "requires a live server (static mode)")
    # LLM families decide for themselves whether they can run without a model — the
    # Legibility engine still runs its offline lints and reports the behavioural part
    # as partial rather than blanking the whole family.
    try:
        return await engine.run(ctx)
    except Exception as exc:  # an engine crash degrades to not-measured, never aborts the run
        return FamilyScore.not_measured(name, f"engine error: {exc!s}")


async def _run_engines(
    config: ProbeConfig,
    surface: ServerSurface,
    client: MCPClientProtocol | None,
    trace: TraceSink,
) -> dict[str, FamilyScore]:
    ctx = _make_ctx(config, surface, client, trace, seed=getattr(config, "seed", 42))

    async def run_one(name: str) -> tuple[str, FamilyScore]:
        return name, await _run_engine_once(name, ctx, client)

    pairs = await asyncio.gather(*(run_one(name) for name in config.families))
    return dict(pairs)


async def _run_reliability_overlay(
    config: ProbeConfig,
    surface: ServerSurface,
    client: MCPClientProtocol | None,
    trace: TraceSink,
    families: dict[str, FamilyScore],
) -> dict[str, Any]:
    """Rerun the nondeterministic, measured families K times and attach pass^k to each.

    Deterministic families short-circuit to reliability 1.0/0.0 with no extra runs (the
    whole fast path costs nothing). The portfolio reliability is the product of the
    per-family rates: a full run only passes if *every* measured family passes.
    """
    from mcp_quality.scoring.reliability import family_passed, reliability_metrics

    k = config.reliability_k
    per_family: dict[str, dict[str, Any]] = {}
    for name, fs in families.items():
        if not fs.measured:
            continue
        engine_cls = ENGINE_REGISTRY.get(name)
        deterministic = getattr(engine_cls, "deterministic", True) if engine_cls else True
        passes = int(family_passed(fs))  # the primary run counts as trial #1
        if deterministic:
            metrics = reliability_metrics(passes, 1)
        else:
            for i in range(1, k):  # k-1 more trials, each with a fresh seed
                ctx = _make_ctx(config, surface, client, trace, seed=getattr(config, "seed", 42) + i)
                trial = await _run_engine_once(name, ctx, client)
                passes += int(family_passed(trial))
            metrics = reliability_metrics(passes, k)
        fs.metrics["reliability"] = metrics
        per_family[name] = metrics

    overall_rate = 1.0
    overall_phk = 1.0
    for m in per_family.values():
        overall_rate *= float(m["pass_rate"])
        overall_phk *= float(m["pass_hat_k"])
    return {
        "k": k,
        "overall_pass_rate": round(overall_rate, 4),
        "overall_pass_hat_k": round(overall_phk, 4),
        "per_family": {n: m["pass_hat_k"] for n, m in per_family.items()},
    }


def _apply_snapshot(
    config: ProbeConfig,
    report: Report,
    surface: ServerSurface,
    families: dict[str, FamilyScore],
) -> None:
    baseline = load_snapshot(config.snapshot_path)
    if baseline is None:
        return
    diff = diff_against_baseline(baseline, surface, families)
    report.regression = diff.to_dict()


def _decide_exit(config: ProbeConfig, report: Report) -> ExitCode:
    # Gate 1: overall grade floor.
    if config.fail_under and report.overall_grade != "not-measured":
        if _GRADE_ORDER.get(report.overall_grade, 0) < _GRADE_ORDER.get(config.fail_under, 0):
            return ExitCode.GATE_FAILURE
    # Gate 2: per-family floors.
    for family, floor in config.fail_under_family.items():
        fam = report.families.get(family)
        if fam and fam.measured and _GRADE_ORDER.get(fam.grade, 0) < _GRADE_ORDER.get(floor, 0):
            return ExitCode.GATE_FAILURE
    # Gate 3: regressions vs snapshot — score drop, broken contract, removed tool, or a
    # capability change (scope expansion / breaking schema) that defeats a prior approval.
    if config.no_regressions and report.regression is not None:
        reg = report.regression
        broke = bool(reg.get("broken_contracts"))
        dropped = any(v < 0 for v in reg.get("score_delta", {}).values())
        drift = bool(reg.get("capability_changes")) or bool(reg.get("removed_tools"))
        if broke or dropped or drift:
            return ExitCode.GATE_FAILURE
    return ExitCode.OK


def _fold_readiness(config: ProbeConfig, families: dict[str, FamilyScore]) -> None:
    """Run readiness adapters and distribute their family-tagged findings into the matching
    (measured) FamilyScore. Findings are attached for the report; scores are unchanged."""
    from mcp_quality.security.adapters import DEFAULT_READINESS_ADAPTERS

    target = getattr(config, "target", "") or getattr(config, "static_path", "") or ""
    for adapter in DEFAULT_READINESS_ADAPTERS:
        if not adapter.available():
            continue
        for finding in adapter.scan(target):
            fam = families.get(finding.family)
            if fam is not None and fam.measured:
                fam.findings.append(finding)
                fam.metrics.setdefault("readiness_findings", 0)
                fam.metrics["readiness_findings"] += 1


def gather_metrics(report: Report) -> dict[str, Any]:
    """Convenience for the leaderboard tooling (launch content)."""
    return {name: fam.metrics for name, fam in report.families.items()}
