"""Snapshot baseline + diff (ARCHITECTURE §6, REQ-C7/C8).

A snapshot is a committed ``.mcp-quality/snapshot.json`` capturing per-tool description/
schema hashes plus each family's score, stamped with ``rubric_version``. On every run we
diff the live surface + scores against it and report **added / removed / changed** tools,
per-family **score deltas**, and **broken contracts**. ``--no-regressions`` turns any
score drop or new contract break into a non-zero exit — independent of absolute grade,
which is how a silent regression surfaces in a PR.

Cross-rubric comparison is refused, not silently performed: comparing scores minted under
different rubrics would be meaningless (ADR-008).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp_quality import RUBRIC_VERSION
from mcp_quality.models import FamilyScore, Report, ServerSurface, ToolDef

SNAPSHOT_SCHEMA = "mcp-quality/snapshot@1"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _tool_fingerprint(tool: ToolDef) -> dict[str, Any]:
    """Per-tool fingerprint for drift detection (#27): content hashes + a capability
    surface (declared safety + params) so we can catch silent scope/breaking changes."""
    schema = tool.input_schema or {}
    props = schema.get("properties") or {}
    return {
        "description_hash": _hash(tool.description or ""),
        "schema_hash": _hash(json.dumps(schema, sort_keys=True)),
        "read_only": bool(tool.is_read_only),
        "destructive": bool(tool.is_destructive),
        "required": sorted(schema.get("required", []) or []),
        "params": {k: (v.get("type") if isinstance(v, dict) else None) for k, v in props.items()},
    }


def _capability_changes(name: str, old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, str]]:
    """Typed drift between two fingerprints of the same tool. Only flags changes that
    widen scope or break existing callers; silent on additive/cosmetic changes."""
    out: list[dict[str, str]] = []
    # scope expansion — was declared safe, now isn't (the rug-pull tell). Only when the
    # baseline recorded the flag (old-format snapshots omit it → skip, no false positive).
    if "read_only" in old and old.get("read_only") and not new.get("read_only"):
        out.append({"tool": name, "kind": "scope-expansion", "detail": "was read-only, now is not"})
    if "destructive" in old and not old.get("destructive") and new.get("destructive"):
        out.append({"tool": name, "kind": "scope-expansion", "detail": "now declares destructive"})
    # breaking schema — new required fields / removed params / changed types break callers.
    if "required" in old:
        new_required = sorted(set(new.get("required", [])) - set(old.get("required", [])))
        if new_required:
            out.append({"tool": name, "kind": "breaking-schema",
                        "detail": f"new required param(s): {', '.join(new_required)}"})
    if "params" in old:
        old_p, new_p = old.get("params", {}), new.get("params", {})
        removed = sorted(set(old_p) - set(new_p))
        if removed:
            out.append({"tool": name, "kind": "breaking-schema",
                        "detail": f"removed param(s): {', '.join(removed)}"})
        for p in sorted(set(old_p) & set(new_p)):
            if old_p[p] != new_p[p]:
                out.append({"tool": name, "kind": "breaking-schema",
                            "detail": f"param '{p}' type {old_p[p]} → {new_p[p]}"})
    return out


def build_snapshot(surface: ServerSurface, families: dict[str, FamilyScore]) -> dict[str, Any]:
    return {
        "schema": SNAPSHOT_SCHEMA,
        "rubric_version": RUBRIC_VERSION,
        "surface_hash": surface.surface_hash,
        "tools": {t.name: _tool_fingerprint(t) for t in surface.tools},
        "family_scores": {
            name: fam.score for name, fam in families.items() if fam.measured
        },
    }


def write_snapshot(path: str | Path, snapshot: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_snapshot(path: str | Path) -> dict[str, Any] | None:
    p = Path(path)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


@dataclass
class SnapshotDiff:
    baseline_hash: str
    added_tools: list[str] = field(default_factory=list)
    removed_tools: list[str] = field(default_factory=list)
    changed_tools: list[str] = field(default_factory=list)  # description or schema changed
    capability_changes: list[dict[str, str]] = field(default_factory=list)  # typed drift (#27)
    broken_contracts: list[str] = field(default_factory=list)
    score_delta: dict[str, float] = field(default_factory=dict)  # per family (negative = worse)
    rubric_mismatch: bool = False

    @property
    def has_regression(self) -> bool:
        """A regression = a newly broken contract, a negative score delta, a removed tool,
        or a capability change (scope expansion / breaking schema) — the drift that
        silently defeats a prior approval (#27)."""
        return (
            bool(self.broken_contracts)
            or bool(self.removed_tools)
            or bool(self.capability_changes)
            or any(d < 0 for d in self.score_delta.values())
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "baseline": self.baseline_hash,
            "changed_tools": self.changed_tools,
            "broken_contracts": self.broken_contracts,
            "score_delta": {k: round(v, 1) for k, v in self.score_delta.items()},
        }
        if self.added_tools:
            out["added_tools"] = self.added_tools
        if self.removed_tools:
            out["removed_tools"] = self.removed_tools
        if self.capability_changes:
            out["capability_changes"] = self.capability_changes
        if self.rubric_mismatch:
            out["rubric_mismatch"] = True
        return out


def diff_against_baseline(
    baseline: dict[str, Any],
    surface: ServerSurface,
    families: dict[str, FamilyScore],
) -> SnapshotDiff:
    diff = SnapshotDiff(baseline_hash=baseline.get("surface_hash", ""))

    # Refuse silent cross-rubric comparison (ADR-008); still report structural changes.
    if baseline.get("rubric_version") != RUBRIC_VERSION:
        diff.rubric_mismatch = True

    old_tools: dict[str, dict[str, str]] = baseline.get("tools", {})
    new_tools = {t.name: _tool_fingerprint(t) for t in surface.tools}

    diff.added_tools = sorted(set(new_tools) - set(old_tools))
    diff.removed_tools = sorted(set(old_tools) - set(new_tools))
    for name in sorted(set(old_tools) & set(new_tools)):
        old_fp, new_fp = old_tools[name], new_tools[name]
        # changed = semantic content (desc/schema) differs — stable across fingerprint-format
        # upgrades, which add keys but don't change these two hashes.
        if (old_fp.get("description_hash"), old_fp.get("schema_hash")) != (
            new_fp["description_hash"], new_fp["schema_hash"]
        ):
            diff.changed_tools.append(name)
        diff.capability_changes.extend(_capability_changes(name, old_fp, new_fp))

    # Score deltas per family — only when rubric matches (else scores aren't comparable).
    if not diff.rubric_mismatch:
        old_scores: dict[str, float] = baseline.get("family_scores", {})
        for name, fam in families.items():
            if fam.measured and fam.score is not None and name in old_scores:
                delta = fam.score - old_scores[name]
                if abs(delta) >= 0.05:  # ignore float noise
                    diff.score_delta[name] = delta

    # Broken contracts: a Contract hard-gate that the baseline didn't have.
    contract = families.get("contract")
    if contract is not None and contract.hard_gate_tripped:
        diff.broken_contracts = [
            f.tool or f.code for f in contract.findings if f.severity.name in ("HIGH", "CRITICAL")
        ]

    return diff


def attach_regression(report: Report, diff: SnapshotDiff) -> None:
    """Fold a diff into a report's ``regression`` block (ARCHITECTURE §7)."""
    report.regression = diff.to_dict()
