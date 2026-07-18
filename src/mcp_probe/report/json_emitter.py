"""The ``--json`` emitter — the stable, versioned machine contract (ARCHITECTURE §7).

This document is what CI gates on, what registries ingest, and what the badge derives
from, so its shape is an API. Field order and presence are deliberate; the top-level
``schema`` key lets consumers pin a version. Timing/wall-clock fields live under ``meta``
and are the *only* part excluded from the fast-path byte-identical comparison (NFR-2).
"""

from __future__ import annotations

import json
from typing import Any

from mcp_probe import REPORT_SCHEMA
from mcp_probe.config import ALL_FAMILIES
from mcp_probe.models import Report


def report_to_dict(report: Report, *, include_meta: bool = True) -> dict[str, Any]:
    surface = report.surface
    target: dict[str, Any] = {
        "transport": surface.transport,
        "protocol_version": surface.protocol_version,
        "surface_hash": surface.surface_hash,
    }

    families_out: dict[str, Any] = {}
    # Emit in canonical family order for deterministic diffing.
    for name in ALL_FAMILIES:
        fam = report.families.get(name)
        if fam is None:
            continue
        families_out[name] = fam.to_dict(weight=report.weights.get(name))

    doc: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "rubric_version": report.rubric_version,
        "tool_version": report.tool_version,
        "target": target,
        "overall": {
            "score": round(report.overall_score, 1) if report.overall_score is not None else None,
            "grade": report.overall_grade,
            "hard_gate": report.hard_gate,
        },
        "families": families_out,
    }
    if report.regression is not None:
        doc["regression"] = report.regression
    doc["provenance_hash"] = report.provenance_hash()
    if include_meta and report.meta:
        doc["meta"] = report.meta
    return doc


def report_to_json(report: Report, *, indent: int | None = 2, include_meta: bool = True) -> str:
    """Serialize a report. ``include_meta=False`` yields byte-identical output for
    identical inputs (drops timing) — used by the determinism guard (TEST-PLAN §9.4)."""
    doc = report_to_dict(report, include_meta=include_meta)
    return json.dumps(doc, indent=indent, sort_keys=False, ensure_ascii=False)
