"""Error-recovery affordance tests (issue #25) — grade the failure-path payload."""

from __future__ import annotations

from mcp_quality.config import ProbeConfig
from mcp_quality.connect.client import FakeClient, InvokeResult
from mcp_quality.contract.errors import grade_error_payload
from mcp_quality.engines.contract import ContractEngine

from .conftest import make_ctx

_TOOL = {"name": "lookup", "description": "look up a record",
         "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
         "annotations": {"readOnlyHint": True}}


def _err(text=None, structured=None):
    return InvokeResult("lookup", is_error=True, content=(text if text is not None else []),
                        structured=structured)


# -- the pure grader ----------------------------------------------------------

def test_actionable_error_scores_full():
    g = grade_error_payload("lookup", _err("Invalid value for 'id': expected a UUID string. Retryable: no."))
    assert g.affordance == 100 and g.findings == []


def test_opaque_error_flagged():
    g = grade_error_payload("lookup", _err("Something went wrong"))
    assert g.affordance <= 40
    assert any(f.code == "C11-error-opaque" for f in g.findings)


def test_leaked_stacktrace_is_high_severity():
    tb = 'Traceback (most recent call last):\n  File "/usr/lib/app/handler.py", line 42, in run\n    raise ValueError: bad id'
    g = grade_error_payload("lookup", _err(tb))
    leak = next((f for f in g.findings if f.code == "C11-error-leak"), None)
    assert leak is not None and leak.severity.name == "HIGH"
    assert g.affordance <= 30


def test_detail_but_no_guidance_is_low():
    g = grade_error_payload("lookup", _err("The identifier you passed does not correspond to anything in our system"))
    assert any(f.code == "C11-error-unactionable" for f in g.findings)
    assert 50 <= g.affordance < 100


def test_silent_accept_of_invalid_input():
    ok = InvokeResult("lookup", is_error=False, content={"result": "ok"})
    g = grade_error_payload("lookup", ok)
    assert any(f.code == "C11-silent-accept" for f in g.findings)


def test_structured_error_payload_read():
    g = grade_error_payload("lookup", _err(structured={"code": "NOT_FOUND", "message": "id not found; provide a valid id"}))
    assert g.affordance == 100  # 'not found' + 'provide' are actionable signals


# -- wired into the Contract engine -------------------------------------------

async def test_engine_surfaces_affordance_and_penalizes():
    # server returns an opaque error on bad input → C11 finding + affordance recorded
    client = FakeClient(results={"lookup": lambda args: (
        InvokeResult("lookup", is_error=False, content={"row": 1}) if isinstance(args.get("id"), str)
        else InvokeResult("lookup", is_error=True, content="error"))})
    fs = await ContractEngine().run(make_ctx([_TOOL], client=client, config=ProbeConfig()))
    assert fs.metrics["error_recovery_affordance"] is not None
    assert any(f.code.startswith("C11-error") for f in fs.findings)


async def test_engine_good_errors_no_penalty(monkeypatch):
    client = FakeClient(results={"lookup": lambda args: (
        InvokeResult("lookup", is_error=False, content={"row": 1}) if isinstance(args.get("id"), str)
        else InvokeResult("lookup", is_error=True,
                          content="Invalid value for 'id': expected a non-empty string; not retryable."))})
    fs = await ContractEngine().run(make_ctx([_TOOL], client=client, config=ProbeConfig()))
    assert fs.metrics["error_recovery_affordance"] == 100
    assert not any(f.code.startswith("C11-error") for f in fs.findings)
    assert fs.score == 100  # perfect affordance → no recovery penalty


async def test_error_recovery_not_measured_in_static():
    fs = await ContractEngine().run(make_ctx([_TOOL], client=None))
    assert fs.metrics["error_recovery_affordance"] is None
