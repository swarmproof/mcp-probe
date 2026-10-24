"""Cross-client portability lints (issue #66) — pure, static-ok grader.

"Works in Claude Code, breaks in Cursor." MCP clients diverge in what they tolerate:
context/token budgets differ, some render rich content and some show it raw, and some
ignore tool annotations entirely. A server that leans on one client's behaviour is a
quality problem even when its contract is perfectly valid — so these are **LOW advisory
lints**, each naming the at-risk client behaviour and the portable fix.

Pure function of the discovered surface (no client, no I/O), so it runs in ``static`` mode
and is trivially unit-testable with crafted :class:`ToolDef`\\s. The hazard set is kept
small and conservative to hold the false-positive rate down.

Hazards:
  * ``C14-oversized-output``  — a tool whose schema/description implies a large/unbounded
    collection but exposes no pagination/limit parameter (context-budget-sensitive clients
    truncate or reject it).
  * ``C14-nonportable-content`` — a description relying on a client-specific content/rendering
    hint (ANSI, raw HTML, embedded images/MIME) that plain clients won't render.
  * ``C14-annotation-only-safety`` — a destructive tool whose only safety signal is an
    annotation; clients that ignore annotations give the user no warning.
"""

from __future__ import annotations

import re

from mcp_quality.models import Finding, Severity, ToolDef

# Input param names that bound a result set — presence means the tool is paginatable.
_PAGINATION_PARAMS = frozenset(
    {
        "limit",
        "page",
        "page_size",
        "pagesize",
        "per_page",
        "perpage",
        "cursor",
        "offset",
        "max_results",
        "maxresults",
        "top",
        "count",
        "first",
        "after",
    }
)

# Description phrasing that strongly implies an unbounded collection result.
_COLLECTION_HINT = re.compile(
    r"\b(returns?|lists?|fetch(?:es)?|gets?|retrieves?|dumps?)\s+"
    r"(?:all|every|the\s+(?:full|entire|complete|whole))\b",
    re.I,
)

# Client-specific content / rendering hints some clients silently ignore or show raw.
_NONPORTABLE_CONTENT = re.compile(
    r"\bANSI\b"
    r"|\bterminal escape"
    r"|\b\w+/(?:html|png|jpeg|jpg|gif|svg\+xml)\b"
    r"|<(?:img|div|span|table|svg)\b"
    r"|data:image/",
    re.I,
)

# Words in a name/description that make a destructive effect self-evident without annotations.
_DESTRUCTIVE_WORD = re.compile(
    r"\b(delete|deletes|remove|removes|destroy|destroys|drop|drops|purge|purges|erase|erases"
    r"|permanent|permanently|irreversible|irreversibly|cannot be undone|wipe|wipes)\b",
    re.I,
)


def _top_level_properties(schema: dict | None) -> dict:
    if not isinstance(schema, dict):
        return {}
    props = schema.get("properties")
    return props if isinstance(props, dict) else {}


def _has_pagination(input_schema: dict | None) -> bool:
    return any(name.lower() in _PAGINATION_PARAMS for name in _top_level_properties(input_schema))


def _implies_collection(tool: ToolDef) -> bool:
    """True when the output schema or description implies a large/unbounded collection."""
    out = tool.output_schema or {}
    if isinstance(out, dict):
        if out.get("type") == "array":
            return True
        for prop in _top_level_properties(out).values():
            if isinstance(prop, dict) and prop.get("type") == "array":
                return True
    return bool(tool.description and _COLLECTION_HINT.search(tool.description))


def _check_oversized_output(tool: ToolDef) -> Finding | None:
    if _implies_collection(tool) and not _has_pagination(tool.input_schema):
        return Finding(
            family="contract",
            code="C14-oversized-output",
            severity=Severity.LOW,
            tool=tool.name,
            message=(
                "returns an unbounded collection with no pagination/limit parameter — clients "
                "with smaller context or token budgets (e.g. Cursor) may truncate or reject the output"
            ),
            remediation="add a limit/cursor parameter (and a default cap) so the result stays bounded",
        )
    return None


def _check_nonportable_content(tool: ToolDef) -> Finding | None:
    if not tool.description:
        return None
    match = _NONPORTABLE_CONTENT.search(tool.description)
    if match:
        return Finding(
            family="contract",
            code="C14-nonportable-content",
            severity=Severity.LOW,
            tool=tool.name,
            message=(
                "description relies on a client-specific content/rendering hint "
                f"({match.group(0).strip()!r}) — clients that don't render it show raw markup or drop it"
            ),
            remediation=(
                "return plain text or structured data and let the client render; "
                "don't assume rich display"
            ),
        )
    return None


def _check_annotation_only_safety(tool: ToolDef) -> Finding | None:
    # Only when the server *explicitly* declares the tool destructive via annotation.
    if tool.annotations.get("destructiveHint") is not True:
        return None
    haystack = f"{tool.name} {tool.description or ''}"
    if _DESTRUCTIVE_WORD.search(haystack):
        return None  # the destructive effect is self-evident from name/description too
    return Finding(
        family="contract",
        code="C14-annotation-only-safety",
        severity=Severity.LOW,
        tool=tool.name,
        message=(
            "destructive tool whose only safety signal is the destructiveHint annotation — "
            "clients that ignore annotations will give the user no warning before it runs"
        ),
        remediation="state the destructive effect in the tool name/description, not only in the annotation",
    )


_CHECKS = (_check_oversized_output, _check_nonportable_content, _check_annotation_only_safety)


def grade_client_compat(tools: tuple[ToolDef, ...] | list[ToolDef]) -> list[Finding]:
    """Return cross-client portability lints for a surface. Pure, deterministic, static-ok."""
    findings: list[Finding] = []
    for tool in tools:
        for check in _CHECKS:
            finding = check(tool)
            if finding is not None:
                findings.append(finding)
    return findings
