"""Contract error-path + forward-compat tests (issue #12, REQ-C9/C10)."""

from __future__ import annotations

from mcp_probe.config import ProbeConfig
from mcp_probe.connect.client import ConnectRecord, FakeClient, InvokeResult
from mcp_probe.contract.schema import synthesize_invalid_args, validate_against
from mcp_probe.engines.contract import ContractEngine

from .conftest import make_ctx

_SCHEMA = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
_TOOL = {"name": "get_x", "description": "read", "inputSchema": _SCHEMA,
         "annotations": {"readOnlyHint": True}}


def test_synthesize_invalid_args_violates_schema():
    bad = synthesize_invalid_args(_SCHEMA)
    assert validate_against(bad, _SCHEMA)  # non-empty → it genuinely violates the schema


async def test_crash_on_bad_input_is_c9_hard_gate():
    def handler(args):
        # fine on valid (string) input, crashes on the malformed (dict) input
        if not isinstance(args.get("x"), str):
            raise RuntimeError("unhandled: cannot coerce")
        return InvokeResult("get_x", is_error=False, content={"x": args["x"]})

    client = FakeClient(results={"get_x": handler})
    fs = await ContractEngine().run(make_ctx([_TOOL], client=client, config=ProbeConfig()))
    assert any(f.code == "C9-error-path" for f in fs.findings)
    assert fs.hard_gate_tripped
    assert fs.metrics["error_path_crashes"] == 1


async def test_clean_rejection_is_not_a_crash():
    # Server returns a clean error result (as the façade does for McpError) → passes C9.
    def handler(args):
        if not isinstance(args.get("x"), str):
            return InvokeResult("get_x", is_error=True, content={"error": "invalid params"})
        return InvokeResult("get_x", is_error=False, content={"x": args["x"]})

    client = FakeClient(results={"get_x": handler})
    fs = await ContractEngine().run(make_ctx([_TOOL], client=client, config=ProbeConfig()))
    assert not any(f.code == "C9-error-path" for f in fs.findings)
    assert fs.metrics["error_path_crashes"] == 0


async def test_c10_flags_sse_transport():
    client = FakeClient(connect_record=ConnectRecord(transport="sse", protocol_version="2025-11-25",
                                                     legacy_handshake_ok=True))
    fs = await ContractEngine().run(make_ctx([_TOOL], client=client))
    c10 = next((f for f in fs.findings if f.code == "C10-forward-compat"), None)
    assert c10 is not None and "SSE" in c10.message


async def test_c9_not_run_in_static_mode():
    fs = await ContractEngine().run(make_ctx([_TOOL], client=None))  # static
    assert fs.metrics["error_path_crashes"] == 0
    assert not any(f.code == "C9-error-path" for f in fs.findings)
