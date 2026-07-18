"""Static description-quality lints ``[fast]`` (REQ-L3) — run with no model.

Cheap, offline heuristics for the description smells that make agents pick wrong: no
example, vague/undocumented params, over-long descriptions that waste context, empty or
stub descriptions. These contribute to the Legibility score even when the behavioural
probe is not run (no model configured).
"""

from __future__ import annotations

import re

from mcp_probe.models import Finding, ServerSurface, Severity

_VAGUE = re.compile(r"\b(various|stuff|things|data|misc|etc\.?|and more|handles?)\b", re.I)
_HAS_EXAMPLE = re.compile(r"(example|e\.g\.|for instance|usage:)", re.I)
OVER_LONG_CHARS = 600  # descriptions longer than this waste context on every turn


def lint_descriptions(surface: ServerSurface) -> list[Finding]:
    findings: list[Finding] = []
    for t in surface.tools:
        desc = (t.description or "").strip()
        if not desc:
            findings.append(_f("L3-missing-description", Severity.HIGH, t.name,
                               "tool has no description — agents cannot tell what it does",
                               "add a one-line description with an example"))
            continue
        if len(desc) > OVER_LONG_CHARS:
            findings.append(_f("L3-over-long", Severity.LOW, t.name,
                               f"description is {len(desc)} chars — trim it; every agent pays this each turn",
                               "tighten to the essential contract; move detail to docs"))
        if _VAGUE.search(desc):
            findings.append(_f("L3-vague", Severity.MEDIUM, t.name,
                               "description uses vague language ('data', 'various', 'stuff')",
                               "state concretely what the tool does and returns"))
        if not _HAS_EXAMPLE.search(desc):
            findings.append(_f("L3-no-example", Severity.LOW, t.name,
                               "description has no example call",
                               "add 'Example: <tool>(...)' — examples sharply improve selection"))
        # undocumented params: properties present but described tersely
        props = (t.input_schema or {}).get("properties", {})
        undocumented = [p for p, s in props.items() if isinstance(s, dict) and not s.get("description")]
        if props and len(undocumented) == len(props):
            findings.append(_f("L3-undocumented-params", Severity.LOW, t.name,
                               "no parameter has a description",
                               "describe each parameter so agents fill them correctly"))
    return findings


def _f(code: str, severity: Severity, tool: str, message: str, remediation: str) -> Finding:
    return Finding(family="legibility", code=code, severity=severity, tool=tool,
                   message=message, remediation=remediation)
