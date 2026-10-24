"""Silent-failure detection component tests (issue #64, REQ-C13).

Covers the pure detector (``detect_silent_failure``) for fire + low-false-positive cases,
plus the ContractEngine wiring: it fires live via FakeClient and is "not measured" in static
mode (ADR-006 — never zeroed)."""

from __future__ import annotations

from mcp_quality.config import ProbeConfig
from mcp_quality.connect.client import FakeClient, InvokeResult
from mcp_quality.contract.silent_failure import detect_silent_failure, promises_content
from mcp_quality.engines.contract import ContractEngine

from .conftest import make_ctx

_PROMISING_SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "string"}},
    "required": ["value"],
}


# -- pure detector: fire cases ------------------------------------------------

def test_detect_flags_error_shaped_success():
    result = InvokeResult("run", is_error=False, content="Traceback (most recent call last): boom")
    f = detect_silent_failure("run", result, None)
    assert f is not None
    assert f.code == "C13-silent-failure"
    assert f.severity.name == "MEDIUM"


def test_detect_flags_exception_marker_in_structured():
    result = InvokeResult("run", is_error=False, content=[], structured={"msg": "ValueError: bad id"})
    f = detect_silent_failure("run", result, None)
    assert f is not None and f.code == "C13-silent-failure"


def test_detect_flags_error_colon_and_failed():
    assert detect_silent_failure(
        "a", InvokeResult("a", is_error=False, content="error: could not connect"), None
    )
    assert detect_silent_failure(
        "b", InvokeResult("b", is_error=False, content="the operation failed"), None
    )


def test_detect_flags_empty_when_output_schema_promises_content():
    result = InvokeResult("fetch", is_error=False, content=[], structured=None)
    f = detect_silent_failure("fetch", result, _PROMISING_SCHEMA)
    assert f is not None and f.code == "C13-silent-failure"
    assert "empty" in f.message


def test_detect_flags_empty_dict_structured_when_promised():
    result = InvokeResult("fetch", is_error=False, content=[], structured={})
    assert detect_silent_failure("fetch", result, _PROMISING_SCHEMA) is not None


# -- pure detector: low-false-positive cases ----------------------------------

def test_healthy_success_not_flagged():
    result = InvokeResult("ok", is_error=False, content="Sunny, 22C", structured={"temp": 22})
    assert detect_silent_failure("ok", result, None) is None


def test_declared_error_is_not_silent():
    # An honest is_error=True result is signalling, not a silent failure — even if error-shaped.
    result = InvokeResult("x", is_error=True, content="Traceback (most recent call last): boom")
    assert detect_silent_failure("x", result, None) is None


def test_prose_mentioning_error_word_not_flagged():
    # "error" without the ':' / exception shape must not trip (word-boundary, conservative).
    result = InvokeResult("x", is_error=False, content="No error occurred; everything is fine")
    assert detect_silent_failure("x", result, None) is None


def test_empty_result_without_output_schema_not_flagged():
    # Empty is only suspicious when a schema promised content.
    result = InvokeResult("x", is_error=False, content=[], structured=None)
    assert detect_silent_failure("x", result, None) is None


def test_empty_result_when_schema_promises_nothing_not_flagged():
    result = InvokeResult("x", is_error=False, content=[], structured=None)
    assert detect_silent_failure("x", result, {"type": "object"}) is None
    assert promises_content({"type": "object"}) is False


# -- engine wiring: live fire -------------------------------------------------

async def test_engine_flags_silent_failure_live():
    tools = [{"name": "run_job", "description": "run a job", "inputSchema": {"type": "object"}}]
    bad = InvokeResult("run_job", is_error=False, content="Traceback (most recent call last): kaboom")
    client = FakeClient(results={"run_job": bad})
    ctx = make_ctx(tools, client=client)
    fs = await ContractEngine().run(ctx)
    assert any(f.code == "C13-silent-failure" for f in fs.findings)
    assert fs.metrics["silent_failures"] == 1


async def test_engine_clean_tool_no_silent_finding():
    tools = [{"name": "greet", "description": "greet", "inputSchema": {"type": "object"}}]
    client = FakeClient(results={"greet": InvokeResult("greet", False, {"msg": "hi"})})
    fs = await ContractEngine().run(make_ctx(tools, client=client))
    assert not any(f.code == "C13-silent-failure" for f in fs.findings)
    assert fs.metrics["silent_failures"] == 0


# -- engine wiring: static = not measured (ADR-006) ---------------------------

async def test_silent_failure_not_measured_in_static_mode():
    tools = [{"name": "run_job", "description": "run a job", "inputSchema": {"type": "object"}}]
    ctx = make_ctx(tools, client=None, config=ProbeConfig(families=("contract",)))
    fs = await ContractEngine().run(ctx)
    # None = "not measured", never zeroed.
    assert fs.metrics["silent_failures"] is None
    assert not any(f.code == "C13-silent-failure" for f in fs.findings)
