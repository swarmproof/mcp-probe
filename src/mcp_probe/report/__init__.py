"""Rendering & emission: the same :class:`~mcp_probe.models.Report` → terminal, HTML,
JSON (the CI contract), and badge. Renderers are read-only consumers of the Report."""

from mcp_probe.report.badge import badge_color, badge_svg, shields_endpoint
from mcp_probe.report.json_emitter import report_to_dict, report_to_json

__all__ = [
    "report_to_dict",
    "report_to_json",
    "badge_color",
    "badge_svg",
    "shields_endpoint",
]
