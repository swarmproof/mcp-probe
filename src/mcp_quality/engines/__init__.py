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
from mcp_quality.engines.spec_surface import SpecSurfaceEngine

# Six scored families + one experimental. Contract/Cost/Security/Safety are static-ok;
# Performance is live-only; Legibility is [llm]; Spec-surface is live-only, experimental
# (opt-in via --experimental, zero rubric weight — reported but never moves the grade).
ENGINE_REGISTRY: dict[str, type[EngineBase]] = {
    "contract": ContractEngine,
    "cost": CostEngine,
    "security": SecurityEngine,
    "safety": SafetyEngine,
    "performance": PerformanceEngine,
    "legibility": LegibilityEngine,
    "spec": SpecSurfaceEngine,
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
    "SpecSurfaceEngine",
    "register",
    "clamp",
    "penalty_score",
]
