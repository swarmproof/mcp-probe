"""Live transport — the only module that imports the MCP SDK (ARCHITECTURE §3).

Wraps the official SDK's ``stdio_client`` / ``streamablehttp_client`` / ``sse_client``
behind the :class:`~mcp_quality.connect.client.MCPClientProtocol` façade so engines never
see the SDK. The session is held open for the whole run via an ``AsyncExitStack`` (the
determinism probe calls a tool twice; Performance hammers it), and unwound once on
``close()``.

Handshake reality check: the current SDK negotiates via ``initialize`` and reports the
server's ``protocolVersion``. There is no ``server/discover`` method in the SDK, so the
"stateless discovery" path from the design doc is left unprobed (``stateless_discover_ok
= None``) rather than fabricated — we grade what the protocol actually does. The one
stateless-conformance rule we *can* check black-box today (#32) is ``tools/list``
stability across two fresh connections — done with a second, short-lived session.
"""

from __future__ import annotations

import asyncio
import shlex
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, McpError, StdioServerParameters, stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CreateMessageResult, ElicitResult, TextContent

from mcp_quality.config import ProbeConfig
from mcp_quality.connect.capture import (
    CaptureLog,
    ElicitedRequest,
    ResourceResolution,
    SampledMessage,
)
from mcp_quality.connect.client import ConnectRecord, InvokeResult
from mcp_quality.connect.discover import surface_from_tools
from mcp_quality.models import ServerSurface, Transport


class MCPClient:
    """Live SDK-backed client. Constructed by :func:`connect`, which also discovers."""

    def __init__(
        self,
        session: ClientSession,
        stack: AsyncExitStack,
        record: ConnectRecord,
        capture: CaptureLog,
    ) -> None:
        self._session = session
        self._stack = stack
        self.connect_record = record
        self.capture = capture

    async def read_resource(self, uri: str) -> ResourceResolution:
        """Attempt to resolve one advertised resource / resource_link (#33)."""
        try:
            from pydantic import AnyUrl

            result = await self._session.read_resource(AnyUrl(uri))
            ok = bool(getattr(result, "contents", None))
            return ResourceResolution(uri=uri, ok=ok, error=None if ok else "empty contents")
        except Exception as exc:
            return ResourceResolution(uri=uri, ok=False, error=str(exc))

    async def call_tool(self, name: str, args: dict[str, Any]) -> InvokeResult:
        # A JSON-RPC error (McpError) is a *clean* protocol response, not a crash — normalize
        # it to an is_error result so engines stay SDK-agnostic and only real crashes raise.
        try:
            result = await self._session.call_tool(name, args)
        except McpError as exc:
            return InvokeResult(tool=name, is_error=True, content={"error": str(exc)}, raw=exc)
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
    capture = CaptureLog()
    try:
        read, write = await _open_streams(stack, transport, config)
        sampling_cb, elicit_cb = _capture_callbacks(capture)
        session = await stack.enter_async_context(
            ClientSession(read, write, sampling_callback=sampling_cb, elicitation_callback=elicit_cb)
        )
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
        # #32: stateless-conformance — is tools/list identical on a second fresh connection?
        record.tools_list_stable = await _probe_tools_list_stability(
            config, transport, surface.surface_hash
        )
        return MCPClient(session, stack, record, capture), surface
    except Exception:
        await stack.aclose()
        raise


def _capture_callbacks(capture: CaptureLog):
    """Build passive sampling/elicitation callbacks that *record* server-originated requests
    (#33) and return a benign, non-executing response so the server call completes. We never
    actually run the requested LLM sampling or collect real user input — the point is to
    inspect what the server *asked for*, safely (ADR-009, read-only spirit)."""

    async def on_sampling(context: Any, params: Any) -> CreateMessageResult:
        capture.used_sampling = True
        capture.sampling.append(
            SampledMessage(
                system_prompt=getattr(params, "systemPrompt", "") or "",
                messages=[_dump(m) for m in getattr(params, "messages", []) or []],
                include_context=getattr(params, "includeContext", None),
                max_tokens=getattr(params, "maxTokens", None),
            )
        )
        return CreateMessageResult(
            role="assistant",
            content=TextContent(type="text", text="[mcp-quality probe] sampling not executed"),
            model="mcp-quality-probe",
            stopReason="endTurn",
        )

    async def on_elicit(context: Any, params: Any) -> ElicitResult:
        capture.used_elicitation = True
        # The SDK models URL vs form elicitation as distinct param types (#33).
        cls = type(params).__name__
        mode = "url" if "URL" in cls or "Url" in cls else ("form" if "Form" in cls else "unknown")
        schema = _dump(getattr(params, "requestedSchema", {})) or {}
        capture.elicitations.append(
            ElicitedRequest(
                message=getattr(params, "message", "") or "",
                mode=mode,
                schema=schema if isinstance(schema, dict) else {},
                url=getattr(params, "url", None),
            )
        )
        return ElicitResult(action="decline")  # never submit real user input

    return on_sampling, on_elicit


async def _probe_tools_list_stability(
    config: ProbeConfig, transport: Transport, first_hash: str
) -> bool | None:
    """Open a *second* fresh connection and compare tools/list to the first (#32).

    Per-connection variance means an agent's tool set depends on which connection it opened
    — a stateless-conformance bug. Best-effort and isolated: any failure (server can't take a
    second connection, transport quirk) returns ``None`` = not measured, never a false alarm."""
    stack = AsyncExitStack()
    try:
        read, write = await _open_streams(stack, transport, config)
        session = await stack.enter_async_context(ClientSession(read, write))
        await asyncio.wait_for(session.initialize(), timeout=config.stdio_timeout)
        tools = await _list_all(session.list_tools, "tools")
        second = surface_from_tools([_dump(t) for t in tools])
        return second.surface_hash == first_hash
    except Exception:
        return None
    finally:
        await stack.aclose()


async def _open_streams(stack: AsyncExitStack, transport: Transport, config: ProbeConfig):
    if transport == "stdio":
        parts = shlex.split(config.target)
        if not parts:
            raise ValueError("empty stdio command")
        params = StdioServerParameters(command=parts[0], args=parts[1:])
        streams = await stack.enter_async_context(stdio_client(params))
        return streams[0], streams[1]
    headers = dict(getattr(config, "headers", {}) or {})
    if transport == "streamable-http":
        # Non-deprecated client; yields (read, write, get_session_id). Auth headers ride on
        # a passed httpx.AsyncClient (the new API's injection point).
        http_client = None
        if headers:
            import httpx

            http_client = await stack.enter_async_context(httpx.AsyncClient(headers=headers))
        streams = await stack.enter_async_context(
            streamable_http_client(config.target, http_client=http_client)
        )
        return streams[0], streams[1]
    if transport == "sse":
        streams = await stack.enter_async_context(sse_client(config.target, headers=headers or None))
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
