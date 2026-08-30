"""Description-quality lint tests (issue #30) — the new offline L3 sub-lints."""

from __future__ import annotations

from mcp_quality.legibility.lints import lint_descriptions

from .conftest import make_surface


def _codes(tools):
    return {f.code for f in lint_descriptions(make_surface(tools))}


def test_ambiguous_param_flagged():
    codes = _codes([{"name": "run", "description": "Run a job. Example: run(data=...).",
                     "inputSchema": {"type": "object", "properties": {"data": {"type": "object"}}}}])
    assert "L3-ambiguous-param" in codes


def test_single_char_param_flagged():
    codes = _codes([{"name": "plot", "description": "Plot. Example: plot(x=1).",
                     "inputSchema": {"type": "object", "properties": {"x": {"type": "number"}}}}])
    assert "L3-ambiguous-param" in codes


def test_specific_param_not_flagged():
    codes = _codes([{"name": "get_user", "description": "Get a user. Example: get_user(user_id='u1').",
                     "inputSchema": {"type": "object",
                                     "properties": {"user_id": {"type": "string", "description": "the id"}}}}])
    assert "L3-ambiguous-param" not in codes


def test_collection_tool_without_pagination_flagged():
    codes = _codes([{"name": "list_records", "description": "List records. Example: list_records().",
                     "inputSchema": {"type": "object", "properties": {}}}])
    assert "L3-no-pagination" in codes


def test_collection_tool_with_pagination_ok():
    codes = _codes([{"name": "search_docs", "description": "Search docs. Example: search_docs(q='x').",
                     "inputSchema": {"type": "object",
                                     "properties": {"q": {"type": "string", "description": "query"},
                                                    "limit": {"type": "integer", "description": "max"}}}}])
    assert "L3-no-pagination" not in codes


def test_non_collection_tool_not_flagged_for_pagination():
    codes = _codes([{"name": "get_weather", "description": "Weather. Example: get_weather(city='x').",
                     "inputSchema": {"type": "object",
                                     "properties": {"city": {"type": "string", "description": "city"}}}}])
    assert "L3-no-pagination" not in codes


def test_leaked_identifier_flagged():
    codes = _codes([{"name": "get_img", "description": "Return the 256px_url and mime_type of an image.",
                     "inputSchema": {"type": "object", "properties": {}}}])
    assert "L3-leaked-identifier" in codes


def test_clean_tool_has_no_new_lints():
    codes = _codes([{"name": "get_weather",
                     "description": "Return the current weather for a city. Example: get_weather(city='Paris').",
                     "inputSchema": {"type": "object",
                                     "properties": {"city": {"type": "string", "description": "City name"}},
                                     "required": ["city"]}}])
    for c in ("L3-ambiguous-param", "L3-no-pagination", "L3-leaked-identifier"):
        assert c not in codes
