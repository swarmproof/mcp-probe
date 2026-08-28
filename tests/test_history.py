"""History + score-delta tests (issue #9) — delta math, rubric guard, sticky markdown,
append/load, and the CLI `compare` + `run --record` surfaces."""

from __future__ import annotations

import json

from mcp_quality.cli import main
from mcp_quality.history import (
    COMMENT_MARKER,
    append_history,
    compute_delta,
    entry_from_report,
    load_history,
    render_delta_markdown,
)


def _report(overall, grade, fams, rubric="2026.07.1"):
    return {
        "rubric_version": rubric,
        "overall": {"score": overall, "grade": grade},
        "target": {"surface_hash": "sha256:abc"},
        "families": {n: {"score": s, "grade": "?"} for n, s in fams.items()},
    }


def test_compute_delta_math():
    base = _report(80, "B", {"cost": 90, "contract": 70})
    cur = _report(75, "C", {"cost": 85, "contract": 65})
    d = compute_delta(base, cur)
    assert d.overall_change == -5.0
    assert d.grade_dropped is True
    assert d.per_family["cost"] == (90, 85)
    assert d.has_regression is True


def test_no_regression_when_flat_or_up():
    base = _report(80, "B", {"cost": 80})
    cur = _report(82, "B", {"cost": 82})
    d = compute_delta(base, cur)
    assert d.has_regression is False


def test_rubric_mismatch_refuses_family_diff():
    base = _report(80, "B", {"cost": 80}, rubric="1999.01.0")
    cur = _report(20, "F", {"cost": 20}, rubric="2026.07.1")
    d = compute_delta(base, cur)
    assert d.rubric_mismatch is True
    assert d.per_family == {}


def test_markdown_has_marker_and_table():
    base = _report(80, "B", {"cost": 90})
    cur = _report(70, "C", {"cost": 70})
    md = render_delta_markdown(compute_delta(base, cur))
    assert md.startswith(COMMENT_MARKER)
    assert "regression" in md
    assert "| Family | Base | PR | Δ |" in md


def test_history_roundtrip(tmp_path):
    path = tmp_path / "history.jsonl"
    entry = entry_from_report(_report(90, "A", {"cost": 90}), commit="abc123", ts="2026-01-01T00:00:00Z")
    append_history(path, entry)
    append_history(path, entry_from_report(_report(85, "B", {"cost": 85}), commit="def456"))
    hist = load_history(path)
    assert len(hist) == 2
    assert hist[0]["commit"] == "abc123"
    assert hist[0]["overall_grade"] == "A"


def test_cli_compare_markdown(tmp_path, capsys):
    base = tmp_path / "base.json"
    cur = tmp_path / "cur.json"
    base.write_text(json.dumps(_report(80, "B", {"cost": 90})), encoding="utf-8")
    cur.write_text(json.dumps(_report(70, "C", {"cost": 70})), encoding="utf-8")
    rc = main(["compare", str(base), str(cur), "--markdown"])
    assert rc == 0
    assert COMMENT_MARKER in capsys.readouterr().out


def test_cli_compare_fail_on_regression(tmp_path):
    base = tmp_path / "base.json"
    cur = tmp_path / "cur.json"
    base.write_text(json.dumps(_report(80, "B", {"cost": 90})), encoding="utf-8")
    cur.write_text(json.dumps(_report(60, "D", {"cost": 60})), encoding="utf-8")
    assert main(["compare", str(base), str(cur), "--fail-on-regression"]) == 1
    # and passes (exit 0) when improved
    cur.write_text(json.dumps(_report(95, "A", {"cost": 95})), encoding="utf-8")
    assert main(["compare", str(base), str(cur), "--fail-on-regression"]) == 0
