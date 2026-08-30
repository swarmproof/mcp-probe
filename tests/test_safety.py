"""Safety-Contract family tests (issue #28) — annotation truthfulness + retry-safety."""

from __future__ import annotations

from mcp_quality.engines.safety import SafetyEngine, check_safety_contract
from mcp_quality.models import ToolDef

from .conftest import make_ctx


def _tool(name, *, ann=None, props=None, required=None, desc="does a thing"):
    schema = {"type": "object", "properties": props or {}}
    if required:
        schema["required"] = required
    return ToolDef(name=name, description=desc, input_schema=schema, annotations=ann or {})


def _codes(tool):
    return {f.code for f in check_safety_contract(tool)}


# -- static truthfulness checks -----------------------------------------------

def test_sc2_read_only_lie_on_write_named_tool():
    codes = _codes(_tool("delete_record", ann={"readOnlyHint": True}, props={"id": {"type": "string"}}))
    assert "SC2-annotation-untrue" in codes


def test_sc2_destructive_false_lie():
    codes = _codes(_tool("drop_table", ann={"destructiveHint": False}))
    assert "SC2-annotation-untrue" in codes


def test_sc1_write_tool_missing_annotations():
    codes = _codes(_tool("create_user", ann={}, props={"name": {"type": "string"}}))
    assert "SC1-annotation-missing" in codes


def test_sc3_write_without_idempotency_signal():
    codes = _codes(_tool("send_email", ann={"destructiveHint": True}, props={"to": {"type": "string"}}))
    assert "SC3-retry-unsafe" in codes


def test_sc3_satisfied_by_idempotency_key():
    codes = _codes(_tool("send_email", ann={"destructiveHint": True},
                         props={"to": {"type": "string"}, "idempotency_key": {"type": "string"}}))
    assert "SC3-retry-unsafe" not in codes


def test_sc3_satisfied_by_idempotent_hint():
    codes = _codes(_tool("set_config", ann={"destructiveHint": True, "idempotentHint": True},
                         props={"k": {"type": "string"}}))
    assert "SC3-retry-unsafe" not in codes


def test_honest_read_tool_is_clean():
    assert check_safety_contract(_tool("get_weather", ann={"readOnlyHint": True})) == []


def test_honest_write_tool_is_clean():
    # named a write, declares destructive + idempotent → truthful, retry-safe → no findings
    t = _tool("update_record", ann={"destructiveHint": True, "idempotentHint": True},
              props={"id": {"type": "string"}})
    assert check_safety_contract(t) == []


# -- engine --------------------------------------------------------------------

async def test_engine_hard_gates_on_annotation_lie():
    tools = [{"name": "delete_record", "description": "Delete a record.",
              "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}},
              "annotations": {"readOnlyHint": True}}]
    fs = await SafetyEngine().run(make_ctx(tools))  # static — no client needed
    assert fs.hard_gate_tripped
    assert fs.grade in ("C", "D", "F")
    assert any(f.code == "SC2-annotation-untrue" for f in fs.findings)


async def test_engine_clean_server_scores_a():
    tools = [{"name": "get_weather", "description": "Return weather.",
              "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": True}}]
    fs = await SafetyEngine().run(make_ctx(tools))
    assert fs.score == 100 and fs.grade == "A"
