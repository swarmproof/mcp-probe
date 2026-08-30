"""Command-line interface — ``run`` / ``static`` / ``snapshot`` / ``badge`` (WBS 0.1).

The CLI is a thin shell: parse flags → build config → drive the pipeline → render →
exit with the CI-contract code. All the logic lives in the library so the same behaviour
is reachable programmatically (registries, tests). Only explicitly-set flags are passed
as overrides, preserving the flags > file > env > default precedence (config.py).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from mcp_quality import __version__
from mcp_quality.config import ALL_FAMILIES, FAST_PATH_FAMILIES, ProbeConfig, load_config
from mcp_quality.exit_codes import ExitCode


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mcp-quality",
        description="The CI quality suite for MCP servers — lint, contract-test, benchmark, load-test.",
    )
    p.add_argument("--version", action="version", version=f"mcp-quality {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    # -- run --
    run = sub.add_parser("run", help="probe a live MCP server and grade it")
    run.add_argument("target", help="stdio command (e.g. 'python my_server.py') or an HTTP URL")
    _add_common_flags(run)
    _add_family_flags(run)

    # -- static --
    st = sub.add_parser("static", help="grade a tools/list JSON dump offline (air-gapped CI)")
    st.add_argument("dump", help="path to a tools/list JSON dump")
    _add_common_flags(st)
    _add_family_flags(st)

    # -- snapshot --
    snap = sub.add_parser("snapshot", help="write/update the regression baseline")
    snap.add_argument("target", help="stdio command or HTTP URL")
    snap.add_argument("--update", action="store_true", help="overwrite the existing baseline")
    snap.add_argument("--snapshot-path", default=None)

    # -- badge --
    badge = sub.add_parser("badge", help="emit a grade badge (SVG + shields endpoint)")
    badge.add_argument("target", nargs="?", help="stdio command / URL to probe, if no --from")
    badge.add_argument("--from", dest="from_report", help="derive the badge from a saved report JSON")
    badge.add_argument("--out", default="badge.svg", help="SVG output path")
    badge.add_argument("--endpoint-out", default=None, help="write the shields JSON endpoint too")
    badge.add_argument("--with-score", action="store_true", help="render 'A · 92' instead of 'A'")

    # -- fix --
    fix = sub.add_parser("fix", help="apply proposed legibility description rewrites (REQ-L7)")
    fix.add_argument("target", nargs="?", help="stdio command / URL to probe, if no --from")
    fix.add_argument("--source", required=True, help="source file whose tool descriptions to rewrite")
    fix.add_argument("--from", dest="from_report", help="use rewrites from a saved report JSON")
    fix.add_argument("--model", default=None, help="legibility model for a fresh probe")
    fix.add_argument("--accept", default=None, help="comma-separated tool names to fix (default: all)")
    fix.add_argument("--apply", action="store_true", help="write changes (default: dry-run diff)")
    fix.add_argument("--pr", action="store_true", help="apply, commit on a branch, and open a PR via gh")
    fix.add_argument("--allow-writes", action="store_true", help=argparse.SUPPRESS)

    # -- compare --
    cmp_ = sub.add_parser("compare", help="diff two report JSONs into a score-delta table")
    cmp_.add_argument("baseline", help="baseline report JSON (or a history entry)")
    cmp_.add_argument("current", help="current report JSON")
    cmp_.add_argument("--markdown", action="store_true", help="emit the sticky PR-comment markdown")
    cmp_.add_argument("--fail-on-regression", action="store_true", help="exit 1 if any family regressed")

    # -- serve --
    serve = sub.add_parser("serve", help="run the registry scoring API (needs the [registry] extra)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    return p


def _add_common_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--json", dest="json_out", action="store_true", help="emit the CI JSON report")
    sp.add_argument("--fail-under", metavar="GRADE", help="exit 1 if overall grade < GRADE (A–F)")
    sp.add_argument("--fail-under-family", metavar="F:G,...", default=None,
                    help="per-family gates, e.g. 'Contract:A,Security:B'")
    sp.add_argument("--no-regressions", action="store_true", help="exit 1 on any regression vs snapshot")
    sp.add_argument("--header", dest="headers", action="append", metavar="'K: V'", default=None,
                    help="HTTP/SSE header (repeatable), e.g. --header 'Authorization: Bearer …'")
    sp.add_argument("--allow-writes", action="store_true", help="permit invoking destructive tools")
    sp.add_argument("--html", dest="html_out", metavar="PATH", help="write an HTML report")
    sp.add_argument("--emit-stampede", metavar="PATH", help="write the stampede --from-probe seed")
    sp.add_argument("--snapshot-path", default=None)
    sp.add_argument("--stdio-timeout", type=float, default=None)
    sp.add_argument("--transport", choices=["auto", "stdio", "streamable-http", "sse"], default=None)
    sp.add_argument("--record", metavar="PATH", default=None, help="append this run to a history JSONL")
    sp.add_argument("--commit", default=None, help="commit SHA for the history entry (or $GITHUB_SHA)")


def _add_family_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--all", dest="all_families", action="store_true", help="run all check families")
    sp.add_argument("--legibility", action="store_true", help="add the Legibility (LLM) family")
    sp.add_argument("--performance", action="store_true", help="add the Performance (load) family")
    sp.add_argument("--security", action="store_true", help="add the Security-lite family")
    sp.add_argument("--safety", action="store_true", help="add the Safety-Contract family")
    sp.add_argument("--experimental", action="store_true",
                    help="add experimental spec-surface checks (sampling/resources/elicitation)")
    sp.add_argument("--deep-security", action="store_true", help="shell out to mcp-scan / Cisco")
    sp.add_argument("--model", default=None, help="legibility model, e.g. 'ollama:qwen2.5-3b'")
    sp.add_argument(
        "--token-model",
        default=None,
        help="authoritative token count via a provider, e.g. 'anthropic:claude-sonnet-5' "
        "(needs ANTHROPIC_API_KEY; falls back to the offline estimate)",
    )
    sp.add_argument("--seed", type=int, default=None)
    sp.add_argument("--concurrency", type=int, default=None)
    sp.add_argument("--reliability", dest="reliability_k", type=int, default=None, metavar="K",
                    help="rerun nondeterministic families K times, report pass^k consistency")
    sp.add_argument("--response-bloat", action="store_true",
                    help="sample read-only tool outputs to measure response token weight (REQ-$5)")


def _families_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    if getattr(args, "all_families", False):
        return ALL_FAMILIES
    families = list(FAST_PATH_FAMILIES)
    if getattr(args, "legibility", False):
        families.append("legibility")
    if getattr(args, "performance", False):
        families.append("performance")
    if getattr(args, "security", False) or getattr(args, "deep_security", False):
        families.append("security")
    if getattr(args, "safety", False):
        families.append("safety")
    # de-dup, keep canonical order; experimental families append after the scored set.
    ordered = [f for f in ALL_FAMILIES if f in set(families)]
    if getattr(args, "experimental", False):
        ordered.append("spec")
    return tuple(ordered)


def _config_from_args(args: argparse.Namespace) -> ProbeConfig:
    overrides: dict[str, Any] = {
        "fail_under": getattr(args, "fail_under", None),
        "fail_under_family": _parse_family_gates(getattr(args, "fail_under_family", None)),
        "headers": _parse_headers(getattr(args, "headers", None)),
        "no_regressions": _true_or_none(getattr(args, "no_regressions", False)),
        "allow_writes": _true_or_none(getattr(args, "allow_writes", False)),
        "json_out": _true_or_none(getattr(args, "json_out", False)),
        "html_out": getattr(args, "html_out", None),
        "emit_stampede": getattr(args, "emit_stampede", None),
        "snapshot_path": getattr(args, "snapshot_path", None),
        "stdio_timeout": getattr(args, "stdio_timeout", None),
        "transport": getattr(args, "transport", None),
        "deep_security": _true_or_none(getattr(args, "deep_security", False)),
        "experimental": _true_or_none(getattr(args, "experimental", False)),
        "model": getattr(args, "model", None),
        "token_model": getattr(args, "token_model", None),
        "response_bloat": _true_or_none(getattr(args, "response_bloat", False)),
        "seed": getattr(args, "seed", None),
        "concurrency": getattr(args, "concurrency", None),
        "reliability_k": getattr(args, "reliability_k", None),
        "families": _families_from_args(args) if hasattr(args, "all_families") else None,
    }
    if args.command == "run":
        overrides["target"] = args.target
    elif args.command == "static":
        overrides["static_path"] = args.dump
    return load_config(cli_overrides=overrides)


def _true_or_none(flag: bool) -> bool | None:
    """Store-true flags default False; treat False as 'unset' so config/env can win."""
    return True if flag else None


def _parse_headers(raw: list[str] | None) -> dict[str, str] | None:
    """Parse repeated ``--header 'K: V'`` into a dict (None if unset → don't override)."""
    if not raw:
        return None
    out: dict[str, str] = {}
    for item in raw:
        key, sep, value = item.partition(":")
        if sep:
            out[key.strip()] = value.strip()
    return out or None


def _parse_family_gates(raw: str | None) -> dict[str, str] | None:
    """Parse ``Contract:A,Security:B`` into {family: grade} (lowercased family keys)."""
    if not raw:
        return None
    out: dict[str, str] = {}
    for pair in raw.split(","):
        fam, sep, grade = pair.partition(":")
        if sep:
            out[fam.strip().lower()] = grade.strip().upper()
    return out or None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "badge":
        return _cmd_badge(args)
    if args.command == "snapshot":
        return _cmd_snapshot(args)
    if args.command == "fix":
        return _cmd_fix(args)
    if args.command == "compare":
        return _cmd_compare(args)
    if args.command == "serve":
        return _cmd_serve(args)
    return _cmd_run(args)


def _cmd_serve(args: argparse.Namespace) -> int:
    try:
        from mcp_quality.registry import serve
    except ImportError:
        print("mcp-quality: the registry API needs the [registry] extra: "
              "pip install 'mcp-quality[registry]'", file=sys.stderr)
        return int(ExitCode.PROBE_ERROR)
    print(f"mcp-quality: registry scoring API on http://{args.host}:{args.port}", file=sys.stderr)
    serve(host=args.host, port=args.port)
    return int(ExitCode.OK)


def _cmd_run(args: argparse.Namespace) -> int:
    from mcp_quality.pipeline import run_probe
    from mcp_quality.report import report_to_json
    from mcp_quality.report.render import render_html, render_terminal

    config = _config_from_args(args)
    try:
        outcome = asyncio.run(run_probe(config))
    except FileNotFoundError as exc:
        print(f"mcp-quality: {exc}", file=sys.stderr)
        return int(ExitCode.PROBE_ERROR)
    except Exception as exc:  # unreachable / non-conformant target
        print(f"mcp-quality: probe error: {exc}", file=sys.stderr)
        return int(ExitCode.PROBE_ERROR)

    report = outcome.report
    if config.json_out:
        print(report_to_json(report))
    else:
        print(render_terminal(report))

    if config.html_out:
        Path(config.html_out).write_text(render_html(report), encoding="utf-8")
    if config.emit_stampede:
        _write_stampede_seed(report, config.emit_stampede)
    if getattr(args, "record", None):
        _record_history(args, report)

    return int(outcome.exit_code)


def _record_history(args: argparse.Namespace, report: Any) -> None:
    import datetime
    import os

    from mcp_quality.history import append_history, entry_from_report
    from mcp_quality.report import report_to_dict

    commit = args.commit or os.environ.get("GITHUB_SHA", "")
    ts = datetime.datetime.now(datetime.UTC).isoformat()
    entry = entry_from_report(report_to_dict(report, include_meta=False), commit=commit, ts=ts)
    append_history(args.record, entry)


def _cmd_compare(args: argparse.Namespace) -> int:
    import json

    from mcp_quality.history import compute_delta, render_delta_markdown

    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    current = json.loads(Path(args.current).read_text(encoding="utf-8"))
    delta = compute_delta(baseline, current)

    if args.markdown:
        print(render_delta_markdown(delta), end="")
    else:
        oc = delta.overall_change
        oc_str = "→0" if oc == 0 else (f"{oc:+.0f}" if oc is not None else "n/a")
        print(f"overall: {delta.grade_before} → {delta.grade_after} ({oc_str})")
        if delta.rubric_mismatch:
            print("  rubric changed — per-family comparison skipped")
        for name, (b, a) in delta.per_family.items():
            bs = "—" if b is None else f"{b:.0f}"
            as_ = "—" if a is None else f"{a:.0f}"
            print(f"  {name:12} {bs:>4} → {as_:>4}")

    if args.fail_on_regression and delta.has_regression:
        return int(ExitCode.GATE_FAILURE)
    return int(ExitCode.OK)


def _cmd_snapshot(args: argparse.Namespace) -> int:
    from mcp_quality.pipeline import run_probe
    from mcp_quality.snapshot import build_snapshot, load_snapshot, write_snapshot

    overrides = {"target": args.target, "snapshot_path": getattr(args, "snapshot_path", None)}
    config = load_config(cli_overrides={k: v for k, v in overrides.items() if v is not None})
    path = config.snapshot_path
    if load_snapshot(path) is not None and not args.update:
        print(f"mcp-quality: snapshot exists at {path}; pass --update to overwrite", file=sys.stderr)
        return int(ExitCode.GATE_FAILURE)
    try:
        outcome = asyncio.run(run_probe(config))
    except Exception as exc:
        print(f"mcp-quality: probe error: {exc}", file=sys.stderr)
        return int(ExitCode.PROBE_ERROR)
    snap = build_snapshot(outcome.report.surface, outcome.report.families)
    write_snapshot(path, snap)
    print(f"mcp-quality: wrote snapshot → {path} ({len(outcome.report.surface.tools)} tools)")
    return int(ExitCode.OK)


def _cmd_badge(args: argparse.Namespace) -> int:
    import json

    from mcp_quality.report.badge import badge_svg, shields_endpoint

    grade, score, rubric = "not-measured", None, ""
    if args.from_report:
        doc = json.loads(Path(args.from_report).read_text(encoding="utf-8"))
        grade = doc.get("overall", {}).get("grade", "not-measured")
        score = doc.get("overall", {}).get("score")
        rubric = doc.get("rubric_version", "")
    elif args.target:
        from mcp_quality.pipeline import run_probe

        config = load_config(cli_overrides={"target": args.target})
        outcome = asyncio.run(run_probe(config))
        grade = outcome.report.overall_grade
        score = outcome.report.overall_score
        rubric = outcome.report.rubric_version
    else:
        print("mcp-quality: badge needs a target or --from report.json", file=sys.stderr)
        return int(ExitCode.PROBE_ERROR)

    svg = badge_svg(grade, rubric_version=rubric, score=score if args.with_score else None)
    Path(args.out).write_text(svg, encoding="utf-8")
    print(f"mcp-quality: wrote badge → {args.out} (grade {grade})")
    if args.endpoint_out:
        Path(args.endpoint_out).write_text(
            json.dumps(shields_endpoint(grade)) + "\n", encoding="utf-8"
        )
    return int(ExitCode.OK)


def _cmd_fix(args: argparse.Namespace) -> int:
    import json

    from mcp_quality.fix import apply_to_file, collect_rewrites

    only = set(args.accept.split(",")) if args.accept else None

    # Source of rewrites: a saved report JSON, or a fresh legibility probe of the target.
    if args.from_report:
        report = json.loads(Path(args.from_report).read_text(encoding="utf-8"))
    elif args.target:
        from mcp_quality.pipeline import run_probe
        from mcp_quality.report import report_to_dict

        overrides = {
            "target": args.target,
            "families": ("contract", "cost", "legibility"),
            "model": args.model,
        }
        config = load_config(cli_overrides={k: v for k, v in overrides.items() if v is not None})
        try:
            outcome = asyncio.run(run_probe(config))
        except Exception as exc:
            print(f"mcp-quality: probe error: {exc}", file=sys.stderr)
            return int(ExitCode.PROBE_ERROR)
        report = report_to_dict(outcome.report)
    else:
        print("mcp-quality: fix needs a target or --from report.json", file=sys.stderr)
        return int(ExitCode.PROBE_ERROR)

    rewrites = collect_rewrites(report, only=only)
    if not rewrites:
        print("mcp-quality: no applicable legibility rewrites found "
              "(run with --legibility and a model, or check --accept)", file=sys.stderr)
        return int(ExitCode.OK)

    write = args.apply or args.pr
    result = apply_to_file(args.source, rewrites, write=write)

    for rw in result.applied:
        print(f"  ✓ {rw.tool}: description rewritten")
    for rw, reason in result.skipped:
        print(f"  – {rw.tool}: skipped ({reason})", file=sys.stderr)
    if result.diff and not write:
        print("\n" + result.diff, end="")
        print("(dry-run — pass --apply to write, or --pr to open a pull request)")

    if not result.changed:
        return int(ExitCode.OK)
    if args.pr:
        return _open_fix_pr(args.source, result)
    if write:
        print(f"\nmcp-quality: applied {len(result.applied)} rewrite(s) to {args.source}")
    return int(ExitCode.OK)


def _open_fix_pr(source: str, result: Any) -> int:
    """Apply → branch → commit → PR via git + gh. Degrades to 'applied locally' on failure."""
    import subprocess

    branch = "mcp-quality/legibility-rewrites"
    body = "Applies mcp-quality legibility description rewrites (REQ-L7):\n\n" + "\n".join(
        f"- `{rw.tool}`" for rw in result.applied
    )
    steps = [
        ["git", "checkout", "-b", branch],
        ["git", "add", source],
        ["git", "commit", "-m", "fix: apply mcp-quality legibility description rewrites"],
        ["git", "push", "-u", "origin", branch],
        ["gh", "pr", "create", "--title", "Apply mcp-quality legibility rewrites", "--body", body],
    ]
    try:
        for step in steps:
            subprocess.run(step, check=True, capture_output=True, text=True)  # noqa: S603
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"mcp-quality: changes applied locally; couldn't open PR automatically ({exc})",
              file=sys.stderr)
        return int(ExitCode.OK)
    print(f"mcp-quality: opened PR from branch {branch}")
    return int(ExitCode.OK)


def _write_stampede_seed(report: Any, path: str) -> None:
    """Emit the stampede handoff seed (ARCHITECTURE §9). Full contract in handoff.py."""
    from mcp_quality.handoff import build_stampede_seed

    Path(path).write_text(build_stampede_seed(report), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
