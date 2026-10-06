"""Registry scoring API (issue #10) — hosted ``static`` scoring for marketplaces.

A stateless HTTP wrapper over the offline scoring path: a registry POSTs a ``tools/list``
dump and gets back the versioned ``mcp-quality/report@1`` JSON. Parity with
``mcp-quality static`` — fast path + security-lite, **no LLM and no live server** (ADR-006),
so it runs air-gapped and deterministically. Every response carries ``rubric_version`` and
a ``provenance_hash``; ``POST /verify`` re-scores a payload and checks a claimed hash so a
registry can detect a hand-edited grade (Badge spec §8 anti-gaming). For marketplaces (#52):
``POST /score/batch`` scores many servers in one request (ingest), and ``POST /freshness``
flags a stored grade as stale when the rubric or the server's surface has changed. No
secrets are needed — the API scores a provided dump; private *live* servers are scored by
``mcp-quality run --header`` on the registry's side, not here.

The server deps (starlette/uvicorn) live in the ``[registry]`` extra; the scoring core
(:func:`score_payload`) is import-light and usable without them.
"""

from __future__ import annotations

from typing import Any

from mcp_quality import RUBRIC_VERSION
from mcp_quality.config import ProbeConfig
from mcp_quality.connect import surface_from_payload
from mcp_quality.pipeline import run_probe
from mcp_quality.report import report_to_dict

# Only static-ok families — the API never spawns a process or calls a model.
REGISTRY_FAMILIES = ("contract", "cost", "security")


async def score_payload(payload: Any, *, families: tuple[str, ...] = REGISTRY_FAMILIES) -> dict[str, Any]:
    """Score an in-memory tools/list payload → report dict. Pure of network/LLM."""
    surface = surface_from_payload(payload)
    config = ProbeConfig(families=families, static_path="<registry>")
    outcome = await run_probe(config, surface=surface)  # client=None → static
    return report_to_dict(outcome.report, include_meta=False)


async def score_batch(
    servers: list[Any], *, families: tuple[str, ...] = REGISTRY_FAMILIES
) -> dict[str, Any]:
    """Score many servers in one request (registry ingest, #52). Each entry is a tools/list
    payload optionally carrying an ``id``; a bad payload fails that entry, not the batch."""
    results: list[dict[str, Any]] = []
    for entry in servers:
        sid = entry.get("id") if isinstance(entry, dict) else None
        try:
            results.append({"id": sid, "report": await score_payload(entry, families=families)})
        except ValueError as exc:
            results.append({"id": sid, "error": str(exc)})
    return {"results": results, "count": len(results), "rubric_version": RUBRIC_VERSION}


def freshness(payload: Any, *, rubric_version: str, surface_hash: str) -> dict[str, Any]:
    """Is a stored grade still current (#52)? A listed grade goes stale when the scoring
    rubric changes (re-score needed for comparability) or the server's surface changes.
    Cheap: recomputes the surface hash only, no scoring."""
    current_hash = surface_from_payload(payload).surface_hash
    rubric_stale = rubric_version != RUBRIC_VERSION
    surface_stale = surface_hash != current_hash
    reasons: list[str] = []
    if rubric_stale:
        reasons.append(f"rubric changed ({rubric_version} → {RUBRIC_VERSION})")
    if surface_stale:
        reasons.append("server surface changed since the last score")
    return {
        "stale": rubric_stale or surface_stale,
        "reasons": reasons,
        "current_rubric_version": RUBRIC_VERSION,
        "current_surface_hash": current_hash,
    }


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

    async def score_batch_route(request: Request) -> JSONResponse:
        """Body: {"servers": [{"id": "...", "tools": [...]}, ...]} → one report per server."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)
        servers = body.get("servers")
        if not isinstance(servers, list):
            return JSONResponse({"error": "body must contain a 'servers' array"}, status_code=400)
        result = await score_batch(servers)
        return JSONResponse(result, headers={"X-MCP-Probe-Rubric": RUBRIC_VERSION})

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

    async def freshness_route(request: Request) -> JSONResponse:
        """Body: {"tools": [...], "rubric_version": "...", "surface_hash": "sha256:…"}."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)
        rubric, sh = body.get("rubric_version"), body.get("surface_hash")
        if not rubric or not sh:
            return JSONResponse(
                {"error": "missing rubric_version or surface_hash"}, status_code=400)
        try:
            return JSONResponse(freshness(body, rubric_version=rubric, surface_hash=sh))
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    return Starlette(routes=[
        Route("/healthz", healthz, methods=["GET"]),
        Route("/score", score, methods=["POST"]),
        Route("/score/batch", score_batch_route, methods=["POST"]),
        Route("/verify", verify, methods=["POST"]),
        Route("/freshness", freshness_route, methods=["POST"]),
    ])


def serve(host: str = "127.0.0.1", port: int = 8080) -> None:  # pragma: no cover - runs a server
    import uvicorn

    uvicorn.run(build_app(), host=host, port=port)
