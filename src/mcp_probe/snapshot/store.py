"""Snapshot baseline + diff (ARCHITECTURE §6, REQ-C7/C8).

A snapshot is a committed ``.mcp-probe/snapshot.json`` capturing per-tool description/
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

from mcp_probe import RUBRIC_VERSION
from mcp_probe.models import FamilyScore, Report, ServerSurface, ToolDef

SNAPSHOT_SCHEMA = "mcp-probe/snapshot@1"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _tool_fingerprint(tool: ToolDef) -> dict[str, str]:
    return {
        "description_hash": _hash(tool.description or ""),
        "schema_hash": _hash(json.dumps(tool.input_schema, sort_keys=True)),
    }


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
    broken_contracts: list[str] = field(default_factory=list)
    score_delta: dict[str, float] = field(default_factory=dict)  # per family (negative = worse)
    rubric_mismatch: bool = False

    @property
    def has_regression(self) -> bool:
        """A regression = any negative score delta or any newly broken contract."""
        return bool(self.broken_contracts) or any(d < 0 for d in self.score_delta.values())

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
        if old_tools[name] != new_tools[name]:
            diff.changed_tools.append(name)

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
