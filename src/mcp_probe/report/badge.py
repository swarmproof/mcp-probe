"""Badge emission (PRD §8) — the distribution mechanism.

Two outputs from one grade: a self-contained SVG (no shields.io round-trip needed in
CI/air-gapped repos) and a shields.io-compatible JSON endpoint for dynamic badges. The
``rubric_version`` rides along in the SVG ``<title>`` so a badge minted under an old
rubric is detectable. Grade → colour runs A(green) … F(red).
"""

from __future__ import annotations

import html
import json

# shields.io named colours, keyed by grade.
_GRADE_COLOR: dict[str, str] = {
    "A": "brightgreen",
    "B": "green",
    "C": "yellow",
    "D": "orange",
    "F": "red",
    "not-measured": "lightgrey",
}

# Hex equivalents for the self-contained SVG.
_COLOR_HEX: dict[str, str] = {
    "brightgreen": "#4c1",
    "green": "#97ca00",
    "yellow": "#dfb317",
    "orange": "#fe7d37",
    "red": "#e05d44",
    "lightgrey": "#9f9f9f",
}


def badge_color(grade: str) -> str:
    return _GRADE_COLOR.get(grade, "lightgrey")


def shields_endpoint(grade: str, *, label: str = "mcp-probe") -> dict[str, object]:
    """The shields.io dynamic-endpoint payload (PRD §8)."""
    return {
        "schemaVersion": 1,
        "label": label,
        "message": grade,
        "color": badge_color(grade),
    }


def _text_width(text: str) -> int:
    # ~7px per char is close enough for Verdana 11; keeps the badge self-contained.
    return max(len(text) * 7 + 10, 20)


def badge_svg(
    grade: str,
    *,
    label: str = "mcp-probe",
    rubric_version: str = "",
    score: float | None = None,
) -> str:
    """A flat shields-style SVG. ``score`` (if given) renders ``mcp-probe: A · 92``."""
    message = grade if score is None else f"{grade} · {int(round(score))}"
    color = _COLOR_HEX[badge_color(grade)]
    lw, mw = _text_width(label), _text_width(message)
    total = lw + mw
    title = html.escape(f"{label}: {message}" + (f" (rubric {rubric_version})" if rubric_version else ""))
    label_e, message_e = html.escape(label), html.escape(message)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" role="img" aria-label="{title}">
  <title>{title}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r"><rect width="{total}" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{lw}" height="20" fill="#555"/>
    <rect x="{lw}" width="{mw}" height="20" fill="{color}"/>
    <rect width="{total}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="{lw / 2}" y="15" fill="#010101" fill-opacity=".3">{label_e}</text>
    <text x="{lw / 2}" y="14">{label_e}</text>
    <text x="{lw + mw / 2}" y="15" fill="#010101" fill-opacity=".3">{message_e}</text>
    <text x="{lw + mw / 2}" y="14">{message_e}</text>
  </g>
</svg>"""


def shields_endpoint_json(grade: str, *, label: str = "mcp-probe") -> str:
    return json.dumps(shields_endpoint(grade, label=label), separators=(",", ":"))
