"""2026-07-28 stateless-conformance tests (issue #32) — version-aware, black-box grading."""

from __future__ import annotations

from mcp_quality.connect.client import ConnectRecord, FakeClient
from mcp_quality.contract.stateless import (
    STATELESS_REVISION,
    grade_stateless_conformance,
    on_stateless_revision,
)
from mcp_quality.engines.contract import ContractEngine

from .conftest import make_ctx

_TOOLS = [{"name": "x", "description": "Return x.", "inputSchema": {"type": "object"},
           "annotations": {"readOnlyHint": True}}]


def _codes(findings):
    return {f.code for f in findings}


# -- version detection ---------------------------------------------------------

def test_on_stateless_revision_boundary():
    assert on_stateless_revision("2026-07-28") is True
    assert on_stateless_revision("2027-01-01") is True
    assert on_stateless_revision("2025-11-25") is False
    assert on_stateless_revision("") is False


# -- pure grader ---------------------------------------------------------------

def test_legacy_server_with_no_signals_is_clean():
    findings, readiness = grade_stateless_conformance("2025-11-25")
    assert findings == []
    assert readiness["on_stateless_revision"] is False


def test_legacy_missing_discover_is_a_gentle_forward_compat_nudge():
    findings, _ = grade_stateless_conformance("2025-11-25", discover_ok=False)
    assert _codes(findings) == {"C10-forward-compat"}  # not a C12 — it's optional pre-2026-07-28


def test_stateless_missing_discover_is_a_real_finding():
    findings, readiness = grade_stateless_conformance(STATELESS_REVISION, discover_ok=False)
    assert "C12-no-server-discover" in _codes(findings)
    assert readiness["on_stateless_revision"] is True


def test_tools_list_variance_flagged_on_any_revision():
    legacy, _ = grade_stateless_conformance("2025-11-25", tools_list_stable=False)
    stateless, _ = grade_stateless_conformance(STATELESS_REVISION, tools_list_stable=False)
    assert "C12-tools-list-unstable" in _codes(legacy)
    assert "C12-tools-list-unstable" in _codes(stateless)


def test_meta_unenforced_only_matters_on_stateless_revision():
    legacy, _ = grade_stateless_conformance("2025-11-25", meta_enforced=False)
    stateless, _ = grade_stateless_conformance(STATELESS_REVISION, meta_enforced=False)
    assert "C12-meta-unenforced" not in _codes(legacy)
    assert "C12-meta-unenforced" in _codes(stateless)


def test_fully_stateless_conformant_server_is_clean():
    findings, _ = grade_stateless_conformance(
        STATELESS_REVISION, discover_ok=True, tools_list_stable=True, meta_enforced=True,
    )
    assert findings == []


def test_not_measured_signals_produce_no_findings():
    findings, readiness = grade_stateless_conformance(STATELESS_REVISION)  # all None
    assert findings == []
    assert readiness["server_discover"] is None and readiness["tools_list_stable"] is None


# -- engine integration (crafted connect records = legacy vs stateless paths) --

async def test_engine_legacy_record_has_no_c12():
    client = FakeClient(connect_record=ConnectRecord(
        transport="stdio", protocol_version="2025-11-25", legacy_handshake_ok=True))
    fs = await ContractEngine().run(make_ctx(_TOOLS, client=client))
    assert not any(f.code.startswith("C12") for f in fs.findings)
    assert fs.metrics["stateless_readiness"]["on_stateless_revision"] is False


async def test_engine_stateless_record_flags_missing_discover():
    client = FakeClient(connect_record=ConnectRecord(
        transport="streamable-http", protocol_version="2026-07-28", stateless_discover_ok=False))
    fs = await ContractEngine().run(make_ctx(_TOOLS, client=client))
    assert any(f.code == "C12-no-server-discover" for f in fs.findings)
    assert fs.metrics["stateless_readiness"]["on_stateless_revision"] is True


async def test_engine_unstable_tools_list_flags_and_penalizes():
    unstable = FakeClient(connect_record=ConnectRecord(
        transport="stdio", protocol_version="2026-07-28", tools_list_stable=False,
        stateless_discover_ok=True, meta_enforced=True))
    stable = FakeClient(connect_record=ConnectRecord(
        transport="stdio", protocol_version="2026-07-28", tools_list_stable=True,
        stateless_discover_ok=True, meta_enforced=True))
    fs_unstable = await ContractEngine().run(make_ctx(_TOOLS, client=unstable))
    fs_stable = await ContractEngine().run(make_ctx(_TOOLS, client=stable))
    assert any(f.code == "C12-tools-list-unstable" for f in fs_unstable.findings)
    assert fs_unstable.score < fs_stable.score  # the bounded penalty bit


async def test_engine_static_mode_reports_what_it_can():
    fs = await ContractEngine().run(make_ctx(_TOOLS, client=None))  # no connect record
    readiness = fs.metrics["stateless_readiness"]
    assert readiness["server_discover"] is None  # not measurable offline
    assert readiness["tools_list_stable"] is None
    assert not any(f.code.startswith("C12") for f in fs.findings)
