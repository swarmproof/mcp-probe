"""Trace sink — the OpenTelemetry GenAI semantic-conventions *profile* (ARCHITECTURE §10).

Deliberately NOT a bespoke schema: events use the ``gen_ai.*`` conventions plus the
``swarmproof.*`` extension, so a trace mcp-probe emits is one that stampede can replay via
the ``--from-probe`` handoff. This module is a thin JSONL sink; it does not pull in the
full OTel SDK (keeping the fast path dependency-light), but it mirrors the profile's
attribute names so swapping in a real exporter later is mechanical.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TraceSink:
    """Collects profile-shaped events in memory; optionally flushes to a JSONL file."""

    def __init__(self, *, run_id: str = "", seq_start: int = 0) -> None:
        self._events: list[dict[str, Any]] = []
        self._run_id = run_id
        self._seq = seq_start

    def event(self, family: str, name: str, attrs: dict[str, Any] | None = None) -> None:
        """Record one span-event. ``family`` maps to the ``swarmproof.check.family``
        attribute; ``name`` to the event name under the ``gen_ai`` namespace where apt."""
        self._seq += 1
        record: dict[str, Any] = {
            "seq": self._seq,
            "name": name,
            "attributes": {
                "swarmproof.tool": "mcp-probe",
                "swarmproof.check.family": family,
                **(attrs or {}),
            },
        }
        if self._run_id:
            record["attributes"]["swarmproof.run_id"] = self._run_id
        self._events.append(record)

    def gen_ai_span(
        self,
        *,
        operation: str,
        model: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        **extra: Any,
    ) -> None:
        """A GenAI operation span (Legibility model calls) using ``gen_ai.*`` attributes."""
        attrs: dict[str, Any] = {"gen_ai.operation.name": operation}
        if model is not None:
            attrs["gen_ai.request.model"] = model
        if input_tokens is not None:
            attrs["gen_ai.usage.input_tokens"] = input_tokens
        if output_tokens is not None:
            attrs["gen_ai.usage.output_tokens"] = output_tokens
        attrs.update(extra)
        self.event("legibility", "gen_ai.client.inference", attrs)

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(e, sort_keys=True) for e in self._events)

    def flush(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_jsonl() + "\n", encoding="utf-8")
