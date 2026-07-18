"""End-to-end scenarios against real fixture MCP servers (TEST-PLAN §4).

Marked ``e2e`` — they spawn a real stdio server (the same python running the tests, which
has the SDK installed). These assert the user-visible contract: grade + JSON + exit code.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mcp_probe.config import ProbeConfig
from mcp_probe.exit_codes import ExitCode
from mcp_probe.pipeline import run_probe

pytestmark = pytest.mark.e2e

SERVERS = Path(__file__).parent / "servers"


def _target(name: str) -> str:
    return f"{sys.executable} {SERVERS / name}"


async def test_e2e_1_happy_path_gets_an_a():
    cfg = ProbeConfig(target=_target("good_server.py"), families=("contract", "cost"))
    outcome = await run_probe(cfg)
    assert outcome.report.overall_grade == "A"
    assert outcome.report.families["contract"].hard_gate_tripped is False
    assert outcome.report.rubric_version
    assert outcome.exit_code == ExitCode.OK


async def test_e2e_2_gate_fails_bloated_server():
    cfg = ProbeConfig(target=_target("bloated_server.py"), families=("contract", "cost"), fail_under="A")
    outcome = await run_probe(cfg)
    assert outcome.exit_code == ExitCode.GATE_FAILURE
    assert outcome.report.families["cost"].score < 90


async def test_e2e_flaky_server_determinism_hard_gate():
    cfg = ProbeConfig(target=_target("flaky_server.py"), families=("contract", "cost"))
    outcome = await run_probe(cfg)
    contract = outcome.report.families["contract"]
    assert any(f.code == "C5-nondeterminism" for f in contract.findings)


async def test_e2e_writes_server_skips_destructive():
    cfg = ProbeConfig(target=_target("writes_server.py"), families=("contract",), allow_writes=False)
    outcome = await run_probe(cfg)
    assert "delete_record" in outcome.report.families["contract"].metrics["skipped_writes"]


async def test_e2e_7_static_mode_not_measured():
    dump = SERVERS / "dump.mcp.json"
    cfg = ProbeConfig(static_path=str(dump), families=("contract", "cost"))
    outcome = await run_probe(cfg)
    assert outcome.exit_code == ExitCode.OK
    # invocation is live-only → reported not measured, never zeroed (ADR-006)
    assert outcome.report.families["contract"].metrics["invocation_measured"] is False
    assert outcome.report.families["cost"].measured is True
