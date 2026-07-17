"""Shared test fixtures — surface builders so component tests feed a fixed ServerSurface
and assert an exact FamilyScore, with no network and no LLM (TEST-PLAN §1, ADR-001)."""

from __future__ import annotations

import pytest

from mcp_probe.config import ProbeConfig
from mcp_probe.connect.client import ConnectRecord, FakeClient, InvokeResult
from mcp_probe.connect.discover import surface_from_tools
from mcp_probe.models import ProbeContext, ServerSurface


def make_surface(tools: list[dict], **kw) -> ServerSurface:
    return surface_from_tools(tools, **kw)


@pytest.fixture
def good_tools() -> list[dict]:
    """A clean, lean, legible toolset → expected A."""
    return [
        {
            "name": "get_weather",
            "description": "Return the current weather for a city. Example: get_weather(city='Paris').",
            "inputSchema": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "City name"}},
                "required": ["city"],
            },
            "annotations": {"readOnlyHint": True},
        },
        {
            "name": "list_cities",
            "description": "List cities the weather service knows about.",
            "inputSchema": {"type": "object", "properties": {}},
            "annotations": {"readOnlyHint": True},
        },
    ]


@pytest.fixture
def confusable_tools() -> list[dict]:
    """delete_record vs archive_record with near-identical descriptions."""
    schema = {
        "type": "object",
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    }
    return [
        {"name": "delete_record", "description": "Remove a record by id.", "inputSchema": schema},
        {"name": "archive_record", "description": "Remove a record by id.", "inputSchema": schema},
    ]


@pytest.fixture
def config() -> ProbeConfig:
    return ProbeConfig(families=("contract", "cost"))


@pytest.fixture
def static_ctx(good_tools, config) -> ProbeContext:
    return ProbeContext(surface=make_surface(good_tools), config=config, client=None)


def make_ctx(tools: list[dict], *, client=None, config: ProbeConfig | None = None) -> ProbeContext:
    return ProbeContext(
        surface=make_surface(tools),
        config=config or ProbeConfig(),
        client=client,
    )


__all__ = [
    "make_surface",
    "make_ctx",
    "FakeClient",
    "InvokeResult",
    "ConnectRecord",
]
