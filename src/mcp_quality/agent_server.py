"""Agentic-native interface — mcp-quality exposed **as an MCP server** (`mcp-quality mcp`).

A coding agent (Claude Code, Cursor, any MCP client) adds this and calls the suite as tools
in its own loop, instead of a human shelling out to the CLI:

- ``grade_server`` — score a server (or a tools/list dump) → grade + verdict + findings
- ``explain_findings`` — just the issues, each with its fix, most-severe first
- ``propose_fixes`` — proposed description rewrites (returned, never written)

Read-only by design: it grades and proposes, it never mutates the caller's files (apply is
the agent's call). It reuses the exact engine the CLI/registry use (``run_probe`` + the
report), so results match ``mcp-quality run``. The tool functions are plain and importable, so
they're testable without standing up a server.
"""

from __future__ import annotations

from typing import Any

from mcp_quality.config import ProbeConfig
from mcp_quality.pipeline import run_probe
from mcp_quality.report import report_to_dict

# Agent-loop default: the fast, keyless families + safety/security + offline legibility lints.
# Performance (a load test) is opt-in via ``families`` — too heavy for a tight iterate loop.
_DEFAULT_FAMILIES = ("contract", "cost", "legibility", "security", "safety")


async def _grade(
    target: str, tools: list[dict[str, Any]] | None, families: list[str] | None, model: str
) -> Any:
    """Run the suite against a live ``target`` command/URL or an in-memory ``tools`` dump."""
    fams = tuple(families) if families else _DEFAULT_FAMILIES
    config = ProbeConfig(
        families=fams,
        model=model or None,
        target=target or "",
        static_path="<mcp>" if tools is not None else None,
    )
    if tools is not None:
        from mcp_quality.connect import surface_from_payload

        outcome = await run_probe(config, surface=surface_from_payload({"tools": tools}))
    else:
        outcome = await run_probe(config)  # live connect to target
    return outcome.report


def _findings(report: Any) -> list[dict[str, Any]]:
    ranked = sorted(report.all_findings(), key=lambda f: f.severity, reverse=True)
    return [
        {"family": f.family, "code": f.code, "severity": f.severity.name.lower(),
         "tool": f.tool, "message": f.message, "remediation": f.remediation}
        for f in ranked
    ]


def build_mcp_server() -> Any:
    """Construct the mcp-quality MCP server. Imported lazily so the base CLI needs no server deps."""
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer("mcp-quality")

    @mcp.tool(description=(
        "Grade an MCP server across the quality families and return the letter grade, the "
        "pass/fail verdict, and all findings. Pass `target` (a stdio command or an http URL) "
        "to grade a live server, or `tools` (a tools/list array) to grade offline. Optional "
        "`families` and `model` (e.g. 'ollama:qwen2.5-3b' for the full legibility probe)."
    ))
    async def grade_server(
        target: str = "", tools: list[dict[str, Any]] | None = None,
        families: list[str] | None = None, model: str = "",
    ) -> dict[str, Any]:
        try:
            report = await _grade(target, tools, families, model)
        except Exception as exc:
            return {"error": str(exc)}
        return report_to_dict(report, include_meta=False)

    @mcp.tool(description=(
        "Return just the findings for a server (or tools/list dump), most-severe first, each "
        "with its remediation — the actionable list to fix. Same inputs as grade_server."
    ))
    async def explain_findings(
        target: str = "", tools: list[dict[str, Any]] | None = None,
        families: list[str] | None = None, model: str = "",
    ) -> dict[str, Any]:
        try:
            report = await _grade(target, tools, families, model)
        except Exception as exc:
            return {"error": str(exc)}
        return {"grade": report.overall_grade, "findings": _findings(report)}

    @mcp.tool(description=(
        "Propose clearer tool-description rewrites for the legibility issues found (returned, "
        "not written — apply them yourself). Needs `model` for the comprehension probe. Same "
        "`target`/`tools` inputs."
    ))
    async def propose_fixes(
        target: str = "", tools: list[dict[str, Any]] | None = None, model: str = "ollama:qwen2.5-3b",
    ) -> dict[str, Any]:
        try:
            report = await _grade(target, tools, ["legibility"], model)
        except Exception as exc:
            return {"error": str(exc)}
        rewrites = [
            {"tool": f.tool, "old": f.evidence.get("old", ""), "rewrite": f.evidence.get("rewrite", "")}
            for f in report.all_findings()
            if f.code == "L5-rewrite" and f.evidence
        ]
        return {"rewrites": rewrites}

    return mcp


def serve_mcp(transport: str = "stdio") -> None:  # pragma: no cover - runs a server
    build_mcp_server().run(transport=transport)
