"""Hardening tests (issue #14): header + per-family-gate parsing, the per-family gate
through the pipeline, and an opt-in real-scanner test."""

from __future__ import annotations

import pytest

from mcp_quality.cli import _config_from_args as cfg_from_args
from mcp_quality.cli import _parse_family_gates, _parse_headers, build_parser
from mcp_quality.config import ProbeConfig
from mcp_quality.connect.discover import surface_from_tools
from mcp_quality.exit_codes import ExitCode
from mcp_quality.pipeline import run_probe

# -- parsing ------------------------------------------------------------------

def test_parse_headers():
    assert _parse_headers(["Authorization: Bearer xyz", "X-Env: prod"]) == {
        "Authorization": "Bearer xyz", "X-Env": "prod"
    }
    assert _parse_headers(None) is None
    assert _parse_headers(["nonsense"]) is None


def test_parse_family_gates():
    assert _parse_family_gates("Contract:A,Security:B") == {"contract": "A", "security": "B"}
    assert _parse_family_gates(None) is None


def test_cli_threads_headers_and_gates_into_config():
    args = build_parser().parse_args([
        "run", "https://host/mcp",
        "--header", "Authorization: Bearer t",
        "--fail-under-family", "Contract:A",
    ])
    config = cfg_from_args(args)
    assert config.headers == {"Authorization": "Bearer t"}
    assert config.fail_under_family == {"contract": "A"}


# -- per-family gate through the pipeline -------------------------------------

BLOAT = [
    {"name": f"t{i}", "description": "word " * 300, "inputSchema": {"type": "object"},
     "annotations": {"readOnlyHint": True}}
    for i in range(20)
]


async def test_fail_under_family_trips_on_weak_family():
    # Cost will be well below A on this bloated surface → the per-family gate fails.
    cfg = ProbeConfig(families=("contract", "cost"), fail_under_family={"cost": "A"})
    outcome = await run_probe(cfg, surface=surface_from_tools(BLOAT))
    assert outcome.report.families["cost"].grade != "A"
    assert outcome.exit_code == ExitCode.GATE_FAILURE


async def test_fail_under_family_passes_when_met():
    good = [{"name": "get_x", "description": "Return x. Example: get_x().",
             "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": True}}]
    cfg = ProbeConfig(families=("contract", "cost"), fail_under_family={"cost": "A", "contract": "A"})
    outcome = await run_probe(cfg, surface=surface_from_tools(good))
    assert outcome.exit_code == ExitCode.OK


# -- opt-in real scanner ------------------------------------------------------

@pytest.mark.deep_security
def test_real_scanner_normalizes_output():
    from mcp_quality.security.adapters import McpScanAdapter

    adapter = McpScanAdapter()
    if not adapter.available():
        pytest.skip("no snyk-agent-scan / mcp-scan on PATH")
    findings = adapter.scan("tests/servers/dump.mcp.json")
    assert isinstance(findings, list)  # normalized Finding[]; may be empty
