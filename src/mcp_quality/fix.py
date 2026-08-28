"""Legibility auto-fix (REQ-L7) — apply the description rewrites mcp-quality proposes.

The diagnosis→fix loop: `run --legibility` emits `L5-rewrite` findings carrying the exact
`old` description and a proposed `rewrite` (in each finding's ``evidence``). This module
finds the old text in a target source file and replaces it with the rewrite, safely:

* **Exact-match only** — the scanned description must appear verbatim in the source, or the
  rewrite is skipped (never a fuzzy edit).
* **Ambiguity guard** — if the old text appears more than once, skip it (can't tell which).
* **Dry-run by default** — callers opt in to writing; opening a PR is a further opt-in.

Servers that build descriptions dynamically won't match; that's reported, not forced.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Rewrite:
    tool: str
    old: str
    new: str


@dataclass
class ApplyResult:
    applied: list[Rewrite] = field(default_factory=list)
    skipped: list[tuple[Rewrite, str]] = field(default_factory=list)  # (rewrite, reason)
    diff: str = ""

    @property
    def changed(self) -> bool:
        return bool(self.applied)


def collect_rewrites(report: dict[str, Any], *, only: set[str] | None = None) -> list[Rewrite]:
    """Pull (tool, old, new) rewrites out of a report's legibility L5-rewrite findings."""
    leg = report.get("families", {}).get("legibility", {})
    out: list[Rewrite] = []
    for f in leg.get("findings", []):
        if f.get("code") != "L5-rewrite":
            continue
        ev = f.get("evidence") or {}
        old, new = ev.get("old"), ev.get("rewrite")
        tool = f.get("tool")
        if not old or not new or not tool:
            continue  # nothing safely applicable (e.g. an empty original description)
        if only is not None and tool not in only:
            continue
        out.append(Rewrite(tool=tool, old=old, new=new))
    return out


def _occurrences(text: str, needle: str) -> list[int]:
    idx, out = text.find(needle), []
    while idx != -1:
        out.append(idx)
        idx = text.find(needle, idx + 1)
    return out


def _locate(text: str, rw: Rewrite) -> tuple[int | None, str]:
    """Return (start_index, reason). When the old text repeats, pick the occurrence
    *nearest* the tool's name (decorator-style servers put them adjacent); a tie is
    ambiguous and skipped. Sequential application also helps: once one identical
    description is rewritten, the next becomes unique."""
    occ = _occurrences(text, rw.old)
    if not occ:
        return None, "original description not found in source (dynamic?)"
    if len(occ) == 1:
        return occ[0], ""
    tool_pos = _occurrences(text, rw.tool)
    if not tool_pos:
        return None, f"original appears {len(occ)}× and tool name '{rw.tool}' not in source — skipped"

    def nearest(i: int) -> int:
        return min(abs(i - tp) for tp in tool_pos)

    ranked = sorted(occ, key=nearest)
    if len(ranked) >= 2 and nearest(ranked[0]) == nearest(ranked[1]):
        return None, f"original appears {len(occ)}× and can't be anchored to '{rw.tool}' — skipped"
    return ranked[0], ""


def apply_rewrites(source: str, rewrites: list[Rewrite]) -> tuple[str, ApplyResult]:
    """Apply rewrites to ``source`` text. Returns (new_source, result). Pure — no I/O.

    Replacement is index-based and re-scans after each edit, so shifting offsets are
    handled and repeated descriptions are disambiguated by tool-name proximity."""
    result = ApplyResult()
    updated = source
    for rw in rewrites:
        if rw.old == rw.new:
            result.skipped.append((rw, "rewrite identical to original"))
            continue
        start, reason = _locate(updated, rw)
        if start is None:
            result.skipped.append((rw, reason))
            continue
        updated = updated[:start] + rw.new + updated[start + len(rw.old):]
        result.applied.append(rw)

    if result.applied:
        result.diff = "".join(
            difflib.unified_diff(
                source.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile="a/source",
                tofile="b/source",
            )
        )
    return updated, result


def apply_to_file(path: str | Path, rewrites: list[Rewrite], *, write: bool) -> ApplyResult:
    """Apply rewrites to a file. ``write=False`` computes the diff without touching disk."""
    p = Path(path)
    source = p.read_text(encoding="utf-8")
    updated, result = apply_rewrites(source, rewrites)
    if write and result.changed:
        p.write_text(updated, encoding="utf-8")
    return result
