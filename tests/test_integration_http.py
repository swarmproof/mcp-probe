"""Transport integration tests (TEST-PLAN INT-2/INT-3): probe a real HTTP MCP server
over Streamable-HTTP and legacy SSE. Spawns the fixture on a free port, waits for it to
accept connections, probes it, and tears it down."""

from __future__ import annotations

import contextlib
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from mcp_probe.config import ProbeConfig
from mcp_probe.pipeline import run_probe

pytestmark = [pytest.mark.integration, pytest.mark.e2e]

SERVER = Path(__file__).parent / "servers" / "http_server.py"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_listening(port: int, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
        time.sleep(0.15)
    return False


@contextlib.contextmanager
def _serve(transport: str) -> Iterator[str]:
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(SERVER), "--transport", transport, "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not _wait_until_listening(port):
            raise RuntimeError(f"{transport} fixture server did not start on :{port}")
        path = "/mcp" if transport == "streamable-http" else "/sse"
        yield f"http://127.0.0.1:{port}{path}"
    finally:
        proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)
        if proc.poll() is None:
            proc.kill()


async def test_int2_streamable_http_connect_and_grade():
    with _serve("streamable-http") as url:
        cfg = ProbeConfig(target=url, transport="streamable-http", families=("contract", "cost"))
        outcome = await run_probe(cfg)
    surface = outcome.report.surface
    assert surface.transport == "streamable-http"
    assert {t.name for t in surface.tools} == {"get_weather", "list_cities"}
    assert outcome.report.overall_grade in ("A", "B")


async def test_int2_auto_detects_http_from_url():
    # transport="auto" + an http:// target → streamable-http (no explicit flag needed).
    with _serve("streamable-http") as url:
        cfg = ProbeConfig(target=url, transport="auto", families=("contract",))
        outcome = await run_probe(cfg)
    assert outcome.report.surface.transport == "streamable-http"
    assert len(outcome.report.surface.tools) == 2


async def test_int3_legacy_sse_connect_and_grade():
    with _serve("sse") as url:
        cfg = ProbeConfig(target=url, transport="sse", families=("contract", "cost"))
        outcome = await run_probe(cfg)
    surface = outcome.report.surface
    assert surface.transport == "sse"
    assert {t.name for t in surface.tools} == {"get_weather", "list_cities"}
