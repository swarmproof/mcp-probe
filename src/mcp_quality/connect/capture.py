"""Message-capture harness (#33) — the SDK-free record of server-originated messages.

MCP servers can talk *back*: ``sampling/createMessage`` (ask the client's LLM to generate),
``elicitation/create`` (ask the user for input), tasks, etc. Those are where a server can
smuggle instructions into your model or phish your user — but they only appear at runtime,
so we need to *capture* them. This module is the pure record: the transport (the only
SDK-aware module) registers callbacks that append to a :class:`CaptureLog`; engines read
the log without ever importing the SDK. Keeping the data model here means ``FakeClient``
can seed a log for tests with no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SampledMessage:
    """A captured ``sampling/createMessage`` the server asked the client to run."""

    system_prompt: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    include_context: str | None = None  # "none" | "thisServer" | "allServers"
    max_tokens: int | None = None

    def all_text(self) -> str:
        """Flatten system prompt + message text for pattern scanning."""
        parts = [self.system_prompt]
        for m in self.messages:
            content = m.get("content") if isinstance(m, dict) else None
            if isinstance(content, dict):
                parts.append(str(content.get("text", "")))
            elif isinstance(content, str):
                parts.append(content)
        return "\n".join(p for p in parts if p)


@dataclass
class ElicitedRequest:
    """A captured ``elicitation/create`` — the server asking the user for input."""

    message: str = ""
    mode: str = "unknown"  # "form" | "url" | "unknown"
    schema: dict[str, Any] = field(default_factory=dict)
    url: str | None = None


@dataclass
class ResourceResolution:
    """Result of attempting to resolve one advertised resource / resource_link."""

    uri: str
    ok: bool
    error: str | None = None


@dataclass
class CaptureLog:
    """Everything the harness observed during a run. Empty lists + False flags = the
    capability was never exercised → engines report those sub-checks 'not measured'."""

    sampling: list[SampledMessage] = field(default_factory=list)
    elicitations: list[ElicitedRequest] = field(default_factory=list)
    used_sampling: bool = False
    used_elicitation: bool = False
