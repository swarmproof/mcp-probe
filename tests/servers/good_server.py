"""Fixture: a clean, lean, legible server → expected overall A (TEST-PLAN §2).

Tools are read-only, tersely but clearly described with an example, and cheap. Used as
the happy-path E2E baseline and the dogfood target in CI.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP("good-server")

_CITIES = {"paris": "18°C, clear", "tokyo": "24°C, rain", "oslo": "9°C, cloudy"}


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True),
    description="Return the current weather for a city. Example: get_weather(city='Paris').",
)
def get_weather(city: str) -> str:
    return _CITIES.get(city.lower(), "unknown city")


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True),
    description="List the cities this weather service knows about.",
)
def list_cities() -> list[str]:
    return sorted(_CITIES)


if __name__ == "__main__":
    mcp.run()
