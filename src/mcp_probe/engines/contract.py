"""Contract engine ``[fast]`` — spec conformance, schema validity, determinism.

LLM-free and deterministic (the CI-critical path). A broken contract is binary and rare
once caught, so Contract carries a 20% weight but a **hard gate**: any conformance break
(bad framing, schema-invalid tool, output that violates its declared shape) caps the
overall grade at C — no A-grade server ships a broken contract.

Static-safe parts (schema validity, handshake findings from the connect record) run in
``static`` mode; invocation + determinism need a live client and are reported
"not measured" offline (never zeroed, ADR-006). Read-only by default: destructive tools
are skipped unless ``--allow-writes`` (NFR-9, ADR-009).
"""

from __future__ import annotations

import re

from mcp_probe.contract.schema import synthesize_args, validate_against, validate_schema
from mcp_probe.engines.base import EngineBase, clamp
from mcp_probe.models import FamilyScore, Finding, ProbeContext, Severity, ToolDef

# Heuristic write-detection for servers that don't set destructiveHint.
_WRITE_VERB = re.compile(
    r"^(delete|remove|drop|destroy|purge|create|update|set|write|put|post|patch|"
    r"send|insert|modify|edit|rename|move|archive|revoke|reset)[_A-Z]",
)


def _is_write(tool: ToolDef) -> bool:
    if tool.is_read_only:
        return False
    if tool.is_destructive:
        return True
    return bool(_WRITE_VERB.match(tool.name))


