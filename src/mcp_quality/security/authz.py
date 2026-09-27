"""Authorization least-privilege lints ``[fast]`` ``[static-ok]`` (#48) — OWASP MCP07.

A server that requests broad OAuth scopes it never exercises is a standing over-grant; an
issuer with no resource indicator invites audience confusion (a token minted for one
resource replayed against another). These grade the **advertised** authorization metadata
(the ``authorization`` block a server declares in its capabilities / dump) — so they run
offline and degrade to *not measured* when a server declares no auth at all (ADR-006):
stdio servers with no OAuth aren't punished, they're simply not graded on this axis.

Deliberately low false-positive: A1 fires only on unambiguous over-grant (wildcard/admin
scopes, or a write-scope on a wholly read-only tool set), not on a guessed scope→tool map.
"""

from __future__ import annotations

import re
from typing import Any

from mcp_quality.models import Finding, ServerSurface, Severity
from mcp_quality.security.patterns import OWASP

_AUTH_KEYS = ("authorization", "oauth", "oauth2", "auth")
# Scope tokens that grant far more than any single tool needs.
_BROAD_SCOPE = re.compile(r"^(?:\*|all|admin|root|full_access|superuser|write:\*|.*:\*)$", re.I)
# Scope substrings implying state change — an over-grant on a read-only tool set.
_WRITE_SCOPE = re.compile(r"\b(write|manage|admin|delete|modify|create|full)\b", re.I)


def auth_block(surface: ServerSurface) -> dict[str, Any] | None:
    """The advertised authorization metadata, if the server declared any."""
    caps = surface.capabilities or {}
    for key in _AUTH_KEYS:
        value = caps.get(key)
        if isinstance(value, dict) and value:
            return value
    return None


def _scopes(auth: dict[str, Any]) -> list[str]:
    raw = (
        auth.get("scopes") or auth.get("scopes_supported")
        or auth.get("required_scopes") or auth.get("scope") or []
    )
    if isinstance(raw, str):  # OAuth space-delimited scope string
        return raw.split()
    return [str(s) for s in raw] if isinstance(raw, list) else []


def _resource_indicator(auth: dict[str, Any]) -> Any:
    return (
        auth.get("resource") or auth.get("resource_indicators")
        or auth.get("audience") or auth.get("aud")
    )


def scan_authorization(surface: ServerSurface) -> list[Finding]:
    """A1/A2/A3 authorization-hygiene findings. Empty list when no auth is declared —
    the engine reports the authz axis as 'not measured' in that case."""
    auth = auth_block(surface)
    if auth is None:
        return []

    findings: list[Finding] = []
    all_read_only = bool(surface.tools) and all(t.is_read_only for t in surface.tools)
    scopes = _scopes(auth)

    # A1 — scope over-grant.
    broad = [s for s in scopes if _BROAD_SCOPE.match(s)]
    if broad:
        findings.append(_f(
            "A1-scope-overgrant", Severity.MEDIUM,
            f"declares broad OAuth scope(s) {broad} — far more than any tool needs",
            "request the narrowest scopes the tool set actually uses (least privilege)",
        ))
    write_scopes = [s for s in scopes if _WRITE_SCOPE.search(s) and s not in broad]
    if all_read_only and write_scopes:
        findings.append(_f(
            "A1-scope-overgrant", Severity.MEDIUM,
            f"every tool is read-only but the server requests write scope(s) {write_scopes}",
            "drop write/manage scopes — a read-only tool set should request read scopes only",
        ))

    # A2 — issuer / resource-indicator (audience) hygiene.
    resource = _resource_indicator(auth)
    issuer = auth.get("issuer") or auth.get("iss")
    if issuer and not resource:
        findings.append(_f(
            "A2-audience-hygiene", Severity.MEDIUM,
            "authorization declares an issuer but no resource indicator (audience)",
            "declare a concrete resource indicator so tokens can't be replayed cross-audience",
        ))
    if resource in ("*", ["*"]):
        findings.append(_f(
            "A2-audience-hygiene", Severity.MEDIUM,
            "resource indicator (audience) is a wildcard — any audience is accepted",
            "pin the resource indicator to this server's concrete resource URI",
        ))

    # A3 — auth flows must be HTTPS.
    for key in ("issuer", "authorization_endpoint", "token_endpoint", "resource"):
        url = auth.get(key)
        if isinstance(url, str) and url.startswith("http://"):
            findings.append(_f(
                "A3-insecure-authz", Severity.HIGH,
                f"authorization {key} is not HTTPS: {url}",
                "serve all authorization endpoints over HTTPS",
            ))
    return findings


def _f(code: str, sev: Severity, message: str, remediation: str) -> Finding:
    return Finding(family="security", code=code, severity=sev, message=message,
                   remediation=remediation, owasp_id=OWASP.AUTHZ)
