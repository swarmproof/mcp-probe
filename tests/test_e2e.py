"""End-to-end scenarios against real fixture MCP servers (TEST-PLAN §4).

Marked ``e2e`` — they spawn a real stdio server (the same python running the tests, which
has the SDK installed). These assert the user-visible contract: grade + JSON + exit code.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mcp_quality.config import ProbeConfig
from mcp_quality.exit_codes import ExitCode
from mcp_quality.pipeline import run_probe

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


async def test_e2e_error_path_clean_on_good_server():
    # REQ-C9: a conformant server handles malformed input without crashing.
    cfg = ProbeConfig(target=_target("good_server.py"), families=("contract",))
    outcome = await run_probe(cfg)
    contract = outcome.report.families["contract"]
    assert contract.metrics["error_path_crashes"] == 0
    assert not any(f.code == "C9-error-path" for f in contract.findings)
    # #25: error-recovery affordance is measured live and in range.
    aff = contract.metrics["error_recovery_affordance"]
    assert aff is not None and 0 <= aff <= 100


async def test_e2e_stateless_tools_list_stable_on_good_server():
    # #32: the transport opens a second fresh connection; a well-behaved server returns an
    # identical tools/list, so the black-box stability probe measures True (no C12 finding).
    cfg = ProbeConfig(target=_target("good_server.py"), families=("contract",))
    outcome = await run_probe(cfg)
    readiness = outcome.report.families["contract"].metrics["stateless_readiness"]
    assert readiness["tools_list_stable"] is True
    assert not any(f.code == "C12-tools-list-unstable" for f in outcome.report.all_findings())


async def test_e2e_spec_surface_experimental_captures_sampling():
    # #33: the harness drives read-only tools; the fixture's tool fires sampling with an
    # injection tell and advertises a resolvable resource. Experimental → never gates.
    cfg = ProbeConfig(target=_target("spec_server.py"), families=("contract", "spec"),
                      experimental=True)
    outcome = await run_probe(cfg)
    spec = outcome.report.families["spec"]
    assert spec.measured is True
    assert "sampling" in spec.metrics["exercised"]
    assert "resources" in spec.metrics["exercised"]
    assert any(f.code == "SS1-sampling-injection" for f in spec.findings)
    assert outcome.report.weights.get("spec", 0.0) == 0.0  # zero rubric weight
    assert outcome.report.hard_gate != "spec"


async def test_e2e_7_static_mode_not_measured():
    dump = SERVERS / "dump.mcp.json"
    cfg = ProbeConfig(static_path=str(dump), families=("contract", "cost"))
    outcome = await run_probe(cfg)
    assert outcome.exit_code == ExitCode.OK
    # invocation is live-only → reported not measured, never zeroed (ADR-006)
    assert outcome.report.families["contract"].metrics["invocation_measured"] is False
    assert outcome.report.families["cost"].measured is True
