"""Load worker (#74) — runs the load curve against a target in its *own process* and emits a
JSON ``LoadResult`` on stdout.

The coordinator (``perf/distributed.py``) spawns N of these — locally, or on remote hosts via
a command template — and aggregates their results. Unlike the in-process fleet (#51), which
shares one event loop, each worker is a real separate process with its own connections and
CPU — the honest foundation for multi-host load. Invoke: ``python -m mcp_quality.perf.worker``
with a JSON job on stdin.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any


def _run_job(job: dict[str, Any]) -> dict[str, Any]:
    from mcp_quality.config import ProbeConfig
    from mcp_quality.connect.transport import connect
    from mcp_quality.perf.load import ConcurrencyCurve, run_load

    cfg = ProbeConfig(
        target=job["target"],
        transport=job.get("transport", "auto"),
        headers=job.get("headers") or {},
        stdio_timeout=float(job.get("stdio_timeout", 60.0)),
    )
    curve = ConcurrencyCurve(**job["curve"])

    async def factory() -> Any:
        client, _surface = await connect(cfg)
        return client

    async def main() -> dict[str, Any]:
        result = await run_load(factory, job["tool"], job.get("args") or {}, curve)
        return result.to_dict()

    return asyncio.run(main())


def main() -> int:
    job = json.load(sys.stdin)
    print(json.dumps(_run_job(job)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
