"""2026-07-28 (stateless) conformance grading (#32) — pure, version-aware, black-box.

The MCP spec is mid-transition. The 2026-07-28 revision drops the ``initialize`` /
``initialized`` handshake and session IDs, makes ``server/discover`` mandatory, requires
per-request ``_meta``, and forbids ``tools/list`` from varying per connection. Servers are
still catching up, so we **grade the transition, require neither path**: a legacy server
gets a gentle forward-compat nudge, not a failure; a server that *claims* the stateless
revision but breaks its rules gets a real finding.

This module is pure — it takes the signals the transport managed to observe (each a
tri-state: True / False / None-for-not-measured) and returns findings + a readiness map.
The transport (the only SDK-aware module) fills the signals in as far as the SDK allows;
anything it can't probe stays ``None`` and is reported "not measured", never zeroed
(ADR-006). That keeps the grader trivially testable with crafted records — no live server.
"""

from __future__ import annotations

from typing import Any

from mcp_quality.models import Finding, Severity

# The first spec revision that mandates the stateless (server/discover + _meta) path.
STATELESS_REVISION = "2026-07-28"


def on_stateless_revision(protocol_version: str) -> bool:
    """ISO-date protocol versions compare lexicographically, so a string ``>=`` is correct."""
    return bool(protocol_version) and protocol_version >= STATELESS_REVISION


def _f(code: str, sev: Severity, message: str, remediation: str, **evidence: Any) -> Finding:
    return Finding(
        family="contract", code=code, severity=sev, message=message,
        remediation=remediation, evidence=evidence or {},
    )


def grade_stateless_conformance(
    protocol_version: str,
    *,
    discover_ok: bool | None = None,
    tools_list_stable: bool | None = None,
    meta_enforced: bool | None = None,
    supported_versions: list[str] | None = None,
) -> tuple[list[Finding], dict[str, Any]]:
    """Grade stateless-readiness from observed signals. Returns (findings, readiness).

    Each signal is tri-state: ``True`` observed-good, ``False`` observed-bad, ``None`` not
    measured. Findings scale with intent: a server *on* the stateless revision that breaks a
    rule earns a real (MEDIUM) finding; a legacy server merely gets forward-compat guidance.
    """
    findings: list[Finding] = []
    stateless = on_stateless_revision(protocol_version)

    # server/discover — mandatory on the stateless revision; optional (nice-to-have) before it.
    if discover_ok is False:
        if stateless:
            findings.append(_f(
                "C12-no-server-discover", Severity.MEDIUM,
                f"negotiated {protocol_version} (stateless) but server/discover is not implemented",
                "implement server/discover — it is required by the 2026-07-28 revision",
                protocol_version=protocol_version,
            ))
        else:
            findings.append(_f(
                "C10-forward-compat", Severity.LOW,
                "server/discover is not implemented (optional today, required by 2026-07-28)",
                "adopt the stateless server/discover path when your SDK ships it",
                protocol_version=protocol_version,
            ))

    # tools/list stability — a genuine bug on ANY revision: per-connection variance means an
    # agent's tool set depends on which connection it happened to open.
    if tools_list_stable is False:
        findings.append(_f(
            "C12-tools-list-unstable", Severity.MEDIUM,
            "tools/list differs across two fresh connections — the surface is per-connection",
            "return an identical tool list on every connection (no per-session leakage)",
        ))

    # _meta enforcement — only a finding when the server is on the revision that requires it.
    if meta_enforced is False and stateless:
        findings.append(_f(
            "C12-meta-unenforced", Severity.LOW,
            f"negotiated {protocol_version} but requests missing required _meta were accepted",
            "reject requests missing required _meta fields per the stateless revision",
        ))

    readiness: dict[str, Any] = {
        "protocol_version": protocol_version or None,
        "on_stateless_revision": stateless,
        "server_discover": discover_ok,
        "tools_list_stable": tools_list_stable,
        "meta_enforced": meta_enforced,
        "supported_versions": supported_versions or [],
    }
    return findings, readiness
