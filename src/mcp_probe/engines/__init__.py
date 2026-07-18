"""Check-family engines. Each is a pure function of ``ServerSurface`` (+ optional live
client) → ``FamilyScore`` (ADR-001). Register a new family in :data:`ENGINE_REGISTRY`."""

from __future__ import annotations

from mcp_probe.engines.base import EngineBase, clamp, penalty_score
from mcp_probe.engines.contract import ContractEngine
from mcp_probe.engines.cost import CostEngine
from mcp_probe.engines.legibility import LegibilityEngine
from mcp_probe.engines.performance import PerformanceEngine
from mcp_probe.engines.security import SecurityEngine

# All five families. Contract/Cost/Security are static-ok; Performance is live-only;
# Legibility is [llm] (runs offline lints without a model, full probe with one).
ENGINE_REGISTRY: dict[str, type[EngineBase]] = {
    "contract": ContractEngine,
    "cost": CostEngine,
    "security": SecurityEngine,
    "performance": PerformanceEngine,
    "legibility": LegibilityEngine,
}


def register(name: str, engine_cls: type[EngineBase]) -> None:
    ENGINE_REGISTRY[name] = engine_cls


__all__ = [
    "ENGINE_REGISTRY",
    "EngineBase",
    "ContractEngine",
    "CostEngine",
    "SecurityEngine",
    "PerformanceEngine",
    "LegibilityEngine",
    "register",
    "clamp",
    "penalty_score",
]
