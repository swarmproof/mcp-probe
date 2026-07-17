"""``--deep-security`` integration adapters (REQ-S4, ARCHITECTURE §8).

A normalizing shell-out layer, **not** a reimplementation (ADR-005): cooperate with the
incumbents. Each adapter checks whether its scanner is on PATH, invokes it against the
same target, and normalizes the native JSON into our :class:`Finding` (carrying
``source`` + ``owasp_id``). A missing scanner is reported "not measured", never a failure
(NFR-8). Parsing is intentionally defensive — external JSON shapes drift, so we extract
severity/title/tool from whatever keys appear rather than assuming a fixed schema.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Protocol

from mcp_probe.models import Finding, FindingSource, Severity

_SEVERITY_WORDS = {
    "critical": Severity.CRITICAL,
    "high": Severity.HIGH,
    "error": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "warning": Severity.MEDIUM,
    "moderate": Severity.MEDIUM,
    "low": Severity.LOW,
    "info": Severity.INFO,
    "informational": Severity.INFO,
}


def _severity_of(raw: Any) -> Severity:
    if isinstance(raw, (int, float)):
        return Severity(max(0, min(4, int(raw))))
    return _SEVERITY_WORDS.get(str(raw).strip().lower(), Severity.MEDIUM)


class SecurityAdapter(Protocol):
    name: str
    source: FindingSource
    binary: str

    def available(self) -> bool: ...

    def scan(self, target: str) -> list[Finding]: ...


class _ShellAdapter:
    """Common shell-out + defensive JSON normalization."""

    name = "shell"
    source: FindingSource = "builtin"
    binary = ""
    args: tuple[str, ...] = ()

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def scan(self, target: str) -> list[Finding]:
        if not self.available():
            return []
        try:
            proc = subprocess.run(  # noqa: S603 - invoking a user-approved scanner
                [self.binary, *self.args, target],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (subprocess.TimeoutExpired, OSError):
            return []
        return self._parse(proc.stdout)

    def _parse(self, stdout: str) -> list[Finding]:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return []
        return [self._normalize(item) for item in self._iter_issues(data)]

    def _iter_issues(self, data: Any) -> list[dict[str, Any]]:
        # Accept {"issues":[...]}, {"findings":[...]}, {"results":[...]}, or a bare list.
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        for key in ("issues", "findings", "results", "vulnerabilities"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
        return []

    def _normalize(self, item: dict[str, Any]) -> Finding:
        title = item.get("title") or item.get("name") or item.get("message") or item.get("rule") or "issue"
        severity = _severity_of(item.get("severity") or item.get("level") or "medium")
        tool = item.get("tool") or item.get("target") or item.get("location")
        owasp = item.get("owasp") or item.get("owasp_id") or item.get("category")
        confidence = item.get("confidence")
        return Finding(
            family="security",
            code=f"{self.source}-{item.get('id') or item.get('rule') or 'finding'}",
            severity=severity,
            tool=str(tool) if tool else None,
            message=str(title),
            owasp_id=str(owasp) if owasp else None,
            source=self.source,
            evidence={"confidence": confidence} if confidence is not None else None,
        )


class McpScanAdapter(_ShellAdapter):
    name = "mcp-scan"
    source: FindingSource = "mcp-scan"
    binary = "mcp-scan"
    args = ("scan", "--json")


class CiscoAdapter(_ShellAdapter):
    name = "cisco-mcp-scanner"
    source: FindingSource = "cisco"
    binary = "mcp-scanner"
    args = ("--json",)


DEFAULT_ADAPTERS: list[SecurityAdapter] = [McpScanAdapter(), CiscoAdapter()]


def suppress_false_positives(findings: list[Finding], *, min_confidence: float = 0.4) -> list[Finding]:
    """Drop low-confidence external flags (the YARA ~78%-FP problem, ARCHITECTURE §8)."""
    kept = []
    for f in findings:
        conf = (f.evidence or {}).get("confidence") if f.evidence else None
        if conf is not None and isinstance(conf, (int, float)) and conf < min_confidence:
            continue
        kept.append(f)
    return kept


def dedup_findings(findings: list[Finding]) -> list[Finding]:
    """Merge duplicates on (owasp_id, tool), preferring the higher-fidelity source
    (external scanners over builtin) and the higher severity (REQ-S5). Findings without a
    meaningful (owasp_id, tool) key are never merged — they pass through untouched."""
    fidelity = {"builtin": 0, "mcp-xray": 1, "cisco": 2, "mcp-scan": 3}
    best: dict[tuple[str, str | None], Finding] = {}
    passthrough: list[Finding] = []
    for f in findings:
        if f.owasp_id is None:
            passthrough.append(f)
            continue
        key = (f.owasp_id, f.tool)
        cur = best.get(key)
        if cur is None or (f.severity, fidelity.get(f.source, 0)) > (
            cur.severity,
            fidelity.get(cur.source, 0),
        ):
            best[key] = f
    return [*best.values(), *passthrough]
