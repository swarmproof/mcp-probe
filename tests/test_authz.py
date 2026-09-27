"""Authorization least-privilege tests (issue #48) — OWASP MCP07, low false-positive."""

from __future__ import annotations

from mcp_quality.config import ProbeConfig
from mcp_quality.engines.security import SecurityEngine
from mcp_quality.models import ProbeContext
from mcp_quality.pipeline import run_probe
from mcp_quality.security.authz import auth_block, scan_authorization

from .conftest import make_surface

_RO = {"name": "get_x", "description": "Return x.", "inputSchema": {"type": "object"},
       "annotations": {"readOnlyHint": True}}
_WRITE = {"name": "delete_x", "description": "Delete x.", "inputSchema": {"type": "object"}}


def _surface(caps, tools=None):
    return make_surface(tools or [_RO], capabilities=caps)


def _codes(surface):
    return {f.code for f in scan_authorization(surface)}


# -- degradation: no auth declared → not measured, never zeroed ----------------

def test_no_auth_metadata_is_not_measured():
    surface = _surface({})
    assert auth_block(surface) is None
    assert scan_authorization(surface) == []


async def test_engine_reports_authz_not_measured_without_auth():
    ctx = ProbeContext(surface=_surface({}), config=ProbeConfig(), client=None)
    fs = await SecurityEngine().run(ctx)
    assert fs.metrics["authz"] == "not measured (no auth metadata)"


# -- A1 scope over-grant -------------------------------------------------------

def test_a1_broad_wildcard_scope():
    assert "A1-scope-overgrant" in _codes(_surface({"authorization": {"scopes": ["*"]}}))


def test_a1_admin_scope():
    assert "A1-scope-overgrant" in _codes(_surface({"oauth": {"scopes_supported": ["admin"]}}))


def test_a1_write_scope_on_read_only_toolset():
    surface = _surface({"authorization": {"scope": "read:data write:data"}}, tools=[_RO])
    assert "A1-scope-overgrant" in _codes(surface)


def test_a1_write_scope_ok_when_toolset_has_writes():
    surface = _surface({"authorization": {"scope": "read:data write:data"}}, tools=[_RO, _WRITE])
    # a write scope is legitimate when a write tool exists → no read-only-overgrant finding
    assert "A1-scope-overgrant" not in _codes(surface)


# -- A2 audience / resource-indicator hygiene ----------------------------------

def test_a2_issuer_without_resource():
    surface = _surface({"authorization": {"issuer": "https://auth.example.com", "scopes": ["read"]}})
    assert "A2-audience-hygiene" in _codes(surface)


def test_a2_wildcard_resource():
    surface = _surface({"authorization": {
        "issuer": "https://auth.example.com", "resource": "*", "scopes": ["read"]}})
    assert "A2-audience-hygiene" in _codes(surface)


# -- A3 insecure transport -----------------------------------------------------

def test_a3_http_issuer():
    surface = _surface({"authorization": {
        "issuer": "http://auth.example.com", "resource": "https://api.example.com", "scopes": ["read"]}})
    codes = _codes(surface)
    assert "A3-insecure-authz" in codes


# -- clean authz ---------------------------------------------------------------

def test_clean_least_privilege_authz_is_silent_but_measured():
    surface = _surface({"authorization": {
        "issuer": "https://auth.example.com",
        "resource": "https://api.example.com",
        "scopes": ["read:data"],
    }}, tools=[_RO])
    assert scan_authorization(surface) == []
    assert auth_block(surface) is not None  # measured, just clean


# -- engine + static mode ------------------------------------------------------

async def test_engine_surfaces_authz_findings_and_measured():
    surface = _surface({"authorization": {"scopes": ["*"], "issuer": "https://a.example.com"}})
    fs = await SecurityEngine().run(ProbeContext(surface=surface, config=ProbeConfig(), client=None))
    assert fs.metrics["authz"] == "measured"
    assert any(f.code.startswith("A1") for f in fs.findings)
    assert any(f.owasp_id == "MCP07:2025" for f in fs.findings)


async def test_static_mode_grades_authz_from_dump():
    # #48 acceptance: works offline when the metadata is in the surface/dump.
    surface = _surface({"authorization": {"scopes": ["admin"], "issuer": "http://a.example.com",
                                          "resource": "https://api.example.com"}})
    cfg = ProbeConfig(families=("security",), static_path="unused")
    outcome = await run_probe(cfg, surface=surface)  # client=None → static
    sec = outcome.report.families["security"]
    assert sec.metrics["authz"] == "measured"
    assert {"A1-scope-overgrant", "A3-insecure-authz"} <= {f.code for f in sec.findings}
