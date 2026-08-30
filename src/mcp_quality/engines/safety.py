"""Safety-Contract engine ``[fast]`` — do a tool's safety claims match its shape? (#28)

Hosts use tool annotations (`readOnlyHint` / `destructiveHint` / `idempotentHint`) to
decide whether to auto-approve a call or ask the user first. But the handler runs
regardless of what it claims, so a destructive tool flagged read-only silently skips the
confirmation dialog. This family grades the *truthfulness* of those claims from the tool
surface — static, so it runs even in offline `static` mode (ideal for registries).

Static by design: verifying "this read-only tool actually mutates" needs a sandbox we
don't have, so we grade declarations + name/verb contradictions (high value, zero false
positives), not live write behaviour.
"""

from __future__ import annotations

import re

from mcp_quality.engines.base import EngineBase, penalty_score
from mcp_quality.models import FamilyScore, Finding, ProbeContext, Severity, ToolDef
from mcp_quality.security.patterns import OWASP

# Names that clearly imply a state-changing tool.
_WRITE_VERB = re.compile(
    r"^(delete|remove|drop|destroy|purge|create|update|set|write|put|post|patch|send|"
    r"insert|modify|edit|rename|move|archive|revoke|reset|cancel|approve|pay|charge|"
    r"transfer|deploy|publish|merge|close|disable|enable)([_A-Z]|$)",
    re.I,
)
# Params that make a write safely retryable.
_IDEMPOTENCY_PARAMS = {"idempotency_key", "idempotencykey", "request_id", "requestid",
                       "client_token", "clienttoken", "dedup_key", "dedupe_key", "nonce"}
_SIDE_EFFECT_NOTE = re.compile(r"\b(idempotent|side.?effect|exactly.?once|at.?most.?once|retry)\b", re.I)


def _write_named(tool: ToolDef) -> bool:
    return bool(_WRITE_VERB.match(tool.name))


def check_safety_contract(tool: ToolDef) -> list[Finding]:
    """Static annotation-truthfulness + retry-safety checks for one tool."""
    findings: list[Finding] = []
    ann = tool.annotations or {}
    props = set(map(str.lower, (tool.input_schema or {}).get("properties", {})))
    write_named = _write_named(tool)

    # SC2 — the claim contradicts the name (the dangerous lie: skips host confirmation).
    if write_named and ann.get("readOnlyHint") is True:
        findings.append(_f("SC2-annotation-untrue", Severity.HIGH, tool.name,
                           f"'{tool.name}' is named like a state change but declares readOnlyHint=true",
                           "correct the annotation — a host will auto-approve this without confirmation",
                           OWASP.PRIVILEGE_ESCALATION))
    if write_named and ann.get("destructiveHint") is False:
        findings.append(_f("SC2-annotation-untrue", Severity.HIGH, tool.name,
                           f"'{tool.name}' is named like a state change but declares destructiveHint=false",
                           "correct the annotation so hosts can gate the call",
                           OWASP.PRIVILEGE_ESCALATION))

    # SC1 — a write-intent tool with no safety annotations at all (host can't reason).
    if write_named and not ann:
        findings.append(_f("SC1-annotation-missing", Severity.LOW, tool.name,
                           f"'{tool.name}' looks state-changing but declares no annotations",
                           "declare readOnlyHint/destructiveHint/idempotentHint so hosts can gate it",
                           OWASP.PRIVILEGE_ESCALATION))

    # SC3 — a write with no retry-safety story → duplicate-write risk under retry storms.
    if write_named and not tool.is_read_only:
        declared_idempotent = ann.get("idempotentHint") is True
        has_key = bool(props & _IDEMPOTENCY_PARAMS)
        documents = bool(_SIDE_EFFECT_NOTE.search(tool.description or ""))
        if not (declared_idempotent or has_key or documents):
            findings.append(_f("SC3-retry-unsafe", Severity.MEDIUM, tool.name,
                               f"'{tool.name}' is a write with no idempotency signal — retries may duplicate",
                               "declare idempotentHint, accept an idempotency key, or document side effects",
                               None))
    return findings


class SafetyEngine(EngineBase):
    name = "safety"
    requires_live = False  # static-ok — pure surface analysis
    requires_llm = False

    async def run(self, ctx: ProbeContext) -> FamilyScore:
        findings: list[Finding] = []
        for tool in ctx.surface.tools:
            findings.extend(check_safety_contract(tool))

        score = penalty_score(findings)
        # A tool lying about its safety class (SC2) bypasses host confirmation — cap at C.
        hard_gate = any(f.code.startswith("SC2") for f in findings)
        if hard_gate:
            score = min(score, 55.0)

        from mcp_quality.scoring import grade_for_score

        by_code: dict[str, int] = {}
        for f in findings:
            by_code[f.code] = by_code.get(f.code, 0) + 1
        return FamilyScore(
            family=self.name,
            score=score,
            grade=grade_for_score(score),
            hard_gate_tripped=hard_gate,
            findings=findings,
            metrics={"findings": len(findings), "by_code": by_code},
        )


def _f(code: str, sev: Severity, tool: str, message: str, remediation: str,
       owasp: str | None) -> Finding:
    return Finding(family="safety", code=code, severity=sev, tool=tool,
                   message=message, remediation=remediation, owasp_id=owasp)
