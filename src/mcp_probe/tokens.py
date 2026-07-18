"""Token counting — deterministic, offline-first, provider-agnostic (REQ-$4).

The Cost engine must produce a *reproducible* number on the CI fast path with no network
(NFR-2, NFR-8). ``tiktoken`` is the preferred counter but it fetches its BPE vocab on
first use, so we degrade to a deterministic character/word heuristic when it is
unavailable — never failing, always reproducible. When a provider key is present the
engine can additionally ask for an *authoritative* count (e.g. Anthropic ``count_tokens``),
marked as such in the report.

Tool serialization mirrors how a toolset actually enters an LLM's context: the
Anthropic ``tools`` array shape ``{name, description, input_schema}`` — that JSON is what
every agent pays for just to *see* the tools (the mcp-xray insight, REQ-$1).
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from mcp_probe.models import ToolDef


def serialize_tool(tool: ToolDef) -> dict[str, object]:
    """One tool in the provider-neutral (Anthropic-style) tool shape."""
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.input_schema,
    }


def serialize_toolset(tools: tuple[ToolDef, ...]) -> str:
    """The whole toolset as it appears in context, as a stable JSON string."""
    return json.dumps([serialize_tool(t) for t in tools], sort_keys=True, ensure_ascii=False)


class TokenCounter(Protocol):
    name: str

    def count(self, text: str) -> int: ...


class HeuristicCounter:
    """Deterministic, offline, network-free fallback. Approximates BPE by counting
    word-ish and punctuation runs — stable across machines, good enough for *relative*
    per-tool attribution which is what the score cares about."""

    name = "heuristic"
    _token_re = re.compile(r"\w+|[^\w\s]", re.UNICODE)

    def count(self, text: str) -> int:
        # ~1.3 subword tokens per whitespace/punct token empirically; keep it integral
        # and deterministic. This is a lower-fidelity but fully reproducible counter.
        pieces = self._token_re.findall(text)
        return int(round(len(pieces) * 1.3))


class TiktokenCounter:
    """Authoritative-ish offline counter via tiktoken (once its vocab is cached)."""

    def __init__(self, encoding: str = "o200k_base") -> None:
        import tiktoken  # imported lazily so the package installs without a live download

        self._enc = tiktoken.get_encoding(encoding)
        self.name = f"tiktoken:{encoding}"

    def count(self, text: str) -> int:
        return len(self._enc.encode(text))


def get_counter(encoding: str = "o200k_base") -> TokenCounter:
    """Best available counter: tiktoken if importable + vocab reachable, else heuristic."""
    try:
        return TiktokenCounter(encoding)
    except Exception:  # ImportError, or vocab fetch failed in an air-gapped env
        return HeuristicCounter()
