"""Legibility result cache (REQ-L6) — the flakiness/cost answer.

Cache key = ``(surface_hash, model_id, seed, goal_set_version)`` (ADR-004). A rerun on an
unchanged surface is a hit → ~$0, instant, byte-identical, and the model is invoked zero
times (which the determinism test asserts). Because the key includes ``surface_hash``,
editing one tool description invalidates only the affected run, not the whole cache.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def cache_key(surface_hash: str, model_id: str, seed: int, goal_set_version: str) -> str:
    basis = f"{surface_hash}|{model_id}|{seed}|{goal_set_version}"
    return hashlib.sha256(basis.encode()).hexdigest()[:24]


class LegibilityCache:
    def __init__(self, cache_dir: str | Path) -> None:
        self._dir = Path(cache_dir)

    def _path(self, key: str) -> Path:
        return self._dir / f"legibility-{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        p = self._path(key)
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def put(self, key: str, value: dict[str, Any]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(key).write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
