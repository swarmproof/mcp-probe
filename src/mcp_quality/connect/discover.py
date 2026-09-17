"""Surface construction — from live discovery results or an offline JSON dump.

``surface_from_dump`` powers ``static`` mode: it ingests the ``tools/list`` shape that
registries and CI already produce, so mcp-quality can score a server with no process to
spawn (REQ-C7 static-ok, ADR-006). Both entry points normalize MCP's camelCase
(``inputSchema``/``outputSchema``) and compute the canonical ``surface_hash``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp_quality.models import (
    PromptDef,
    ResourceDef,
    ServerSurface,
    ToolDef,
    Transport,
)

# MCP annotation hints: SDK v1 (and the wire/dump format) use camelCase; SDK v2 emits
# snake_case. We canonicalize to camelCase at this single boundary so every engine reads
# one key set (ADR-003: normalize at the edge).
_CANON_ANNOTATION = {
    "read_only_hint": "readOnlyHint",
    "destructive_hint": "destructiveHint",
    "idempotent_hint": "idempotentHint",
    "open_world_hint": "openWorldHint",
}


def _normalize_annotations(raw: dict[str, Any] | None) -> dict[str, Any]:
    """camel/snake → canonical camelCase, dropping None values so an all-None hint block
    (SDK v2 emits every hint as null) reads as 'no annotations declared' — which SC1 needs."""
    out: dict[str, Any] = {}
    for key, value in (raw or {}).items():
        if value is None:
            continue
        out[_CANON_ANNOTATION.get(key, key)] = value
    return out


def _tool_from_raw(raw: dict[str, Any]) -> ToolDef:
    return ToolDef(
        name=raw["name"],
        description=raw.get("description"),
        input_schema=raw.get("inputSchema") or raw.get("input_schema") or {},
        output_schema=raw.get("outputSchema") or raw.get("output_schema"),
        annotations=_normalize_annotations(raw.get("annotations")),
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
    """Load a ``tools/list`` dump file for ``static`` mode (see :func:`surface_from_payload`)."""
    return surface_from_payload(json.loads(Path(path).read_text(encoding="utf-8")))


def surface_from_payload(data: Any) -> ServerSurface:
    """Build a surface from an in-memory ``tools/list`` payload. Accepts a bare list, a
    ``{"tools": [...]}`` object, or a full ``{"result": {"tools": [...]}}`` JSON-RPC frame.
    Powers both file-based ``static`` mode and the registry scoring API."""
    if isinstance(data, list):
        payload: dict[str, Any] = {"tools": data}
    elif isinstance(data, dict) and "result" in data and isinstance(data["result"], dict):
        payload = data["result"]
    elif isinstance(data, dict):
        payload = data
    else:
        raise ValueError("payload must be a list or object with a 'tools' array")
    return surface_from_tools(
        payload.get("tools", []),
        resources=payload.get("resources"),
        prompts=payload.get("prompts"),
        server_info=payload.get("serverInfo") or payload.get("server_info") or {},
        capabilities=payload.get("capabilities") or {},
        protocol_version=payload.get("protocolVersion") or payload.get("protocol_version") or "",
        transport="stdio",
    )
