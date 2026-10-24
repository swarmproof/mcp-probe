"""Silent-failure detection (issue #64) — pure, live-only grader.

"Fails silently" is a top MCP failure mode: a tool returns a *success* result
(``is_error=False``) while it actually errored or did nothing. C11 already catches the
inverse ("accepts invalid input"); this module catches the success-that-isn't on a
valid invocation, so an agent that trusts ``is_error`` doesn't march on with a non-result.

Two conservative, low-false-positive signals (heuristic → MEDIUM, non-gating):
  1. the result is marked success but its content is **error-shaped** (a stack trace,
     an exception/traceback marker, ``error:``/``failed``), and
  2. the result is **empty while the declared ``output_schema`` promises content**
     (the schema has ``required``/``properties`` but nothing came back).

Pure: it takes an already-captured :class:`InvokeResult`-like object, so it is unit-testable
with no live server. The engine only calls it on the live valid-args path, so in ``static``
mode silent-failure is "not measured" (ADR-006), never zeroed.
"""

from __future__ import annotations

import re
from typing import Any

from mcp_quality.contract.errors import error_text
from mcp_quality.models import Finding, Severity

# Error-shaped markers in a *success* payload. Deliberately conservative (word-boundary,
# case-insensitive, anchored punctuation) to keep false positives low: a tool legitimately
# returning the word "error" in prose shouldn't trip, but "Traceback", "...Exception:",
# "error:", and standalone "failed" are strong error signals.
_ERROR_SHAPED = re.compile(
    r"Traceback \(most recent call last\)"
    r"|File \"[^\"]+\", line \d+"
    r"|\b[A-Za-z_]+(?:Error|Exception):"
    r"|\btraceback\b"
    r"|\berror:"
    r"|\bfailed\b",
    re.I,
)


def promises_content(output_schema: dict[str, Any] | None) -> bool:
    """True when the declared output schema advertises actual fields/content."""
    if not output_schema:
        return False
    return bool(output_schema.get("required") or output_schema.get("properties"))


def _is_empty_result(result: Any) -> bool:
    """True when a success result carries no structured content and no text.

    Conservative: a non-empty ``structured`` or any truthy ``content`` counts as content
    (fewer false positives), so only a genuinely empty result trips the empty branch."""
    structured = getattr(result, "structured", None)
    if structured not in (None, {}, [], ""):
        return False
    return not getattr(result, "content", None)


def detect_silent_failure(
    tool: str,
    result: Any,
    output_schema: dict[str, Any] | None,
) -> Finding | None:
    """Return a ``C13-silent-failure`` finding if a success result looks like a failure.

    Returns ``None`` for a declared error (``is_error=True`` is honest, not silent) and for
    a healthy result. Pure — no I/O."""
    if getattr(result, "is_error", False):
        return None  # a declared error is honest signalling, not a silent failure

    text = error_text(result)
    match = _ERROR_SHAPED.search(text)
    if match:
        return Finding(
            family="contract",
            code="C13-silent-failure",
            severity=Severity.MEDIUM,
            tool=tool,
            message=(
                "tool returned success (is_error=False) but the content is error-shaped "
                f"({match.group(0).strip()!r}) — an agent will treat a failure as a result"
            ),
            remediation="set is_error / return a JSON-RPC error when the tool fails, not a success",
            evidence={"marker": match.group(0).strip()},
        )

    if promises_content(output_schema) and _is_empty_result(result):
        return Finding(
            family="contract",
            code="C13-silent-failure",
            severity=Severity.MEDIUM,
            tool=tool,
            message=(
                "tool returned success with empty content though its output_schema promises "
                "fields — the agent gets nothing while believing the call succeeded"
            ),
            remediation="return the promised content, or signal the no-result case with is_error",
        )

    return None
