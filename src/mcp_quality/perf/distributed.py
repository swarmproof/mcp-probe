"""Cross-host distributed load (#74) — a coordinator fans the load curve across N worker
*processes* (local by default; remote via a command template) and merges their results
through the existing fleet math (``aggregate_results``).

This is the multi-machine step up from the in-process fleet (#51): #51 runs N coroutines on
one event loop; this runs N real processes (and, with a command template like
``ssh host -- …``, N hosts). The aggregation layer is unchanged — only *distribution* is new.
A ``launcher`` seam keeps it testable with no real subprocess, and makes remote a drop-in.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import sys
from collections.abc import Awaitable, Callable
from typing import Any

from mcp_quality.perf.load import LoadResult, aggregate_results

# Runs one worker with the job; returns its LoadResult, or None if that worker failed.
WorkerLauncher = Callable[[int, dict[str, Any]], Awaitable["LoadResult | None"]]


def _parse_worker_output(stdout: bytes) -> LoadResult | None:
    """Last non-empty stdout line is the JSON LoadResult (tolerates leading log noise)."""
    lines = [ln for ln in stdout.decode(errors="replace").splitlines() if ln.strip()]
    if not lines:
        return None
    try:
        return LoadResult.from_dict(json.loads(lines[-1]))
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def make_command_launcher(command: str | None) -> WorkerLauncher:
    """Build a launcher. ``command`` is a shell template for running the worker; ``None`` →
    the local interpreter. For remote: ``"ssh host1 -- python -m mcp_quality.perf.worker"``.
    The worker reads its job from stdin and prints a JSON LoadResult."""
    argv = shlex.split(command) if command else [sys.executable, "-m", "mcp_quality.perf.worker"]

    async def launcher(index: int, job: dict[str, Any]) -> LoadResult | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate(json.dumps(job).encode())
            if proc.returncode != 0:
                return None
            return _parse_worker_output(out)
        except Exception:
            return None

    return launcher


async def run_coordinated_load(
    job: dict[str, Any],
    worker_count: int,
    *,
    launcher: WorkerLauncher | None = None,
) -> tuple[LoadResult, list[LoadResult]]:
    """Fan the job across ``worker_count`` workers concurrently and aggregate. Returns the
    fleet-wide result + the surviving per-worker results (a worker that fails drops out)."""
    launch = launcher or make_command_launcher(None)
    outcomes = await asyncio.gather(*(launch(i, job) for i in range(worker_count)))
    per_worker = [r for r in outcomes if r is not None]
    return aggregate_results(per_worker), per_worker
