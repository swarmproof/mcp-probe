"""Fixture: a tool with undeclared nondeterminism → Contract determinism probe flags it
(TEST-PLAN §2, REQ-C5). ``get_status`` returns a different value on each call."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP("flaky-server")
_state = {"n": 0}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), description="Get a status token.")
def get_status() -> str:
    _state["n"] += 1
    return f"status-{_state['n']}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), description="Return a fixed greeting.")
def greet(name: str) -> str:
    return f"hello {name}"


if __name__ == "__main__":
    mcp.run()
