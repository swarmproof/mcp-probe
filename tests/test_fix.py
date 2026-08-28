"""Legibility auto-fix tests (REQ-L7, issue #8) — collect + apply rewrites, incl. the
name-anchoring that resolves identical descriptions, and an e2e through the CLI."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from mcp_quality.cli import main
from mcp_quality.fix import Rewrite, apply_rewrites, collect_rewrites

SERVERS = Path(__file__).parent / "servers"


def _report_with_rewrites(entries: list[dict]) -> dict:
    return {
        "families": {
            "legibility": {
                "findings": [
                    {"code": "L5-rewrite", "tool": e["tool"],
                     "evidence": {"old": e["old"], "rewrite": e["new"]}}
                    for e in entries
                ]
            }
        }
    }


def test_collect_rewrites_pulls_old_and_new():
    report = _report_with_rewrites([{"tool": "t", "old": "Old.", "new": "New, clearer."}])
    rws = collect_rewrites(report)
    assert rws == [Rewrite(tool="t", old="Old.", new="New, clearer.")]


def test_collect_rewrites_respects_accept_filter():
    report = _report_with_rewrites([
        {"tool": "a", "old": "A", "new": "AA"},
        {"tool": "b", "old": "B", "new": "BB"},
    ])
    assert [r.tool for r in collect_rewrites(report, only={"b"})] == ["b"]


def test_apply_exact_single_match():
    src = 'description="Old text here."\n'
    out, res = apply_rewrites(src, [Rewrite("t", "Old text here.", "New text.")])
    assert "New text." in out and "Old text here." not in out
    assert res.applied and not res.skipped


def test_apply_skips_when_not_found():
    _out, res = apply_rewrites("nothing matches", [Rewrite("t", "absent", "x")])
    assert not res.applied
    assert "not found" in res.skipped[0][1]


def test_apply_name_anchors_identical_descriptions():
    # Both tools share the same description string — the confusable case. Anchoring by the
    # tool name must send each rewrite to the right occurrence.
    src = (
        'def delete_record():\n    description="Remove a record by id."\n\n'
        'def archive_record():\n    description="Remove a record by id."\n'
    )
    rws = [
        Rewrite("delete_record", "Remove a record by id.", "Permanently delete a record by id."),
        Rewrite("archive_record", "Remove a record by id.", "Move a record to the archive."),
    ]
    out, res = apply_rewrites(src, rws)
    assert len(res.applied) == 2
    # each rewrite landed next to its own function
    assert "def delete_record():\n    description=\"Permanently delete a record by id.\"" in out
    assert "def archive_record():\n    description=\"Move a record to the archive.\"" in out


def test_cli_fix_apply_changes_confusable_server(tmp_path):
    # e2e: apply real rewrites to a copy of the confusable fixture via the CLI.
    src = tmp_path / "confusable_server.py"
    shutil.copy(SERVERS / "confusable_server.py", src)
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_report_with_rewrites([
        {"tool": "delete_record", "old": "Remove a record by id.",
         "new": "Permanently delete a record by id (cannot be undone)."},
        {"tool": "archive_record", "old": "Remove a record by id.",
         "new": "Move a record to the archive; reversible."},
    ])), encoding="utf-8")

    rc = main(["fix", "--from", str(report), "--source", str(src), "--apply"])
    assert rc == 0
    text = src.read_text(encoding="utf-8")
    assert "Permanently delete a record by id" in text
    assert "Move a record to the archive" in text
    assert "Remove a record by id." not in text  # both originals rewritten


def test_cli_fix_dry_run_does_not_write(tmp_path):
    src = tmp_path / "s.py"
    src.write_text('description="Remove a record by id."\n', encoding="utf-8")
    report = tmp_path / "r.json"
    report.write_text(json.dumps(_report_with_rewrites([
        {"tool": "delete_record", "old": "Remove a record by id.", "new": "Delete it."},
    ])), encoding="utf-8")
    before = src.read_text(encoding="utf-8")
    rc = main(["fix", "--from", str(report), "--source", str(src)])  # no --apply
    assert rc == 0
    assert src.read_text(encoding="utf-8") == before  # unchanged
