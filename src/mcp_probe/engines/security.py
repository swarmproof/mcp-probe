"""Security-lite engine ``[fast]`` + ``[net]`` integration (REQ-S1–S5).

Deliberately light (10% weight): a *floor*, not the point. Owns the easy 80% with
built-in offline lints (injection/tool-poisoning, secrets, dangerous capabilities) and
defers the hard 20% to mcp-scan / Cisco via ``--deep-security``. All findings carry
``source`` + ``owasp_id``; builtin and external findings are deduped on (owasp_id, tool)
with the higher-fidelity source winning. A CRITICAL finding hard-gates the overall grade.
"""

from __future__ import annotations

from mcp_probe.engines.base import EngineBase, penalty_score
from mcp_probe.models import FamilyScore, Finding, ProbeContext, Severity
from mcp_probe.security.adapters import (
    DEFAULT_ADAPTERS,
    dedup_findings,
    suppress_false_positives,
)
from mcp_probe.security.patterns import (
    scan_dangerous_capabilities,
    scan_injection,
    scan_secrets,
)


class SecurityEngine(EngineBase):
    name = "security"
    requires_live = False  # builtin lints are static-ok; --deep-security adds a [net] path
    requires_llm = False

    def __init__(self, adapters=None) -> None:
        self._adapters = adapters if adapters is not None else DEFAULT_ADAPTERS

    async def run(self, ctx: ProbeContext) -> FamilyScore:
        findings: list[Finding] = []
        findings += scan_injection(ctx.surface)  # S1 → LLM01
        findings += scan_secrets(ctx.surface)  # S2 → LLM02
        findings += scan_dangerous_capabilities(ctx.surface)  # S3 → LLM06

        deep_notes: dict[str, str] = {}
        if getattr(ctx.config, "deep_security", False):
            external = self._run_adapters(ctx, deep_notes)
            findings += suppress_false_positives(external)

        findings = dedup_findings(findings)

        score = penalty_score(findings)
        hard_gate = any(f.severity >= Severity.CRITICAL for f in findings)
        if hard_gate:
            score = min(score, 55.0)

        from mcp_probe.scoring import grade_for_score

        by_owasp: dict[str, int] = {}
        for f in findings:
            if f.owasp_id:
                by_owasp[f.owasp_id] = by_owasp.get(f.owasp_id, 0) + 1

        deep_status = deep_notes if getattr(ctx.config, "deep_security", False) else "not measured"
        return FamilyScore(
            family=self.name,
            score=score,
            grade=grade_for_score(score),
            hard_gate_tripped=hard_gate,
            findings=findings,
            metrics={
                "findings": len(findings),
                "by_owasp": by_owasp,
                "deep_security": deep_status,
            },
        )

    def _run_adapters(self, ctx: ProbeContext, notes: dict[str, str]) -> list[Finding]:
        target = getattr(ctx.config, "target", "") or getattr(ctx.config, "static_path", "") or ""
        collected: list[Finding] = []
        for adapter in self._adapters:
            if adapter.available():
                notes[adapter.name] = "ran"
                collected += adapter.scan(target)
            else:
                notes[adapter.name] = "not measured (scanner not on PATH)"
        return collected
