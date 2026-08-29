"""Error-recovery affordance grading (issue #25).

When a tool fails, the *shape* of the error it returns decides whether the agent recovers
or spirals: a structured, actionable error lets the agent fix-and-retry; a vague "something
went wrong" makes it invent a recovery and run it against a live system. This module grades
the error payload an agent would actually receive — pure, so it's fully unit-testable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from mcp_quality.models import Finding, Severity

# Leaked internals — a stack trace / path / exception class / secret in an error payload.
_LEAK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("stack-trace", re.compile(r"Traceback \(most recent call last\)|File \"[^\"]+\", line \d+")),
    ("exception-class", re.compile(r"\b[A-Za-z_]+(Error|Exception)\b:")),
    ("filesystem-path", re.compile(r"(/(usr|home|Users|var|opt|etc)/|[A-Za-z]:\\\\)")),
    ("secret", re.compile(r"\bsk-[A-Za-z0-9]{16,}\b|\bAKIA[0-9A-Z]{16}\b|BEGIN (RSA )?PRIVATE KEY")),
]

# A bare/generic message with nothing an agent can act on.
_OPAQUE = re.compile(
    r"^(error|failed|failure|something went wrong|internal( server)? error|unknown error"
    r"|bad request|invalid|not ?ok|\d{3})\.?$",
    re.I,
)

# Signals that the error tells the agent how to recover.
_ACTIONABLE = re.compile(
    r"\b(retry|retryable|retry[_-]?after|must be|required|expected|provide|missing|"
    r"invalid value|out of range|did you mean|use \w+ instead|not found|unauthorized|"
    r"rate ?limit|too large|exceeds)\b",
    re.I,
)


@dataclass
class ErrorAffordance:
    affordance: int  # 0..100 — how recoverable the error is for an agent
    findings: list[Finding]


def error_text(result: Any) -> str:
    """Flatten an InvokeResult's payload (content blocks / structured) into one string."""
    parts: list[str] = []
    structured = getattr(result, "structured", None)
    if structured is not None:
        parts.append(json.dumps(structured, default=str, ensure_ascii=False))
    content = getattr(result, "content", None)
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, dict):
        parts.append(json.dumps(content, default=str, ensure_ascii=False))
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or json.dumps(block, default=str, ensure_ascii=False)))
            else:
                parts.append(str(block))
    return " ".join(p for p in parts if p).strip()


def grade_error_payload(tool: str, result: Any) -> ErrorAffordance:
    """Grade the error a tool returned for malformed input (issue #25).

    Cases: (1) leaked internals → HIGH, big penalty; (2) opaque/generic → MEDIUM;
    (3) some text but no actionable guidance → LOW; (4) actionable → clean, high score.
    A tool that returns a *non-error* for schema-invalid input gets a LOW 'silent-accept'.
    """
    findings: list[Finding] = []
    is_error = bool(getattr(result, "is_error", False))
    text = error_text(result)

    if not is_error:
        findings.append(
            _f("C11-silent-accept", Severity.LOW, tool,
               "tool returned a non-error result for schema-invalid input — no signal to correct",
               "reject invalid input with a clear error result")
        )
        return ErrorAffordance(affordance=45, findings=findings)

    leaked = [label for label, pat in _LEAK_PATTERNS if pat.search(text)]
    if leaked:
        findings.append(
            _f("C11-error-leak", Severity.HIGH, tool,
               f"error payload leaks internals ({', '.join(leaked)}) — info disclosure + hurts recovery",
               "return a clean, categorized error; never surface stack traces / paths / secrets",
               evidence={"leaked": leaked})
        )
        return ErrorAffordance(affordance=25, findings=findings)

    stripped = text.strip()
    if not stripped or _OPAQUE.match(stripped):
        findings.append(
            _f("C11-error-opaque", Severity.MEDIUM, tool,
               "error payload is opaque ('something went wrong') — the agent can't tell what to fix",
               "include a category/code and what the caller should change")
        )
        return ErrorAffordance(affordance=40, findings=findings)

    if not _ACTIONABLE.search(text):
        findings.append(
            _f("C11-error-unactionable", Severity.LOW, tool,
               "error has detail but no actionable guidance (what to change, retryable, alternative)",
               "state the fix: which field, whether it's retryable, or an alternative tool")
        )
        return ErrorAffordance(affordance=70, findings=findings)

    return ErrorAffordance(affordance=100, findings=findings)


def _f(code: str, sev: Severity, tool: str, message: str, remediation: str,
       evidence: dict | None = None) -> Finding:
    return Finding(family="contract", code=code, severity=sev, tool=tool,
                   message=message, remediation=remediation, evidence=evidence)
