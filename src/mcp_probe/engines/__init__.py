"""Check-family engines. Each is a pure function of ``ServerSurface`` (+ optional live
client) → ``FamilyScore`` (ADR-001). Register a new family in :data:`ENGINE_REGISTRY`."""

from __future__ import annotations

from mcp_probe.engines.base import EngineBase, clamp, penalty_score
from mcp_probe.engines.contract import ContractEngine
from mcp_probe.engines.cost import CostEngine
from mcp_probe.engines.security import SecurityEngine

# Legibility / Performance are registered as they come online; the fast-path families
# (Contract, Cost) and Security-lite are available with zero external dependencies.
ENGINE_REGISTRY: dict[str, type[EngineBase]] = {
    "contract": ContractEngine,
    "cost": CostEngine,
    "security": SecurityEngine,
}


def register(name: str, engine_cls: type[EngineBase]) -> None:
    ENGINE_REGISTRY[name] = engine_cls


__all__ = [
    "ENGINE_REGISTRY",
    "EngineBase",
    "ContractEngine",
    "CostEngine",
    "SecurityEngine",
    "register",
    "clamp",
    "penalty_score",
]
