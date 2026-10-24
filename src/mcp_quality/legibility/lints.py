"""Static description-quality lints ``[fast]`` (REQ-L3) — run with no model.

Cheap, offline heuristics for the description smells that make agents pick wrong: no
example, vague/undocumented params, over-long descriptions that waste context, empty or
stub descriptions. These contribute to the Legibility score even when the behavioural
probe is not run (no model configured).
"""

from __future__ import annotations

import re

from mcp_quality.models import Finding, ServerSurface, Severity

_VAGUE = re.compile(r"\b(various|stuff|things|data|misc|etc\.?|and more|handles?)\b", re.I)
_HAS_EXAMPLE = re.compile(r"(example|e\.g\.|for instance|usage:)", re.I)
OVER_LONG_CHARS = 600  # descriptions longer than this waste context on every turn

# Generic param names an agent can't reason about (kept tight to avoid false positives;
# common-and-fine names like id/name/query/url/path/key/value are intentionally excluded).
_AMBIGUOUS_PARAMS = {
    "data", "obj", "arg", "args", "input", "param", "params", "tmp", "temp",
    "foo", "bar", "thing", "things", "stuff", "payload", "info",
}
# Tools whose name implies they return a collection — they should support pagination.
_COLLECTION_TOOL = re.compile(r"(^|_)(list|search|query|find|browse|feed|history|recent|all)(_|$)", re.I)
_PAGINATION_PARAMS = {
    "limit", "offset", "cursor", "page", "per_page", "page_size", "pagesize",
    "page_token", "max_results", "maxresults", "count", "top", "after", "before",
}
# Low-level identifiers that shouldn't leak into agent-facing descriptions.
_LEAKED_ID = re.compile(r"\b(uuid|guid|mime_?type|base64|[0-9]{2,4}px|etag|checksum|sha-?256)\b", re.I)

# Tool-count overload (#63): agent tool-selection accuracy craters past ~40–50 tools
# (measured ~95%→71%); <10–15 visible tools is ideal for smaller models. Bands: (threshold,
# severity, why) in descending order — the first exceeded band wins.
_OVERLOAD_BANDS: tuple[tuple[int, Severity, str], ...] = (
    (50, Severity.MEDIUM, "past the ~40–50-tool cliff where agents start picking the wrong tool"),
    (30, Severity.LOW, "above the comfortable range — tool selection begins to degrade"),
    (15, Severity.INFO, "above the ~10–15-tool ideal for smaller models"),
)


def overload_band(tool_count: int) -> str:
    """Short band label for metrics: ok | above-ideal | degraded | overloaded."""
    if tool_count > 50:
        return "overloaded"
    if tool_count > 30:
        return "degraded"
    if tool_count > 15:
        return "above-ideal"
    return "ok"


def lint_tool_overload(surface: ServerSurface) -> Finding | None:
    """Surface-level: flag a toolset large enough to hurt agent tool-selection (#63)."""
    n = len(surface.tools)
    for threshold, severity, why in _OVERLOAD_BANDS:
        if n > threshold:
            return Finding(
                family="legibility", code="L8-tool-overload", severity=severity,
                message=f"{n} tools exposed — {why}",
                remediation="group/namespace tools, split into focused sub-servers, or load "
                "tools dynamically (tool-search / RAG-MCP) so the agent sees only what it needs",
                evidence={"tool_count": n, "band": overload_band(n)},
            )
    return None


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
        # ambiguous param names — a model can't reason about `data`/`obj`/single letters
        ambiguous = sorted(p for p in props if p.lower() in _AMBIGUOUS_PARAMS or len(p) == 1)
        if ambiguous:
            findings.append(_f("L3-ambiguous-param", Severity.LOW, t.name,
                               f"generic parameter name(s): {', '.join(ambiguous)}",
                               "use specific names (e.g. `user_id`, not `id`/`data`)"))
        # collection tools should paginate — unbounded lists blow the context window
        if _COLLECTION_TOOL.search(t.name) and not (set(map(str.lower, props)) & _PAGINATION_PARAMS):
            findings.append(_f("L3-no-pagination", Severity.LOW, t.name,
                               "looks like it returns a collection but has no pagination param",
                               "add a `limit`/`cursor` so callers can bound the response"))
        # low-level identifiers leaking into the agent-facing description
        if _LEAKED_ID.search(desc):
            findings.append(_f("L3-leaked-identifier", Severity.INFO, t.name,
                               "description exposes a low-level identifier (uuid/mime_type/etc.)",
                               "describe behaviour in the caller's terms, not implementation details"))
    return findings


def _f(code: str, severity: Severity, tool: str, message: str, remediation: str) -> Finding:
    return Finding(family="legibility", code=code, severity=severity, tool=tool,
                   message=message, remediation=remediation)
