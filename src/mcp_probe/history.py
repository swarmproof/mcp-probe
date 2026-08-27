"""Historical score tracking + PR score-delta rendering (issue #9).

The gate says pass/fail; history says which *direction* you're trending. Each run can be
appended to ``.mcp-probe/history.jsonl`` (one JSON object per line), and any two reports
can be diffed into a per-family delta table — rendered for the terminal or as a sticky PR
comment. Cross-rubric comparison is refused (scores minted under different rubrics aren't
comparable, same rule as snapshot diffing / NFR-7).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp_probe.scoring.scorer import _GRADE_ORDER

# Sticky marker so a CI bot can find-and-update its own PR comment instead of spamming.
COMMENT_MARKER = "<!-- mcp-probe-score-delta -->"


def entry_from_report(report: dict[str, Any], *, commit: str = "", ts: str = "") -> dict[str, Any]:
    """Project a report dict down to a compact history entry."""
    fams = {
        name: fam.get("score")
        for name, fam in report.get("families", {}).items()
        if fam.get("score") is not None
    }
    return {
        "commit": commit,
        "ts": ts,
        "rubric_version": report.get("rubric_version", ""),
        "overall_score": report.get("overall", {}).get("score"),
        "overall_grade": report.get("overall", {}).get("grade"),
        "surface_hash": report.get("target", {}).get("surface_hash", ""),
        "families": fams,
    }


def append_history(path: str | Path, entry: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


def load_history(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


@dataclass
class ScoreDelta:
    overall_before: float | None
    overall_after: float | None
    grade_before: str
    grade_after: str
    per_family: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)
    rubric_mismatch: bool = False

    @property
    def overall_change(self) -> float | None:
        if self.overall_before is None or self.overall_after is None:
            return None
        return round(self.overall_after - self.overall_before, 1)

    @property
    def grade_dropped(self) -> bool:
        return _GRADE_ORDER.get(self.grade_after, 0) < _GRADE_ORDER.get(self.grade_before, 0)

    @property
    def has_regression(self) -> bool:
        if self.grade_dropped:
            return True
        return any(
            b is not None and a is not None and a < b - 0.05
            for b, a in self.per_family.values()
        )


def compute_delta(baseline: dict[str, Any], current: dict[str, Any]) -> ScoreDelta:
    """Diff two report dicts (or history entries): baseline → current."""
    b_over = _overall(baseline)
    c_over = _overall(current)
    delta = ScoreDelta(
        overall_before=b_over[0],
        overall_after=c_over[0],
        grade_before=b_over[1],
        grade_after=c_over[1],
        rubric_mismatch=baseline.get("rubric_version") != current.get("rubric_version"),
    )
    if delta.rubric_mismatch:
        return delta  # refuse per-family comparison across rubrics
    b_fams, c_fams = _families(baseline), _families(current)
    for name in sorted(set(b_fams) | set(c_fams)):
        delta.per_family[name] = (b_fams.get(name), c_fams.get(name))
    return delta


def _overall(doc: dict[str, Any]) -> tuple[float | None, str]:
    if "overall" in doc:  # a report dict
        return doc["overall"].get("score"), doc["overall"].get("grade", "?")
    return doc.get("overall_score"), doc.get("overall_grade", "?")  # a history entry


def _families(doc: dict[str, Any]) -> dict[str, float]:
    if "families" in doc and doc["families"] and isinstance(next(iter(doc["families"].values())), dict):
        return {n: f["score"] for n, f in doc["families"].items() if f.get("score") is not None}
    return {n: s for n, s in doc.get("families", {}).items() if s is not None}  # history entry


def _arrow(before: float | None, after: float | None) -> str:
    if before is None or after is None:
        return "·"
    d = after - before
    if abs(d) < 0.05:
        return "→ 0"
    return f"{'▲' if d > 0 else '▼'} {d:+.0f}"


def render_delta_markdown(delta: ScoreDelta) -> str:
    """The sticky PR comment body."""
    lines = [COMMENT_MARKER, "### MCP Quality Score — change vs base", ""]
    if delta.rubric_mismatch:
        lines.append("⚠️ Rubric version changed vs base — scores are not comparable.")
        return "\n".join(lines) + "\n"
    oc = delta.overall_change
    oc_str = "→ 0" if oc == 0 else (f"{oc:+.0f}" if oc is not None else "n/a")
    lines += [
        f"**Overall:** {delta.grade_before} → **{delta.grade_after}** ({oc_str})"
        + ("  ⚠️ **regression**" if delta.has_regression else ""),
        "",
        "| Family | Base | PR | Δ |",
        "|--------|------|----|---|",
    ]
    for name, (b, a) in delta.per_family.items():
        lines.append(
            f"| {name.capitalize()} | {b:.0f} | {a:.0f} | {_arrow(b, a)} |"
            if b is not None and a is not None
            else f"| {name.capitalize()} | {'—' if b is None else f'{b:.0f}'} "
            f"| {'—' if a is None else f'{a:.0f}'} | · |"
        )
    return "\n".join(lines) + "\n"
