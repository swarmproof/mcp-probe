"""Shared engine scaffolding — the common shape and small scoring helpers.

Engines subclass :class:`EngineBase` for the boilerplate (name/flags, trace helper,
not-measured shortcut) but the real contract is the :class:`~mcp_probe.models.CheckEngine`
Protocol: ``async def run(ctx) -> FamilyScore``. Nothing here holds mutable run state —
an engine instance is cheap and stateless, constructed per run.
"""

from __future__ import annotations

from mcp_probe.models import FamilyScore, Finding, ProbeContext, Severity


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


# Severity → points subtracted from a 100 baseline. Used by the penalty-style families
# (Security-lite, description lints) so scoring is consistent across engines.
_SEVERITY_PENALTY: dict[Severity, float] = {
    Severity.INFO: 0.0,
    Severity.LOW: 3.0,
    Severity.MEDIUM: 8.0,
    Severity.HIGH: 20.0,
    Severity.CRITICAL: 40.0,
}


def penalty_score(findings: list[Finding], base: float = 100.0) -> float:
    """``base`` minus the severity-weighted sum of findings, clamped to [0, 100]."""
    deduction = sum(_SEVERITY_PENALTY.get(f.severity, 0.0) for f in findings)
    return clamp(base - deduction)


class EngineBase:
    """Convenience base. Concrete engines set the three class attrs and implement ``run``."""

    name: str = "base"
    requires_live: bool = False
    requires_llm: bool = False

    async def run(self, ctx: ProbeContext) -> FamilyScore:  # pragma: no cover - abstract
        raise NotImplementedError

    # -- helpers --------------------------------------------------------------

    def not_measured(self, reason: str) -> FamilyScore:
        return FamilyScore.not_measured(self.name, reason)

    def emit(self, ctx: ProbeContext, event: str, **attrs: object) -> None:
        """Record a trace event on the OTel GenAI sink, if one is attached."""
        if ctx.trace is not None:
            ctx.trace.event(self.name, event, attrs)
