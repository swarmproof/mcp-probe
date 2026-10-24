"""Cross-client portability lint component tests (issue #66, REQ-C14).

C14 is static-ok and pure over the surface, so every case is a crafted ToolDef — no client,
no I/O. Covers each hazard's fire + a low-false-positive counter-case, and the engine wiring
(findings appear in both static and live runs)."""

from __future__ import annotations

from mcp_quality.contract.client_compat import grade_client_compat
from mcp_quality.engines.contract import ContractEngine
from mcp_quality.models import ToolDef

from .conftest import make_ctx


def _codes(tools: list[ToolDef]) -> set[str]:
    return {f.code for f in grade_client_compat(tuple(tools))}


def _tool(name="t", description="desc", input_schema=None, output_schema=None, annotations=None):
    return ToolDef(
        name=name,
        description=description,
        input_schema=input_schema if input_schema is not None else {"type": "object"},
        output_schema=output_schema,
        annotations=annotations or {},
    )


# -- (a) oversized output -----------------------------------------------------

def test_array_output_without_pagination_fires():
    t = _tool(output_schema={"type": "array", "items": {"type": "string"}})
    assert "C14-oversized-output" in {f.code for f in grade_client_compat((t,))}


def test_array_property_output_without_pagination_fires():
    t = _tool(output_schema={"type": "object", "properties": {"rows": {"type": "array"}}})
    assert "C14-oversized-output" in _codes([t])


def test_collection_description_without_pagination_fires():
    t = _tool(description="Returns all records in the database.")
    assert "C14-oversized-output" in _codes([t])


def test_array_output_with_limit_param_does_not_fire():
    t = _tool(
        input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
        output_schema={"type": "array"},
    )
    assert "C14-oversized-output" not in _codes([t])


def test_array_output_with_cursor_param_does_not_fire():
    t = _tool(
        input_schema={"type": "object", "properties": {"cursor": {"type": "string"}}},
        output_schema={"type": "array"},
    )
    assert "C14-oversized-output" not in _codes([t])


def test_scalar_output_not_flagged_oversized():
    t = _tool(description="Return a single record.", output_schema={"type": "object"})
    assert "C14-oversized-output" not in _codes([t])


# -- (b) non-portable content hints -------------------------------------------

def test_html_content_hint_fires():
    t = _tool(description="Returns an <img> tag with the rendered chart.")
    assert "C14-nonportable-content" in _codes([t])


def test_ansi_content_hint_fires():
    t = _tool(description="Output is colorized with ANSI escape codes for the terminal.")
    assert "C14-nonportable-content" in _codes([t])


def test_mime_image_hint_fires():
    t = _tool(description="Returns image/png bytes.")
    assert "C14-nonportable-content" in _codes([t])


def test_plain_description_not_flagged_content():
    t = _tool(description="Return the current temperature as a number.")
    assert "C14-nonportable-content" not in _codes([t])


# -- (c) annotation-only safety -----------------------------------------------

def test_destructive_annotation_without_warning_fires():
    t = _tool(name="cleanup", description="Tidy up the workspace.",
              annotations={"destructiveHint": True})
    assert "C14-annotation-only-safety" in _codes([t])


def test_destructive_annotation_with_explicit_warning_does_not_fire():
    t = _tool(name="delete_record", description="Permanently delete a record; cannot be undone.",
              annotations={"destructiveHint": True})
    assert "C14-annotation-only-safety" not in _codes([t])


def test_non_destructive_tool_not_flagged_safety():
    t = _tool(name="get_item", description="Fetch an item.", annotations={"readOnlyHint": True})
    assert "C14-annotation-only-safety" not in _codes([t])


def test_clean_tool_produces_no_hazards():
    t = _tool(
        name="get_weather",
        description="Return the current weather for a city.",
        input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
    )
    assert grade_client_compat((t,)) == []


# -- engine wiring (static-ok) ------------------------------------------------

async def test_engine_emits_client_compat_in_static_mode():
    tools = [{
        "name": "dump_logs",
        "description": "Returns all log lines.",
        "inputSchema": {"type": "object"},
        "outputSchema": {"type": "array"},
    }]
    fs = await ContractEngine().run(make_ctx(tools, client=None))
    assert any(f.code == "C14-oversized-output" for f in fs.findings)
    assert fs.metrics["client_compat_hazards"] >= 1


async def test_engine_clean_surface_no_client_compat():
    tools = [{
        "name": "get_weather",
        "description": "Return the current weather for a city.",
        "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}},
    }]
    fs = await ContractEngine().run(make_ctx(tools, client=None))
    assert not any(f.code.startswith("C14") for f in fs.findings)
    assert fs.metrics["client_compat_hazards"] == 0