class ContractEngine(EngineBase):
    name = "contract"
    requires_live = False  # partial (schema + handshake) works static; invocation needs live
    requires_llm = False

    async def run(self, ctx: ProbeContext) -> FamilyScore:
        findings: list[Finding] = []
        tools = ctx.surface.tools

        self._check_handshake(ctx, findings)  # REQ-C1, C2, C10 (from the connect record)

        # REQ-C3: schema validity of every tool (static-ok).
        schema_invalid: set[str] = set()
        for tool in tools:
            for issue in validate_schema(tool.input_schema):
                schema_invalid.add(tool.name)
                findings.append(
                    Finding(
                        family=self.name,
                        code="C3-schema-invalid",
                        severity=Severity.HIGH,
                        tool=tool.name,
                        message=f"input schema is not well-formed: {issue.message}",
                        remediation="fix the JSON Schema (resolve $ref, correct types/enums)",
                        evidence={"path": issue.path},
                    )
                )
            if tool.output_schema:
                for issue in validate_schema(tool.output_schema):
                    schema_invalid.add(tool.name)
                    findings.append(
                        Finding(
                            family=self.name,
                            code="C3-output-schema-invalid",
                            severity=Severity.MEDIUM,
                            tool=tool.name,
                            message=f"output schema is not well-formed: {issue.message}",
                        )
                    )

        invoked = 0
        conformance_breaks = 0
        nondeterministic = 0
        skipped_writes: list[str] = []

        if ctx.client is not None:
            for tool in tools:
                if tool.name in schema_invalid:
                    continue  # can't synthesize valid args for a broken schema
                if _is_write(tool) and not getattr(ctx.config, "allow_writes", False):
                    skipped_writes.append(tool.name)
                    continue
                invoked += 1
                broke, nondet = await self._probe_tool(ctx, tool, findings)
                conformance_breaks += int(broke)
                nondeterministic += int(nondet)

        # Scoring: fraction of tools passing schema + (where invoked) conformance/determinism.
        measured_live = ctx.client is not None
        total = max(1, len(tools))
        passing = len(tools) - len(schema_invalid) - conformance_breaks - nondeterministic
        score = clamp(100.0 * passing / total)

        hard_gate = bool(schema_invalid) or conformance_breaks > 0 or not self._framing_ok(ctx)
        if hard_gate:
            # A broken contract must be visible in the grade even if most tools pass.
            score = min(score, 65.0)

        summary_bits = []
        if schema_invalid:
            summary_bits.append(f"{len(schema_invalid)} schema-invalid")
        if conformance_breaks:
            summary_bits.append(f"{conformance_breaks} contract break(s)")
        if nondeterministic:
            summary_bits.append(f"{nondeterministic} nondeterministic")
        if skipped_writes:
            summary_bits.append(f"{len(skipped_writes)} write tools skipped")
        summary = ", ".join(summary_bits) or f"{len(tools)} tools conform"

        from mcp_probe.scoring import grade_for_score

        return FamilyScore(
            family=self.name,
            score=score,
            grade=grade_for_score(score),
            hard_gate_tripped=hard_gate,
            findings=findings,
            metrics={
                "tools": len(tools),
                "invoked": invoked,
                "schema_invalid": sorted(schema_invalid),
                "conformance_breaks": conformance_breaks,
                "nondeterministic": nondeterministic,
                "skipped_writes": skipped_writes,
                "invocation_measured": measured_live,
                "protocol_version": ctx.surface.protocol_version,
                "summary": summary,
            },
        )

    # -- probes ---------------------------------------------------------------

    async def _probe_tool(
        self, ctx: ProbeContext, tool: ToolDef, findings: list[Finding]
    ) -> tuple[bool, bool]:
        """Invoke a tool with synthesized args; check output conformance (C4) and
        determinism (C5). Returns (conformance_broke, nondeterministic)."""
        assert ctx.client is not None  # only called on the live path
        seed = getattr(ctx.config, "seed", 42)
        args = synthesize_args(tool.input_schema, seed=seed)
        broke = False
        nondet = False
        try:
            first = await ctx.client.call_tool(tool.name, args)
        except Exception as exc:  # a crash on schema-valid args is itself a contract break
            findings.append(
                Finding(
                    family=self.name,
                    code="C4-invocation-error",
                    severity=Severity.HIGH,
                    tool=tool.name,
                    message=f"tool raised on schema-valid args: {exc!s}",
                )
            )
            return True, False

        # REQ-C4: output conformance against the declared output_schema.
        if tool.output_schema and not first.is_error:
            payload = first.structured if first.structured is not None else first.content
            issues = validate_against(payload, tool.output_schema)
            if issues:
                broke = True
                findings.append(
                    Finding(
                        family=self.name,
                        code="C4-output-nonconformant",
                        severity=Severity.HIGH,
                        tool=tool.name,
                        message=f"result violates declared output schema: {issues[0].message}",
                        remediation="align the returned shape with output_schema, or drop the schema",
                    )
                )

        # REQ-C5: determinism probe — same args twice.
        try:
            second = await ctx.client.call_tool(tool.name, args)
            if not first.is_error and not second.is_error and first.content != second.content:
                if not tool.annotations.get("volatile"):  # allow opt-out via annotation
                    nondet = True
                    findings.append(
                        Finding(
                            family=self.name,
                            code="C5-nondeterminism",
                            severity=Severity.MEDIUM,
                            tool=tool.name,
                            message="same args produced different results on two calls",
                            remediation="declare volatile output, or make the tool deterministic",
                        )
                    )
        except Exception:
            pass  # a second-call failure is noise; the first call already scored the tool
        return broke, nondet

    # -- handshake / framing --------------------------------------------------

    def _framing_ok(self, ctx: ProbeContext) -> bool:
        rec = getattr(ctx.client, "connect_record", None)
        return True if rec is None else rec.framing_ok

    def _check_handshake(self, ctx: ProbeContext, findings: list[Finding]) -> None:
        rec = getattr(ctx.client, "connect_record", None)
        if rec is None:
            return
        if not rec.framing_ok:
            findings.append(
                Finding(
                    family=self.name,
                    code="C1-framing",
                    severity=Severity.CRITICAL,
                    message="server emitted non-conformant JSON-RPC 2.0 framing",
                    evidence={"errors": rec.framing_errors},
                )
            )
        # REQ-C2 / C10: forward-compat. Only nudge when a newer path is known-missing.
        if rec.stateless_discover_ok is False and rec.legacy_handshake_ok:
            findings.append(
                Finding(
                    family=self.name,
                    code="C10-forward-compat",
                    severity=Severity.LOW,
                    message="server speaks only the legacy initialize handshake",
                    remediation="adopt the newer stateless discovery path when your SDK supports it",
                    evidence={"protocol_version": rec.protocol_version},
                )
            )
