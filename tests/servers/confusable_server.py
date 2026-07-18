"""Fixture: two tools with near-identical descriptions → low legibility, high confusion
in the disambiguation matrix (TEST-PLAN §2, REQ-L2)."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP("confusable-server")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False), description="Remove a record by id.")
def delete_record(id: str) -> str:
    return f"deleted {id}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False), description="Remove a record by id.")
def archive_record(id: str) -> str:
    return f"archived {id}"


if __name__ == "__main__":
    mcp.run()
