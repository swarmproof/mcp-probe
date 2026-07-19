"""Terminal (and HTML) report rendering — the oxblood-themed view over a Report.

This stands in for the shared ``report-renderer`` primitive until it is extracted from
stampede (vendor-first, DELIVERY-PLAN §1.3). It registers a "QualityScoreReport" view:
overall grade banner → per-family table → the findings that matter. Rendering is a pure,
read-only projection of the Report — no scoring logic leaks in here.
"""

from __future__ import annotations

import io
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from mcp_probe.models import NOT_MEASURED, Report

# Oxblood palette — the toolkit's house accent.
OXBLOOD = "#4a0e17"
_GRADE_STYLE: dict[str, str] = {
    "A": "bold green",
    "B": "green",
    "C": "yellow",
    "D": "orange3",
    "F": "bold red",
    NOT_MEASURED: "dim",
}

_FAMILY_ORDER = ("cost", "legibility", "contract", "performance", "security")


def _grade_text(grade: str) -> Text:
    return Text(grade, style=_GRADE_STYLE.get(grade, "white"))


def render_terminal(report: Report, *, console: Console | None = None) -> str:
    """Render to a string (always returned, so it's testable). If a ``console`` is
    passed, the same text is also printed to it."""
    buffer = io.StringIO()
    con = Console(file=buffer, force_terminal=False, width=88, highlight=False)

    score = report.overall_score
    score_str = f"{score:.0f}" if score is not None else "—"
    banner = Text.assemble(
        ("MCP Quality Score  ", f"bold {OXBLOOD}"),
        (score_str, "bold white"),
        ("   Grade ", "white"),
        _grade_text(report.overall_grade),
    )
    con.print(Panel(banner, border_style=OXBLOOD, expand=False))

    if report.hard_gate:
        con.print(
            Text.assemble(
                ("⚠ hard-gate: ", "bold red"),
                (f"'{report.hard_gate}' capped the overall grade at C", "red"),
            )
        )

    table = Table(show_header=True, header_style=f"bold {OXBLOOD}", expand=True)
    table.add_column("Family")
    table.add_column("Grade", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("Weight", justify="right")
    table.add_column("Headline", overflow="fold")

    for name in _FAMILY_ORDER:
        fam = report.families.get(name)
        if fam is None:
            continue
        weight = report.weights.get(name)
        weight_str = f"{weight:.0%}" if weight else "—"
        if fam.measured and fam.score is not None:
            score_cell = f"{fam.score:.0f}"
        else:
            score_cell = "n/m"
        table.add_row(
            name.capitalize(),
            _grade_text(fam.grade),
            score_cell,
            weight_str,
            _family_headline(name, fam.metrics),
        )
    con.print(table)

    # Surface the most severe findings (the actionable part).
    top = sorted(report.all_findings(), key=lambda f: f.severity, reverse=True)[:8]
    if top:
        con.print(Text("\nTop findings", style=f"bold {OXBLOOD}"))
        for f in top:
            line = Text.assemble(
                (f"  [{f.severity.name.lower()}] ", _severity_style(f.severity.name)),
                (f"{f.family}/{f.code}", "cyan"),
                (f"  {f.message}", "white"),
            )
            con.print(line)
            if f.remediation:
                con.print(Text(f"      ↳ {f.remediation}", style="dim"))

    out = buffer.getvalue()

    # The disambiguation matrix goes last — the headline artifact when legibility ran.
    leg = report.families.get("legibility")
    if leg is not None and leg.metrics.get("matrix"):
        out += render_confusion_matrix(leg.metrics)

    if console is not None:
        console.print(out, end="")
    return out


def render_confusion_matrix(metrics: dict[str, Any], *, console: Console | None = None) -> str:
    """The disambiguation matrix — the headline artifact (REQ-L2). Rows = the tool a goal
    *should* pick; columns = the tool an agent actually picked. Off-diagonal mass is
    confusion. Returns "" when no matrix is available (large surface / no model)."""
    order = metrics.get("tool_order")
    matrix = metrics.get("matrix")
    totals = metrics.get("per_tool_total")
    if not order or matrix is None or not totals:
        return ""

    buffer = io.StringIO()
    con = Console(file=buffer, force_terminal=False, width=max(60, 14 + 6 * len(order)), highlight=False)
    con.print(Text("\nDisambiguation matrix  (row = correct tool · cell = % of times chosen)", style=f"bold {OXBLOOD}"))

    table = Table(show_header=True, header_style=f"bold {OXBLOOD}", padding=(0, 1))
    table.add_column("correct ↓ / chose →", overflow="fold")
    labels = [n[:6] for n in order]
    for lab in labels:
        table.add_column(lab, justify="right")

    for true_tool in order:
        total = totals.get(true_tool, 0) or 1
        cells = []
        for chosen in order:
            if chosen == true_tool:
                correct = total - sum(matrix.get(true_tool, {}).values())
                rate = correct / total
                cells.append(Text(f"{rate:.0%}", style="green" if rate >= 0.8 else "yellow"))
            else:
                count = matrix.get(true_tool, {}).get(chosen, 0)
                rate = count / total
                style = "bold red" if rate >= 0.3 else ("red" if rate > 0 else "dim")
                cells.append(Text(f"{rate:.0%}" if rate else "·", style=style))
        table.add_row(Text(true_tool[:18], style="cyan"), *cells)
    con.print(table)

    out = buffer.getvalue()
    if console is not None:
        console.print(out, end="")
    return out


def _severity_style(name: str) -> str:
    return {
        "critical": "bold red",
        "high": "red",
        "medium": "yellow",
        "low": "dim",
        "info": "dim",
    }.get(name.lower(), "white")


def _family_headline(name: str, metrics: dict[str, Any]) -> str:
    """One-line, family-specific summary of the key number(s)."""
    if not metrics:
        return ""
    if name == "cost" and "toolset_tokens" in metrics:
        parts = [f"{metrics['toolset_tokens']} toolset tokens"]
        if "usd_per_task" in metrics:
            parts.append(f"${metrics['usd_per_task']}/task")
        return "; ".join(parts)
    if name == "legibility":
        rate = metrics.get("selection_rate")
        if rate is None:
            return "lints only (no model)"
        headline = f"{rate:.0%} right-tool selection"
        if metrics.get("top_confusion"):
            a, b, r = metrics["top_confusion"]
            headline += f"; {a}⇄{b} {r:.0%}"
        return headline
    if name == "performance" and "p95_ms" in metrics:
        return f"p95 {metrics['p95_ms']}ms; degradation {metrics.get('degradation', '?')}"
    if name == "contract":
        return metrics.get("summary", "")
    return metrics.get("reason", "")


def render_html(report: Report) -> str:
    """Minimal shareable HTML view (oxblood). Self-contained, no external assets."""
    rows = []
    for name in _FAMILY_ORDER:
        fam = report.families.get(name)
        if fam is None:
            continue
        score_cell = f"{fam.score:.0f}" if (fam.measured and fam.score is not None) else "n/m"
        rows.append(
            f"<tr><td>{name.capitalize()}</td><td class='g g-{fam.grade}'>{fam.grade}</td>"
            f"<td>{score_cell}</td></tr>"
        )
    score = f"{report.overall_score:.0f}" if report.overall_score is not None else "—"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>mcp-probe report</title>
<style>
 body{{font-family:system-ui,sans-serif;background:#faf7f7;color:#1a1a1a;margin:2rem}}
 h1{{color:{OXBLOOD}}} table{{border-collapse:collapse;margin-top:1rem}}
 td,th{{border:1px solid #ddd;padding:.4rem .8rem}}
 .g-A{{color:#0a0}}.g-B{{color:#3a3}}.g-C{{color:#b90}}.g-D{{color:#d60}}.g-F{{color:#c00}}
 .score{{font-size:3rem;font-weight:700}}
</style></head><body>
<h1>MCP Quality Score</h1>
<div class="score">{score} <span class="g g-{report.overall_grade}">{report.overall_grade}</span></div>
<p>rubric {report.rubric_version} · tool {report.tool_version} · {report.surface.protocol_version or 'unknown protocol'}</p>
<table><tr><th>Family</th><th>Grade</th><th>Score</th></tr>{''.join(rows)}</table>
</body></html>"""
