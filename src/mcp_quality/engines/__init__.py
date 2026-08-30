"""Check-family engines. Each is a pure function of ``ServerSurface`` (+ optional live
client) → ``FamilyScore`` (ADR-001). Register a new family in :data:`ENGINE_REGISTRY`."""

from __future__ import annotations

from mcp_quality.engines.base import EngineBase, clamp, penalty_score
from mcp_quality.engines.contract import ContractEngine
from mcp_quality.engines.cost import CostEngine
from mcp_quality.engines.legibility import LegibilityEngine
from mcp_quality.engines.performance import PerformanceEngine
from mcp_quality.engines.safety import SafetyEngine
from mcp_quality.engines.security import SecurityEngine

# Six families. Contract/Cost/Security/Safety are static-ok; Performance is live-only;
# Legibility is [llm] (runs offline lints without a model, full probe with one).
ENGINE_REGISTRY: dict[str, type[EngineBase]] = {
    "contract": ContractEngine,
    "cost": CostEngine,
    "security": SecurityEngine,
    "safety": SafetyEngine,
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
    "SafetyEngine",
    "PerformanceEngine",
    "LegibilityEngine",
    "register",
    "clamp",
    "penalty_score",
]
