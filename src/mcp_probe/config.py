"""Configuration resolution — precedence: **flags > file > env > default** (TEST-PLAN §7).

A single :class:`ProbeConfig` is threaded through :class:`~mcp_probe.models.ProbeContext`
to every engine, so an engine's behaviour is a pure function of (surface, config).
Config is loaded once, up front, from three layers merged in strict precedence order.
"""

from __future__ import annotations

import os
import tomllib  # stdlib on the supported Python (>=3.11)
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_FILENAMES = (".mcp-probe.toml", "mcp-probe.toml")
ENV_PREFIX = "MCP_PROBE_"

# The five families in canonical order, and which are on the zero-LLM fast path.
FAST_PATH_FAMILIES = ("contract", "cost")
LIVE_FAMILIES = ("contract", "performance", "security")  # need a live client for full scoring
LLM_FAMILIES = ("legibility",)
ALL_FAMILIES = ("contract", "legibility", "cost", "performance", "security")


@dataclass
class ProbeConfig:
    """Resolved run configuration. Every field has a safe default so the fast path
    runs with zero flags and zero external services (NFR-1, NFR-5)."""

    # --- target / mode ---
    target: str = ""  # command (stdio) or URL (http); empty in `static` mode
    transport: str = "auto"  # "auto" | "stdio" | "streamable-http" | "sse"
    static_path: str | None = None  # path to a tools/list JSON dump → offline mode
    stdio_timeout: float = 60.0  # Cisco-parity default; servers may fetch deps on first run

    # --- which families to run ---
    families: tuple[str, ...] = FAST_PATH_FAMILIES  # default = zero-LLM fast path
    allow_writes: bool = False  # gate destructive tool invocation (NFR-9, ADR-009)

    # --- gating ---
    fail_under: str | None = None  # letter grade; overall < this → exit 1
    fail_under_family: dict[str, str] = field(default_factory=dict)  # per-family gates
    no_regressions: bool = False  # any family dropped vs snapshot → exit 1

    # --- legibility ([llm]) ---
    model: str | None = None  # e.g. "ollama:qwen2.5-3b", "anthropic:claude-haiku-4-5"
    seed: int = 42
    goal_set_version: str = "1"
    goals_path: str | None = None  # .mcp-probe/goals.yaml

    # --- cost ---
    price_points: tuple[str, ...] = ()  # e.g. ("anthropic:claude-sonnet-5",); default set applied
    tokenizer: str = "o200k_base"  # deterministic offline tiktoken encoding (REQ-$4)

    # --- performance ([net]) ---
    concurrency: int = 50
    load_duration: float = 10.0  # seconds of sustained hold for leak detection

    # --- security ---
    deep_security: bool = False  # shell out to mcp-scan / Cisco (REQ-S4)

    # --- outputs ---
    json_out: bool = False
    html_out: str | None = None
    emit_stampede: str | None = None  # write the stampede handoff seed (ARCHITECTURE §9)
    snapshot_path: str = ".mcp-probe/snapshot.json"
    cache_dir: str = ".mcp-probe/cache"

    def with_overrides(self, **overrides: Any) -> ProbeConfig:
        """Return a copy with non-None overrides applied (used to layer CLI flags on top)."""
        clean = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **clean)


def _coerce(field_type: Any, raw: str) -> Any:
    """Coerce an env/file string into the dataclass field's type (best-effort)."""
    origin = getattr(field_type, "__name__", str(field_type))
    if field_type is bool or origin == "bool":
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if field_type is int or origin == "int":
        return int(raw)
    if field_type is float or origin == "float":
        return float(raw)
    return raw


def _from_env() -> dict[str, Any]:
    """Read ``MCP_PROBE_<FIELD>`` env vars into a partial config dict."""
    out: dict[str, Any] = {}
    type_by_name = {f.name: f.type for f in fields(ProbeConfig)}
    for key, value in os.environ.items():
        if not key.startswith(ENV_PREFIX):
            continue
        name = key[len(ENV_PREFIX) :].lower()
        if name in type_by_name:
            out[name] = _coerce(type_by_name[name], value)
    return out


def _from_file(start: Path) -> dict[str, Any]:
    """Load the nearest ``.mcp-probe.toml`` walking up from ``start`` (repo-root friendly)."""
    known = {f.name for f in fields(ProbeConfig)}
    for directory in (start, *start.parents):
        for filename in DEFAULT_CONFIG_FILENAMES:
            candidate = directory / filename
            if candidate.is_file():
                with candidate.open("rb") as fh:
                    data = tomllib.load(fh)
                # accept either a flat table or a [tool.mcp-probe] section
                section = data.get("tool", {}).get("mcp-probe", data)
                return {k.replace("-", "_"): v for k, v in section.items() if k.replace("-", "_") in known}
    return {}


def load_config(
    *,
    cli_overrides: dict[str, Any] | None = None,
    cwd: Path | None = None,
) -> ProbeConfig:
    """Resolve the effective config with strict precedence flags > file > env > default.

    ``cli_overrides`` should contain only explicitly-set flags (None values are ignored),
    so an unset flag never clobbers a file/env value.
    """
    cwd = cwd or Path.cwd()
    merged: dict[str, Any] = {}
    merged.update(_from_env())  # lowest non-default layer
    merged.update(_from_file(cwd))  # file beats env
    if cli_overrides:  # flags beat everything
        merged.update({k: v for k, v in cli_overrides.items() if v is not None})
    return ProbeConfig(**merged) if merged else ProbeConfig()
