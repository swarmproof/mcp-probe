"""Path-traversal surface lint ``[fast]`` ``[static-ok]`` (#65) — OWASP MCP05.

Path traversal is the #1 MCP CVE class (82% of audited servers vulnerable): a tool takes a
``path``/``file``/``dir`` argument and joins it into a filesystem (or URL) path without
constraining it, so ``../../etc/passwd`` escapes the intended root. We can't *prove* a
server sanitizes its inputs from the surface alone — that's deep analysis for
``--deep-security``. What we *can* do, offline, is a cheap, high-precision **surface lint**:
flag a path-like parameter that advertises **no constraint at all** (no ``enum``, no
``pattern``, no ``format``, no ``const``) — the single cheapest signal of traversal risk.

Deliberately low false-positive (the whole Security-lite doctrine — deep scanners hit
~78% FP, so this adds signal not noise):
  * the path-name matcher is **token-exact** (``profile`` is not ``file``; ``compiler`` is
    not ``filepath``) — we tokenize snake_case / camelCase and match whole tokens only;
  * a parameter carrying **any** schema constraint is treated as handled and never flagged.
"""

from __future__ import annotations

import re
from typing import Any

from mcp_quality.models import Finding, ServerSurface, Severity
from mcp_quality.security.patterns import OWASP

# Whole-token names that denote a filesystem/URL path argument. Kept tight on purpose:
# matching is against *tokens* split out of the parameter name, never a substring, so
# "profile"/"compiler"/"filter" don't trip the "file" token.
_PATH_TOKENS = frozenset({
    "path", "paths", "filepath", "filepaths", "fpath",
    "file", "files", "filename", "filenames",
    "dir", "dirs", "directory", "directories", "dirpath",
    "folder", "folders", "pathname",
})

# Split a parameter name into lowercase word tokens across snake_case, kebab-case,
# dotted, and camelCase boundaries ("inputFilePath" -> input/file/path).
_TOKEN_SPLIT = re.compile(r"[^A-Za-z0-9]+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

# Schema keys that bound a string's value enough to defeat the naive-traversal signal.
_CONSTRAINT_KEYS = ("enum", "pattern", "format", "const")


def _tokens(name: str) -> set[str]:
    return {t.lower() for t in _TOKEN_SPLIT.split(name) if t}


def _is_path_param(name: str) -> bool:
    return bool(_tokens(name) & _PATH_TOKENS)


def _is_constrained(schema: Any) -> bool:
    """True when the param schema advertises *any* value constraint — then it's handled,
    not an unconstrained traversal surface, and we stay silent (low false-positive)."""
    if not isinstance(schema, dict):
        return False
    return any(schema.get(k) for k in _CONSTRAINT_KEYS)


def _unconstrained_path_params(input_schema: dict[str, Any]) -> list[str]:
    props = input_schema.get("properties")
    if not isinstance(props, dict):
        return []
    flagged: list[str] = []
    for param, schema in props.items():
        if _is_path_param(str(param)) and not _is_constrained(schema):
            flagged.append(str(param))
    return flagged


def scan_path_traversal(surface: ServerSurface) -> list[Finding]:
    """S4 path-traversal-surface findings — one per tool that exposes an unconstrained
    path-like parameter. Empty list when nothing matches (a clean/unmeasured surface is
    never zeroed; the engine folds this into the Security-lite score, ADR-006)."""
    findings: list[Finding] = []
    for t in surface.tools:
        flagged = _unconstrained_path_params(t.input_schema)
        if not flagged:
            continue
        shown = ", ".join(repr(p) for p in flagged)
        findings.append(
            Finding(
                family="security",
                code="S4-path-traversal-surface",
                severity=Severity.MEDIUM,
                tool=t.name,
                message=(
                    f"tool '{t.name}' takes path-like parameter(s) {shown} with no schema "
                    "constraint — a traversal payload (e.g. '../../etc/passwd') could escape "
                    "the intended root"
                ),
                remediation=(
                    "constrain the parameter (JSON Schema pattern/enum/format) and resolve + "
                    "validate the path against an allowed base directory server-side"
                ),
                owasp_id=OWASP.COMMAND_INJECTION,
                evidence={"params": flagged},
            )
        )
    return findings
