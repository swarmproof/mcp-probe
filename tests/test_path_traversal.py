"""Path-traversal surface lint tests (issue #65) — OWASP MCP05, low false-positive."""

from __future__ import annotations

from mcp_quality.config import ProbeConfig
from mcp_quality.engines.security import SecurityEngine
from mcp_quality.models import ProbeContext
from mcp_quality.security.path_traversal import scan_path_traversal

from .conftest import make_surface


def _tool(name: str, props: dict) -> dict:
    return {
        "name": name,
        "description": f"{name} a thing.",
        "inputSchema": {"type": "object", "properties": props},
        "annotations": {"readOnlyHint": True},
    }


def _codes(surface) -> set[str]:
    return {f.code for f in scan_path_traversal(surface)}


# -- fires on an unconstrained path-like parameter -----------------------------

def test_fires_on_unconstrained_path_param():
    surface = make_surface([_tool("read_file", {"path": {"type": "string"}})])
    findings = scan_path_traversal(surface)
    assert [f.code for f in findings] == ["S4-path-traversal-surface"]
    assert findings[0].tool == "read_file"
    assert findings[0].evidence == {"params": ["path"]}


def test_matches_common_path_name_variants():
    for pname in ("file", "filename", "filepath", "dir", "directory", "folder",
                  "inputFilePath", "output_dir", "src_path"):
        surface = make_surface([_tool("t", {pname: {"type": "string"}})])
        assert "S4-path-traversal-surface" in _codes(surface), pname


def test_lists_every_unconstrained_path_param_for_a_tool():
    surface = make_surface([_tool("copy", {
        "src": {"type": "string"},  # not a path token → ignored
        "source_path": {"type": "string"},
        "dest_file": {"type": "string"},
    })])
    findings = scan_path_traversal(surface)
    assert len(findings) == 1
    assert findings[0].evidence == {"params": ["source_path", "dest_file"]}


# -- silent when the param is constrained (low false-positive) ------------------

def test_silent_when_param_has_pattern():
    surface = make_surface([_tool("read_file", {
        "path": {"type": "string", "pattern": r"^[\w./-]+$"}})])
    assert scan_path_traversal(surface) == []


def test_silent_when_param_has_enum():
    surface = make_surface([_tool("read_log", {
        "file": {"type": "string", "enum": ["app.log", "err.log"]}})])
    assert scan_path_traversal(surface) == []


def test_silent_when_param_has_format():
    surface = make_surface([_tool("fetch", {
        "path": {"type": "string", "format": "uri"}})])
    assert scan_path_traversal(surface) == []


# -- silent for non-path params (tight matcher, no substring false-positives) ---

def test_silent_for_non_path_params():
    surface = make_surface([_tool("search", {
        "query": {"type": "string"},
        "profile": {"type": "string"},   # contains "file" but is not the token
        "compiler": {"type": "string"},  # contains "file" substring too
        "filter": {"type": "string"},
    })])
    assert scan_path_traversal(surface) == []


def test_silent_for_schema_without_properties():
    surface = make_surface([{"name": "ping", "description": "Ping.",
                             "inputSchema": {"type": "object"}}])
    assert scan_path_traversal(surface) == []


# -- engine integration --------------------------------------------------------

async def test_engine_surfaces_path_traversal_finding_with_owasp_id():
    surface = make_surface([_tool("read_file", {"path": {"type": "string"}})])
    fs = await SecurityEngine().run(ProbeContext(surface=surface, config=ProbeConfig(), client=None))
    hits = [f for f in fs.findings if f.code == "S4-path-traversal-surface"]
    assert hits and hits[0].owasp_id == "MCP05:2025"
    assert fs.metrics["path_traversal"] == 1


async def test_engine_path_traversal_metric_zero_when_clean():
    surface = make_surface([_tool("read_log", {
        "file": {"type": "string", "enum": ["app.log"]}})])
    fs = await SecurityEngine().run(ProbeContext(surface=surface, config=ProbeConfig(), client=None))
    assert fs.metrics["path_traversal"] == 0
    assert not any(f.code == "S4-path-traversal-surface" for f in fs.findings)
