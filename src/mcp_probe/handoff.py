"""The ``stampede --from-probe`` handoff seed (ARCHITECTURE §9).

mcp-probe already did connect + discover and knows where the bodies are buried — which
tool pairs agents confuse, which tools are expensive, which are nondeterministic. This
serializes that into the ``swarmproof/probe-handoff@1`` document stampede consumes to
boot a full behavioural simulation of the *same* server. "Your server scored a B — now
watch 200 agents actually use it."

Both tools share the OTel GenAI trace profile and the MCPTarget shape, so the handoff is
thin: target + discovered surface + a prior on where to look.
"""

from __future__ import annotations

import json
from typing import Any

from mcp_probe.models import Report

HANDOFF_SCHEMA = "swarmproof/probe-handoff@1"


def build_stampede_seed_dict(report: Report) -> dict[str, Any]:
    surface = report.surface
    cost = report.families.get("cost")
    legibility = report.families.get("legibility")
    contract = report.families.get("contract")

    expensive = _top_expensive(cost.metrics if cost else {})
    confusable = _confusable_pairs(legibility.metrics if legibility else {})
    nondeterministic = (contract.metrics.get("nondeterministic_tools", []) if contract else [])

    command = report.meta.get("target") or ""
    return {
        "schema": HANDOFF_SCHEMA,
        "target": {
            "type": "mcp",
            "transport": surface.transport,
            "command": command,
            "protocol_version": surface.protocol_version,
        },
        "surface": {
            "surface_hash": surface.surface_hash,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in surface.tools
            ],
        },
        "hotspots": {
            "confusable_tool_pairs": confusable,
            "expensive_tools": expensive,
            "nondeterministic_tools": nondeterministic,
        },
        "suggested_stampede_yaml": {
            "target": {"type": "mcp", "transport": surface.transport, "command": command},
            "population": {
                "size": 200,
                "mix": {"naive": 0.5, "expert": 0.2, "adversarial": 0.05},
            },
        },
        "probe_report_ref": "./mcp-probe-report.json",
    }


def build_stampede_seed(report: Report, *, indent: int = 2) -> str:
    return json.dumps(build_stampede_seed_dict(report), indent=indent) + "\n"


def _top_expensive(cost_metrics: dict[str, Any], *, top: int = 3) -> list[str]:
    per_tool: dict[str, int] = cost_metrics.get("per_tool_tokens", {})
    return [name for name, _ in list(per_tool.items())[:top]]


def _confusable_pairs(leg_metrics: dict[str, Any]) -> list[list[Any]]:
    top = leg_metrics.get("top_confusion")
    return [list(top)] if top else []
