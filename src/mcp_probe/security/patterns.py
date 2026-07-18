"""Built-in security lints ``[fast]`` (REQ-S1–S3), mapped to OWASP IDs.

Standard: findings anchor to the **OWASP MCP Top 10 (2025)** — the MCP-specific catalogue
(OWASP/www-project-mcp-top-10) — as the primary ``owasp_id``. That project is in **Beta**,
so the ``MCPxx:2025`` IDs may shift before GA; re-verify before a 1.0 release. Where a
finding also has a general-agent analogue we note the OWASP Top-10-for-LLM-Apps 2025 ID as
a secondary reference. The ``owasp_id`` lets findings dedup cleanly against external
scanners (mcp-scan / Cisco), which map to the same taxonomies (REQ-S5).

These are cheap, offline, high-precision lints — the point is a security *floor*, not a
replacement for mcp-scan / Cisco (that's ``--deep-security``, §8).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from mcp_probe.models import Finding, ServerSurface, Severity


class OWASP:
    """OWASP MCP Top 10 (2025, Beta) identifiers — the primary finding anchors.
    Source: OWASP/www-project-mcp-top-10. IDs may shift before the project's GA."""

    SECRET_EXPOSURE = "MCP01:2025"       # Token Mismanagement & Secret Exposure
    PRIVILEGE_ESCALATION = "MCP02:2025"  # Privilege Escalation via Scope Creep
    TOOL_POISONING = "MCP03:2025"        # Tool Poisoning (hidden instructions, rug-pull)
    SUPPLY_CHAIN = "MCP04:2025"          # Supply Chain & Dependency Tampering
    COMMAND_INJECTION = "MCP05:2025"     # Command Injection & Execution
    INTENT_SUBVERSION = "MCP06:2025"     # Intent Flow Subversion
    AUTHZ = "MCP07:2025"                 # Insufficient Authentication & Authorization
    CONTEXT_INJECTION = "MCP10:2025"     # Context Injection & Over-Sharing


class LLMTop10:
    """OWASP Top 10 for LLM Applications (2025) — secondary/dual-map reference for
    findings that aren't MCP-specific."""

    PROMPT_INJECTION = "LLM01:2025"
    SENSITIVE_INFO = "LLM02:2025"
    EXCESSIVE_AGENCY = "LLM06:2025"


# Hidden-instruction / tool-poisoning markers in tool & resource text (LLM01).
_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("override-instruction", re.compile(r"ignore (all |the )?(previous|prior|above) instructions", re.I)),
    ("hidden-directive", re.compile(r"<(important|system|secret|instructions?)>", re.I)),
    ("imperative-injection", re.compile(r"\b(you must|always|never) (call|use|invoke|run|send)\b", re.I)),
    ("data-exfil", re.compile(r"(send|forward|leak|exfiltrat\w+).{0,30}\b(to |@)\b", re.I)),
    ("html-comment", re.compile(r"<!--.*?-->", re.S)),
    ("tool-shadow", re.compile(r"\bdo not (mention|tell|reveal)\b", re.I)),
]

# Secret material (LLM02).
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[posu]_[A-Za-z0-9]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("private-key", re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----")),
    ("generic-bearer", re.compile(r"\bbearer\s+[A-Za-z0-9._-]{20,}\b", re.I)),
]

# Dangerous capability signals in names/descriptions (LLM06 excessive agency).
_DANGEROUS = re.compile(
    r"\b(exec|eval|shell|subprocess|os\.system|spawn|/bin/(sh|bash)|rm\s+-rf|"
    r"sudo|chmod|write_file|delete_file|drop_table|arbitrary code)\b",
    re.I,
)


@dataclass
class _Hit:
    tool: str | None
    where: str


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _texts(surface: ServerSurface) -> list[tuple[str | None, str, str]]:
    """(tool_name, where, text) tuples across the whole surface."""
    out: list[tuple[str | None, str, str]] = []
    for t in surface.tools:
        if t.description:
            out.append((t.name, "description", t.description))
        out.append((t.name, "schema", str(t.input_schema)))
    for r in surface.resources:
        if r.description:
            out.append((None, f"resource:{r.uri}", r.description))
    if surface.server_info:
        out.append((None, "server_info", str(surface.server_info)))
    return out


def scan_injection(surface: ServerSurface) -> list[Finding]:
    findings: list[Finding] = []
    for tool, where, text in _texts(surface):
        for label, pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                findings.append(
                    Finding(
                        family="security",
                        code=f"S1-injection-{label}",
                        severity=Severity.HIGH,
                        tool=tool,
                        message=f"possible tool-poisoning / hidden-instruction marker in {where}: {label}",
                        remediation="remove hidden instructions from tool/resource text",
                        owasp_id=OWASP.TOOL_POISONING,
                        evidence={"where": where},
                    )
                )
    return findings


def scan_secrets(surface: ServerSurface) -> list[Finding]:
    findings: list[Finding] = []
    for tool, where, text in _texts(surface):
        for label, pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(
                    Finding(
                        family="security",
                        code=f"S2-secret-{label}",
                        severity=Severity.CRITICAL,
                        tool=tool,
                        message=f"hard-coded secret ({label}) exposed in {where}",
                        remediation="move secrets to env/secret store; never ship them in the surface",
                        owasp_id=OWASP.SECRET_EXPOSURE,
                        evidence={"where": where},
                    )
                )
        # high-entropy token heuristic (catches unlabeled keys)
        for token in re.findall(r"[A-Za-z0-9+/=_-]{32,}", text):
            if _shannon_entropy(token) > 4.3:
                findings.append(
                    Finding(
                        family="security",
                        code="S2-secret-high-entropy",
                        severity=Severity.HIGH,
                        tool=tool,
                        message=f"high-entropy string in {where} may be a leaked credential",
                        remediation="verify this is not a secret; move credentials out of the surface",
                        owasp_id=OWASP.SECRET_EXPOSURE,
                        evidence={"where": where, "entropy": round(_shannon_entropy(token), 2)},
                    )
                )
                break  # one entropy finding per text is enough
    return findings


def scan_dangerous_capabilities(surface: ServerSurface) -> list[Finding]:
    findings: list[Finding] = []
    for t in surface.tools:
        haystack = f"{t.name} {t.description or ''}"
        if _DANGEROUS.search(haystack):
            findings.append(
                Finding(
                    family="security",
                    code="S3-dangerous-capability",
                    severity=Severity.MEDIUM,
                    tool=t.name,
                    message=f"tool '{t.name}' exposes a command-execution capability (shell/exec/file/db)",
                    remediation="constrain the capability, require confirmation, or scope it down",
                    owasp_id=OWASP.COMMAND_INJECTION,
                )
            )
    return findings
