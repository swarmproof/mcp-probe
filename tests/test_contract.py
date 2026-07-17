"""Contract engine + schema module component tests (TEST-PLAN §6 Contract).

Uses FakeClient so invocation/determinism are exercised with zero I/O — the pure-function
design (ADR-001) makes this possible."""

from __future__ import annotations

from mcp_probe.config import ProbeConfig
from mcp_probe.connect.client import ConnectRecord, FakeClient, InvokeResult
from mcp_probe.contract.schema import synthesize_args, validate_against, validate_schema
from mcp_probe.engines.contract import ContractEngine

from .conftest import make_ctx


# -- schema validity (REQ-C3) -------------------------------------------------

def test_validate_schema_accepts_valid():
    assert validate_schema({"type": "object", "properties": {"x": {"type": "string"}}}) == []


def test_validate_schema_flags_bad_type():
    issues = validate_schema({"type": "not-a-type"})
    assert issues


def test_validate_schema_flags_unresolvable_ref():
    issues = validate_schema({"type": "object", "properties": {"x": {"$ref": "#/nope"}}})
    assert any("$ref" in i.message for i in issues)


# -- arg synthesis (REQ-C4) ---------------------------------------------------

def test_synthesize_args_deterministic_and_valid():
    schema = {
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "count": {"type": "integer", "minimum": 3},
            "mode": {"enum": ["a", "b"]},
        },
        "required": ["city", "count", "mode"],
    }
    a1 = synthesize_args(schema, seed=42)
    a2 = synthesize_args(schema, seed=42)
    assert a1 == a2  # pure function of (schema, seed) → determinism probe is stable
    assert validate_against(a1, schema) == []
    assert a1["count"] >= 3
    assert a1["mode"] in ("a", "b")


# -- determinism probe (REQ-C5) -----------------------------------------------

async def test_determinism_probe_flags_nondeterministic_tool():
    tools = [{"name": "get_status", "description": "status", "inputSchema": {"type": "object"}}]
    counter = {"n": 0}

    def flaky() -> InvokeResult:
        counter["n"] += 1
        return InvokeResult(tool="get_status", is_error=False, content={"n": counter["n"]})

    client = FakeClient(results={"get_status": flaky})
    ctx = make_ctx(tools, client=client, config=ProbeConfig(allow_writes=False))
    fs = await ContractEngine().run(ctx)
    assert any(f.code == "C5-nondeterminism" for f in fs.findings)


async def test_deterministic_tool_passes():
    tools = [{"name": "greet", "description": "greet", "inputSchema": {"type": "object"}}]
    client = FakeClient(results={"greet": InvokeResult("greet", False, {"msg": "hi"})})
    ctx = make_ctx(tools, client=client)
    fs = await ContractEngine().run(ctx)
    assert not any(f.code == "C5-nondeterminism" for f in fs.findings)
    assert fs.score == 100


# -- output conformance (REQ-C4) ----------------------------------------------

async def test_output_nonconformance_hard_gates():
    tools = [
        {
            "name": "count",
            "description": "count",
            "inputSchema": {"type": "object"},
            "outputSchema": {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]},
        }
    ]
    # structured result missing required 'n' → violates declared output schema
    bad = InvokeResult("count", False, content=[], structured={"wrong": "shape"})
    client = FakeClient(results={"count": bad})
    ctx = make_ctx(tools, client=client)
    fs = await ContractEngine().run(ctx)
    assert fs.hard_gate_tripped
    assert any(f.code == "C4-output-nonconformant" for f in fs.findings)


# -- schema-invalid hard-gate -------------------------------------------------

async def test_schema_invalid_hard_gates():
    tools = [{"name": "bad", "description": "bad", "inputSchema": {"type": "nonsense"}}]
    ctx = make_ctx(tools, client=FakeClient())
    fs = await ContractEngine().run(ctx)
    assert fs.hard_gate_tripped
    assert any(f.code == "C3-schema-invalid" for f in fs.findings)


# -- write skipping (NFR-9) ---------------------------------------------------

async def test_write_tool_skipped_by_default():
    tools = [{"name": "delete_record", "description": "delete", "inputSchema": {"type": "object"}}]
    client = FakeClient()
    ctx = make_ctx(tools, client=client, config=ProbeConfig(allow_writes=False))
    await ContractEngine().run(ctx)
    assert client.calls == []  # destructive tool never invoked


async def test_write_tool_invoked_with_allow_writes():
    tools = [{"name": "delete_record", "description": "delete", "inputSchema": {"type": "object"}}]
    client = FakeClient()
    ctx = make_ctx(tools, client=client, config=ProbeConfig(allow_writes=True))
    await ContractEngine().run(ctx)
    assert client.calls  # invoked when explicitly allowed


# -- forward-compat handshake finding (REQ-C10) -------------------------------

async def test_legacy_only_forward_compat_finding():
    tools = [{"name": "x", "description": "x", "inputSchema": {"type": "object"}}]
    record = ConnectRecord(
        transport="sse", protocol_version="2025-11-25",
        legacy_handshake_ok=True, stateless_discover_ok=False,
    )
    client = FakeClient(connect_record=record)
    ctx = make_ctx(tools, client=client)
    fs = await ContractEngine().run(ctx)
    assert any(f.code == "C10-forward-compat" for f in fs.findings)
