"""Fixture: many verbose tools → high toolset token cost → Cost near-F + bloat findings
(TEST-PLAN §2, REQ-$1/$2). Tools are generated to inflate the context tax."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP("bloated-server")

_BLURB = (
    "This tool performs an extremely comprehensive, configurable, enterprise-grade "
    "operation with many options and caveats. " * 8
)


def _make(idx: int) -> None:
    @mcp.tool(
        name=f"operation_{idx:02d}",
        annotations=ToolAnnotations(readOnlyHint=True),
        description=f"{_BLURB} (variant {idx})",
    )
    def _op(query: str, limit: int = 10, verbose: bool = False, tags: list[str] | None = None) -> str:
        return f"result-{idx}:{query}"


for _i in range(30):
    _make(_i)


if __name__ == "__main__":
    mcp.run()
