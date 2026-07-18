"""Fixture: a clean server served over HTTP — Streamable-HTTP or legacy SSE.

Used by the transport integration tests (INT-2/INT-3). Reads ``--transport`` and
``--port`` so a test can spawn it on a free port. Same tool surface as good_server so the
grade is predictable across transports.

Run: python http_server.py --transport streamable-http --port 8123
"""

from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


def build(port: int) -> FastMCP:
    mcp = FastMCP("http-server", host="127.0.0.1", port=port)

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True),
        description="Return the current weather for a city. Example: get_weather(city='Paris').",
    )
    def get_weather(city: str) -> str:
        return f"{city}: 20C, clear"

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True),
        description="List the cities this weather service knows about.",
    )
    def list_cities() -> list[str]:
        return ["paris", "tokyo", "oslo"]

    return mcp


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", default="streamable-http", choices=["streamable-http", "sse"])
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    build(args.port).run(transport=args.transport)
