"""Live transport — the only module that imports the MCP SDK (ARCHITECTURE §3).

Wraps the official SDK's ``stdio_client`` / ``streamablehttp_client`` / ``sse_client``
behind the :class:`~mcp_probe.connect.client.MCPClientProtocol` façade so engines never
see the SDK. The session is held open for the whole run via an ``AsyncExitStack`` (the
determinism probe calls a tool twice; Performance hammers it), and unwound once on
``close()``.

Handshake reality check: the current SDK negotiates via ``initialize`` and reports the
server's ``protocolVersion``. There is no ``server/discover`` method in the SDK, so the
"stateless discovery" path from the design doc is left unprobed (``stateless_discover_ok
= None``) rather than fabricated — we grade what the protocol actually does.
"""

from __future__ import annotations

import asyncio
import shlex
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from mcp_probe.config import ProbeConfig
from mcp_probe.connect.client import ConnectRecord, InvokeResult
from mcp_probe.connect.discover import surface_from_tools
from mcp_probe.models import ServerSurface, Transport


class MCPClient:
    """Live SDK-backed client. Constructed by :func:`connect`, which also discovers."""

    def __init__(self, session: ClientSession, stack: AsyncExitStack, record: ConnectRecord) -> None:
        self._session = session
        self._stack = stack
        self.connect_record = record

    async def call_tool(self, name: str, args: dict[str, Any]) -> InvokeResult:
        result = await self._session.call_tool(name, args)
        content = [_dump(block) for block in (result.content or [])]
        return InvokeResult(
            tool=name,
            is_error=bool(result.isError),
            content=content,
            structured=result.structuredContent,
            raw=result,
        )

    async def close(self) -> None:
        await self._stack.aclose()


def _dump(obj: Any) -> Any:
    """Normalize a pydantic content block to a plain dict for comparison/validation."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return obj


def _pick_transport(config: ProbeConfig) -> Transport:
    if config.transport and config.transport != "auto":
        return config.transport  # type: ignore[return-value]
    target = config.target.strip()
    if target.startswith(("http://", "https://")):
        return "streamable-http"
    return "stdio"


async def connect(config: ProbeConfig) -> tuple[MCPClient, ServerSurface]:
    """Negotiate transport + handshake, discover the surface, return (client, surface).

    Raises on an unreachable / non-conformant target — the pipeline maps that to exit 2.
    """
    transport = _pick_transport(config)
    stack = AsyncExitStack()
    try:
        read, write = await _open_streams(stack, transport, config)
        session = await stack.enter_async_context(ClientSession(read, write))
        init = await asyncio.wait_for(session.initialize(), timeout=config.stdio_timeout)

        record = ConnectRecord(
            transport=transport,
            protocol_version=getattr(init, "protocolVersion", "") or "",
            framing_ok=True,
            legacy_handshake_ok=True,
            stateless_discover_ok=None,  # no such method in the SDK; don't fabricate a probe
            server_info=_dump(getattr(init, "serverInfo", {})) or {},
            capabilities=_dump(getattr(init, "capabilities", {})) or {},
        )
        surface = await _discover(session, record)
        return MCPClient(session, stack, record), surface
    except Exception:
        await stack.aclose()
        raise


async def _open_streams(stack: AsyncExitStack, transport: Transport, config: ProbeConfig):
    if transport == "stdio":
        parts = shlex.split(config.target)
        if not parts:
            raise ValueError("empty stdio command")
        params = StdioServerParameters(command=parts[0], args=parts[1:])
        streams = await stack.enter_async_context(stdio_client(params))
        return streams[0], streams[1]
    if transport == "streamable-http":
        # Non-deprecated client; yields (read, write, get_session_id). Auth headers, when
        # added, go via a passed httpx.AsyncClient (v0.2).
        streams = await stack.enter_async_context(streamable_http_client(config.target))
        return streams[0], streams[1]
    if transport == "sse":
        streams = await stack.enter_async_context(sse_client(config.target))
        return streams[0], streams[1]
    raise ValueError(f"unknown transport: {transport}")


async def _discover(session: ClientSession, record: ConnectRecord) -> ServerSurface:
    tools = await _list_all(session.list_tools, "tools")
    resources = await _safe_list(session.list_resources, "resources")
    prompts = await _safe_list(session.list_prompts, "prompts")
    return surface_from_tools(
        [_dump(t) for t in tools],
        resources=[_dump(r) for r in resources],
        prompts=[_dump(p) for p in prompts],
        server_info=record.server_info,
        capabilities=record.capabilities,
        protocol_version=record.protocol_version,
        transport=record.transport,  # type: ignore[arg-type]
    )


async def _list_all(method: Any, attr: str) -> list[Any]:
    """Follow ``nextCursor`` pagination to completion."""
    items: list[Any] = []
    cursor: str | None = None
    while True:
        result = await method(cursor) if cursor else await method()
        items.extend(getattr(result, attr, []) or [])
        cursor = getattr(result, "nextCursor", None)
        if not cursor:
            return items


async def _safe_list(method: Any, attr: str) -> list[Any]:
    """resources/prompts are optional capabilities — a server without them errors; treat
    that as 'none', not a failure."""
    try:
        return await _list_all(method, attr)
    except Exception:
        return []
