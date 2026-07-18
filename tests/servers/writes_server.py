"""Fixture: a destructive tool that must be skipped unless ``--allow-writes`` (NFR-9,
ADR-009). ``delete_record`` matches the write heuristic and carries destructiveHint."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP("writes-server")
_db = {"1": "alice", "2": "bob"}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), description="Look up a record by id.")
def get_record(id: str) -> str:
    return _db.get(id, "not found")


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
    description="Permanently delete a record by id.",
)
def delete_record(id: str) -> str:
    _db.pop(id, None)
    return "deleted"


if __name__ == "__main__":
    mcp.run()
