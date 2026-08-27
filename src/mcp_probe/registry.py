"""Registry scoring API (issue #10) — hosted ``static`` scoring for marketplaces.

A stateless HTTP wrapper over the offline scoring path: a registry POSTs a ``tools/list``
dump and gets back the versioned ``mcp-probe/report@1`` JSON. Parity with
``mcp-probe static`` — fast path + security-lite, **no LLM and no live server** (ADR-006),
so it runs air-gapped and deterministically. Every response carries ``rubric_version`` and
a ``provenance_hash``; ``POST /verify`` re-scores a payload and checks a claimed hash so a
registry can detect a hand-edited grade (Badge spec §8 anti-gaming).

The server deps (starlette/uvicorn) live in the ``[registry]`` extra; the scoring core
(:func:`score_payload`) is import-light and usable without them.
"""

from __future__ import annotations

from typing import Any

from mcp_probe import RUBRIC_VERSION
from mcp_probe.config import ProbeConfig
from mcp_probe.connect import surface_from_payload
from mcp_probe.pipeline import run_probe
from mcp_probe.report import report_to_dict

# Only static-ok families — the API never spawns a process or calls a model.
REGISTRY_FAMILIES = ("contract", "cost", "security")


async def score_payload(payload: Any, *, families: tuple[str, ...] = REGISTRY_FAMILIES) -> dict[str, Any]:
    """Score an in-memory tools/list payload → report dict. Pure of network/LLM."""
    surface = surface_from_payload(payload)
    config = ProbeConfig(families=families, static_path="<registry>")
    outcome = await run_probe(config, surface=surface)  # client=None → static
    return report_to_dict(outcome.report, include_meta=False)


def build_app() -> Any:
    """Construct the Starlette app. Imported lazily so the base install needs no web deps."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def healthz(_request: Request) -> JSONResponse:
        return JSONResponse(
            {"status": "ok", "rubric_version": RUBRIC_VERSION},
            headers={"X-MCP-Probe-Rubric": RUBRIC_VERSION},
        )

    async def score(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)
        try:
            report = await score_payload(payload)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse(report, headers={"X-MCP-Probe-Rubric": RUBRIC_VERSION})

    async def verify(request: Request) -> JSONResponse:
        """Body: {"tools": [...], "provenance_hash": "sha256:…"}. Re-scores and compares."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)
        claimed = body.get("provenance_hash")
        if not claimed:
            return JSONResponse({"error": "missing provenance_hash"}, status_code=400)
        try:
            report = await score_payload(body)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        actual = report["provenance_hash"]
        return JSONResponse(
            {"verified": actual == claimed, "claimed": claimed, "actual": actual,
             "rubric_version": report["rubric_version"]}
        )

    return Starlette(routes=[
        Route("/healthz", healthz, methods=["GET"]),
        Route("/score", score, methods=["POST"]),
        Route("/verify", verify, methods=["POST"]),
    ])


def serve(host: str = "127.0.0.1", port: int = 8080) -> None:  # pragma: no cover - runs a server
    import uvicorn

    uvicorn.run(build_app(), host=host, port=port)
