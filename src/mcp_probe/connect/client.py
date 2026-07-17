"""The client façade — a thin, SDK-agnostic contract every engine invokes through.

Engines never import the MCP SDK. They see :class:`MCPClientProtocol` (invoke a tool,
read the handshake record) and :class:`InvokeResult`. That isolation means a change in
the SDK — or swapping stdio for HTTP — touches only ``transport.py``, and it lets tests
drive engines with :class:`FakeClient` and zero I/O (ADR-001, TEST-PLAN §6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ConnectRecord:
    """What the version-aware handshake negotiation discovered (ARCHITECTURE §3).

    The Contract engine turns this into findings: "your server only speaks the legacy
    handshake" is itself a graded, forward-compat check (REQ-C2, REQ-C10).
    """

    transport: str
    protocol_version: str = ""
    framing_ok: bool = True
    framing_errors: list[str] = field(default_factory=list)
    legacy_handshake_ok: bool | None = None  # `initialize`/`initialized`
    stateless_discover_ok: bool | None = None  # newer `server/discover` + _meta path, if any
    server_info: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)


@dataclass
class InvokeResult:
    """Normalized result of a ``tools/call`` — decoupled from the SDK's result type."""

    tool: str
    is_error: bool
    content: Any  # normalized text/structured payload used for conformance + determinism
    structured: Any | None = None  # structuredContent, when the server returns it
    raw: Any = None


@runtime_checkable
class MCPClientProtocol(Protocol):
    connect_record: ConnectRecord

    async def call_tool(self, name: str, args: dict[str, Any]) -> InvokeResult: ...

    async def close(self) -> None: ...


class FakeClient:
    """Scripted in-memory client for tests and the determinism harness.

    ``results`` maps a tool name to either a fixed :class:`InvokeResult` or a zero-arg
    callable returning one (use a callable to script *nondeterministic* output — e.g. a
    counter — so the determinism probe has something to catch)."""

    def __init__(
        self,
        results: dict[str, Any] | None = None,
        *,
        connect_record: ConnectRecord | None = None,
    ) -> None:
        self._results = results or {}
        self.connect_record = connect_record or ConnectRecord(
            transport="stdio",
            protocol_version="2025-11-25",
            legacy_handshake_ok=True,
        )
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, args: dict[str, Any]) -> InvokeResult:
        self.calls.append((name, args))
        spec = self._results.get(name)
        if spec is None:
            return InvokeResult(tool=name, is_error=False, content={"ok": True})
        if callable(spec):
            return spec()
        return spec

    async def close(self) -> None:
        return None
