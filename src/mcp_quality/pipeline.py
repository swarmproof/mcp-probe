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

    try:
        families = await _run_engines(config, surface, client, trace)
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
        },
    )

    _apply_snapshot(config, report, surface, families)
    exit_code = _decide_exit(config, report)
    return RunOutcome(report=report, exit_code=exit_code)


async def _connect(config: ProbeConfig) -> tuple[MCPClientProtocol, ServerSurface]:
    # Lazy import: pulls in the MCP SDK only for live runs.
    from mcp_quality.connect.transport import connect

    return await connect(config)


async def _run_engines(
    config: ProbeConfig,
    surface: ServerSurface,
    client: MCPClientProtocol | None,
    trace: TraceSink,
) -> dict[str, FamilyScore]:
    # Build the legibility model provider from config (None → lints-only legibility).
    from mcp_quality.legibility.model import build_model

    model = build_model(getattr(config, "model", None), seed=getattr(config, "seed", 42))

    ctx = ProbeContext(
        surface=surface,
        config=config,
        client=client,
        model=model,
        trace=trace,
    )

    async def run_one(name: str) -> tuple[str, FamilyScore]:
        engine_cls = ENGINE_REGISTRY.get(name)
        if engine_cls is None:
            return name, FamilyScore.not_measured(name, "engine not available in this build")
        engine = engine_cls()
        # static mode: a live-only family can't be scored — report not-measured (ADR-006).
        if client is None and name in LIVE_FAMILIES and engine.requires_live:
            return name, FamilyScore.not_measured(name, "requires a live server (static mode)")
        # LLM families decide for themselves whether they can run without a model — the
        # Legibility engine still runs its offline lints and reports the behavioural part
        # as partial rather than blanking the whole family.
        try:
            return name, await engine.run(ctx)
        except Exception as exc:  # an engine crash degrades to not-measured, never aborts the run
            return name, FamilyScore.not_measured(name, f"engine error: {exc!s}")

    pairs = await asyncio.gather(*(run_one(name) for name in config.families))
    return dict(pairs)


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
