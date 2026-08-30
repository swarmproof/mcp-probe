"""Spec-surface engine ``[net]`` ``⊕ experimental`` (#33) — checks the capabilities *beyond
tools*: sampling, elicitation, resources.

Servers can talk back — ``sampling/createMessage`` (run something on the client's LLM),
``elicitation/create`` (ask the user for input), and advertised resources. These are where
a server can smuggle instructions into your model, phish your user, or dangle links that
don't resolve. They only surface at runtime, so this engine *drives* the read-only tools to
provoke server-originated messages, captures them via the harness (``client.capture``), and
grades what it observed.

**Experimental and opt-in** (``--experimental``): some target spec surfaces are still
stabilizing, so this family is reported but carries **zero rubric weight** — it never moves
the overall grade or trips the hard gate. Every sub-check degrades to *not measured* when
its capability was never exercised (ADR-006): no sampling seen → sampling is not scored.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from mcp_quality.connect.capture import CaptureLog
from mcp_quality.contract.schema import synthesize_args
from mcp_quality.engines.base import EngineBase, penalty_score
from mcp_quality.engines.contract import _is_write
from mcp_quality.models import FamilyScore, Finding, ProbeContext, Severity
from mcp_quality.security.patterns import _INJECTION_PATTERNS, OWASP

# Terms that make an elicitation "sensitive" — these belong behind a URL flow (OAuth-style),
# never a plain form the server scrapes back.
_SENSITIVE_TERMS = (
    "password", "passphrase", "secret", "api key", "api_key", "apikey", "token",
    "credit card", "card number", "cvv", "ssn", "social security", "private key", "seed phrase",
)


class SpecSurfaceEngine(EngineBase):
    name = "spec"
    requires_live = True  # sampling/elicitation/resources are runtime-only
    requires_llm = False
    deterministic = True
    experimental = True

    async def run(self, ctx: ProbeContext) -> FamilyScore:
        if ctx.client is None:  # static mode — nothing to exercise
            return self.not_measured("requires a live server (static mode)")

        await self._drive(ctx)  # provoke server-originated messages via read-only tools
        cap: CaptureLog = ctx.client.capture
        findings: list[Finding] = []
        measured: dict[str, bool] = {}
        metrics: dict[str, Any] = {}

        s_findings, measured["sampling"], s_metrics = self._grade_sampling(cap)
        r_findings, measured["resources"], r_metrics = await self._grade_resources(ctx)
        e_findings, measured["elicitation"] = self._grade_elicitation(cap)
        findings += s_findings + r_findings + e_findings
        metrics.update(s_metrics)
        metrics.update(r_metrics)

        if not any(measured.values()):
            return self.not_measured("no spec-surface capability exercised (sampling/resources/elicitation)")

        from mcp_quality.scoring import grade_for_score

        score = penalty_score(findings)
        metrics["exercised"] = sorted(k for k, v in measured.items() if v)
        return FamilyScore(
            family=self.name,
            score=score,
            grade=grade_for_score(score),
            hard_gate_tripped=False,  # experimental never gates the overall grade
            findings=findings,
            metrics=metrics,
        )

    # -- driver ---------------------------------------------------------------

    async def _drive(self, ctx: ProbeContext) -> None:
        """Invoke read-only tools once each so a server that uses sampling/elicitation emits
        its requests (captured passively by the harness). Writes are skipped (ADR-009)."""
        assert ctx.client is not None
        seed = getattr(ctx.config, "seed", 42)
        for tool in ctx.surface.tools:
            if _is_write(tool) and not getattr(ctx.config, "allow_writes", False):
                continue
            # a tool that errors is the contract engine's concern, not ours
            with contextlib.suppress(Exception):
                await ctx.client.call_tool(tool.name, synthesize_args(tool.input_schema, seed=seed))

    # -- sub-checks -----------------------------------------------------------

    def _grade_sampling(self, cap: CaptureLog) -> tuple[list[Finding], bool, dict[str, Any]]:
        if not cap.used_sampling:
            return [], False, {}
        findings: list[Finding] = []
        for msg in cap.sampling:
            text = msg.all_text()
            for label, pattern in _INJECTION_PATTERNS:
                if pattern.search(text):
                    findings.append(_f(
                        "SS1-sampling-injection", Severity.HIGH,
                        f"server-built sampling prompt carries an injection tell ({label})",
                        "don't embed instructions or echoed tool/user data in sampling prompts",
                        OWASP.CONTEXT_INJECTION,
                    ))
                    break
            if msg.include_context == "allServers":
                findings.append(_f(
                    "SS2-sampling-context-broad", Severity.MEDIUM,
                    "sampling requests includeContext=allServers — exposes other servers' context",
                    "scope includeContext to 'none' or 'thisServer'",
                    OWASP.CONTEXT_INJECTION,
                ))
        return findings, True, {"sampling_requests": len(cap.sampling)}

    async def _grade_resources(self, ctx: ProbeContext) -> tuple[list[Finding], bool, dict[str, Any]]:
        assert ctx.client is not None
        uris = [r.uri for r in ctx.surface.resources if getattr(r, "uri", "")]
        if not uris:
            return [], False, {}
        results = [await ctx.client.read_resource(uri) for uri in uris]
        unresolved = [r for r in results if not r.ok]
        findings = [_f(
            "SS3-resource-unresolved", Severity.MEDIUM,
            f"advertised resource does not resolve: {r.uri} ({r.error})",
            "ensure every advertised resource / resource_link actually resolves",
            None,
        ) for r in unresolved]
        metrics = {"resources_checked": len(uris), "resources_unresolved": len(unresolved)}
        return findings, True, metrics

    def _grade_elicitation(self, cap: CaptureLog) -> tuple[list[Finding], bool]:
        if not cap.used_elicitation:
            return [], False
        findings: list[Finding] = []
        for el in cap.elicitations:
            blob = (el.message + " " + json.dumps(el.schema)).lower()
            sensitive = any(term in blob for term in _SENSITIVE_TERMS)
            if el.mode == "form" and sensitive:
                findings.append(_f(
                    "SS4-elicitation-sensitive-form", Severity.HIGH,
                    "server elicits secrets/PII via a form the server can read — use URL mode",
                    "request sensitive input through URL-mode elicitation, not an inline form",
                    OWASP.SECRET_EXPOSURE,
                ))
            if el.mode == "url" and el.url and not el.url.startswith("https://"):
                findings.append(_f(
                    "SS5-elicitation-insecure-url", Severity.MEDIUM,
                    f"elicitation URL is not HTTPS: {el.url}",
                    "serve elicitation URLs over HTTPS",
                    OWASP.SECRET_EXPOSURE,
                ))
        return findings, True


def _f(code: str, sev: Severity, message: str, remediation: str, owasp: str | None) -> Finding:
    return Finding(family="spec", code=code, severity=sev, message=message,
                   remediation=remediation, owasp_id=owasp)
