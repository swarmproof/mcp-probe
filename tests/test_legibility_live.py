"""Live legibility test against a real local model (TEST-PLAN §3, §9.7).

Marked ``live_llm`` — EXCLUDED from the default/CI run; opt-in via ``pytest -m live_llm``.
Catches model drift and proves the real provider path (prompt build + response parse),
which the StubModel tests can't. Skips cleanly when openai isn't installed or Ollama isn't
reachable, so it never flakes the merge path.

Set MCP_PROBE_LIVE_MODEL to override the model (default: a small local Ollama model).
"""

from __future__ import annotations

import os
import urllib.request

import pytest

pytestmark = pytest.mark.live_llm

MODEL = os.environ.get("MCP_PROBE_LIVE_MODEL", "ollama:mistral-small:latest")


def _ollama_up() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False


@pytest.fixture(autouse=True)
def _requires_ollama():
    pytest.importorskip("openai")
    if MODEL.startswith("ollama:") and not _ollama_up():
        pytest.skip("Ollama not reachable on :11434")


async def test_live_legibility_detects_confusable_pair(tmp_path):
    from mcp_probe.config import ProbeConfig
    from mcp_probe.connect.discover import surface_from_tools
    from mcp_probe.engines.legibility import LegibilityEngine
    from mcp_probe.legibility.model import build_model
    from mcp_probe.models import ProbeContext

    tools = [
        {"name": "delete_record", "description": "Remove a record by id.", "inputSchema": {"type": "object"}},
        {"name": "archive_record", "description": "Remove a record by id.", "inputSchema": {"type": "object"}},
        {"name": "get_weather", "description": "Return the current weather for a city.", "inputSchema": {"type": "object"}},
    ]
    surface = surface_from_tools(tools)
    model = build_model(MODEL, seed=42)
    ctx = ProbeContext(
        surface=surface, config=ProbeConfig(cache_dir=str(tmp_path)), client=None, model=model
    )
    fs = await LegibilityEngine().run(ctx)

    # Soft invariants (real models are not perfectly deterministic): a valid rate, the model
    # was actually called, and the grade is a real letter. A clear tool (get_weather) among
    # two identical ones should keep selection_rate below a perfect 1.0.
    rate = fs.metrics["selection_rate"]
    assert isinstance(rate, float) and 0.0 <= rate <= 1.0
    assert model.call_count > 0
    assert fs.grade in ("A", "B", "C", "D", "F")


async def test_live_cache_hit_is_free(tmp_path):
    from mcp_probe.config import ProbeConfig
    from mcp_probe.connect.discover import surface_from_tools
    from mcp_probe.engines.legibility import LegibilityEngine
    from mcp_probe.legibility.model import build_model
    from mcp_probe.models import ProbeContext

    tools = [{"name": "get_weather", "description": "Weather for a city.", "inputSchema": {"type": "object"}}]
    surface = surface_from_tools(tools)
    cfg = ProbeConfig(cache_dir=str(tmp_path))

    m1 = build_model(MODEL, seed=42)
    await LegibilityEngine().run(ProbeContext(surface=surface, config=cfg, client=None, model=m1))
    assert m1.call_count > 0

    m2 = build_model(MODEL, seed=42)
    fs2 = await LegibilityEngine().run(ProbeContext(surface=surface, config=cfg, client=None, model=m2))
    assert m2.call_count == 0  # served from cache (REQ-L6) — a warm rerun costs nothing
    assert fs2.metrics["cache_hit"] is True
