"""Surface construction — from live discovery results or an offline JSON dump.

``surface_from_dump`` powers ``static`` mode: it ingests the ``tools/list`` shape that
registries and CI already produce, so mcp-probe can score a server with no process to
spawn (REQ-C7 static-ok, ADR-006). Both entry points normalize MCP's camelCase
(``inputSchema``/``outputSchema``) and compute the canonical ``surface_hash``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp_probe.models import (
    PromptDef,
    ResourceDef,
    ServerSurface,
    ToolDef,
    Transport,
)


def _tool_from_raw(raw: dict[str, Any]) -> ToolDef:
    return ToolDef(
        name=raw["name"],
        description=raw.get("description"),
        input_schema=raw.get("inputSchema") or raw.get("input_schema") or {},
        output_schema=raw.get("outputSchema") or raw.get("output_schema"),
        annotations=raw.get("annotations") or {},
        title=raw.get("title"),
    )


def _resource_from_raw(raw: dict[str, Any]) -> ResourceDef:
    return ResourceDef(
        uri=raw.get("uri", ""),
        name=raw.get("name"),
        description=raw.get("description"),
        mime_type=raw.get("mimeType") or raw.get("mime_type"),
    )


def _prompt_from_raw(raw: dict[str, Any]) -> PromptDef:
    return PromptDef(
        name=raw["name"],
        description=raw.get("description"),
        arguments=tuple(raw.get("arguments") or ()),
    )


def surface_from_tools(
    tools: list[dict[str, Any]],
    *,
    resources: list[dict[str, Any]] | None = None,
    prompts: list[dict[str, Any]] | None = None,
    server_info: dict[str, Any] | None = None,
    capabilities: dict[str, Any] | None = None,
    protocol_version: str = "",
    transport: Transport = "stdio",
) -> ServerSurface:
    surface = ServerSurface(
        tools=tuple(_tool_from_raw(t) for t in tools),
        resources=tuple(_resource_from_raw(r) for r in (resources or [])),
        prompts=tuple(_prompt_from_raw(p) for p in (prompts or [])),
        server_info=server_info or {},
        capabilities=capabilities or {},
        protocol_version=protocol_version,
        transport=transport,
    )
    return surface.with_hash()


def surface_from_dump(path: str | Path) -> ServerSurface:
    """Load a ``tools/list`` dump for ``static`` mode. Accepts either a bare list, a
    ``{"tools": [...]}`` object, or a full ``{"result": {"tools": [...]}}`` JSON-RPC frame."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        payload: dict[str, Any] = {"tools": data}
    elif "result" in data and isinstance(data["result"], dict):
        payload = data["result"]
    else:
        payload = data
    return surface_from_tools(
        payload.get("tools", []),
        resources=payload.get("resources"),
        prompts=payload.get("prompts"),
        server_info=payload.get("serverInfo") or payload.get("server_info") or {},
        capabilities=payload.get("capabilities") or {},
        protocol_version=payload.get("protocolVersion") or payload.get("protocol_version") or "",
        transport="stdio",
    )
