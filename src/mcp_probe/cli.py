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

from mcp_probe import __version__
from mcp_probe.config import ALL_FAMILIES, FAST_PATH_FAMILIES, ProbeConfig, load_config
from mcp_probe.exit_codes import ExitCode


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mcp-probe",
        description="The CI quality suite for MCP servers — lint, contract-test, benchmark, load-test.",
    )
    p.add_argument("--version", action="version", version=f"mcp-probe {__version__}")
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
    return p


def _add_common_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--json", dest="json_out", action="store_true", help="emit the CI JSON report")
    sp.add_argument("--fail-under", metavar="GRADE", help="exit 1 if overall grade < GRADE (A–F)")
    sp.add_argument("--no-regressions", action="store_true", help="exit 1 on any regression vs snapshot")
    sp.add_argument("--allow-writes", action="store_true", help="permit invoking destructive tools")
    sp.add_argument("--html", dest="html_out", metavar="PATH", help="write an HTML report")
    sp.add_argument("--emit-stampede", metavar="PATH", help="write the stampede --from-probe seed")
    sp.add_argument("--snapshot-path", default=None)
    sp.add_argument("--stdio-timeout", type=float, default=None)
    sp.add_argument("--transport", choices=["auto", "stdio", "streamable-http", "sse"], default=None)


def _add_family_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--all", dest="all_families", action="store_true", help="run all five families")
    sp.add_argument("--legibility", action="store_true", help="add the Legibility (LLM) family")
    sp.add_argument("--performance", action="store_true", help="add the Performance (load) family")
    sp.add_argument("--security", action="store_true", help="add the Security-lite family")
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
    # de-dup, keep canonical order
    return tuple(f for f in ALL_FAMILIES if f in set(families))


def _config_from_args(args: argparse.Namespace) -> ProbeConfig:
    overrides: dict[str, Any] = {
        "fail_under": getattr(args, "fail_under", None),
        "no_regressions": _true_or_none(getattr(args, "no_regressions", False)),
        "allow_writes": _true_or_none(getattr(args, "allow_writes", False)),
        "json_out": _true_or_none(getattr(args, "json_out", False)),
        "html_out": getattr(args, "html_out", None),
        "emit_stampede": getattr(args, "emit_stampede", None),
        "snapshot_path": getattr(args, "snapshot_path", None),
        "stdio_timeout": getattr(args, "stdio_timeout", None),
        "transport": getattr(args, "transport", None),
        "deep_security": _true_or_none(getattr(args, "deep_security", False)),
        "model": getattr(args, "model", None),
        "token_model": getattr(args, "token_model", None),
        "seed": getattr(args, "seed", None),
        "concurrency": getattr(args, "concurrency", None),
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "badge":
        return _cmd_badge(args)
    if args.command == "snapshot":
        return _cmd_snapshot(args)
    return _cmd_run(args)


def _cmd_run(args: argparse.Namespace) -> int:
    from mcp_probe.pipeline import run_probe
    from mcp_probe.report import report_to_json
    from mcp_probe.report.render import render_html, render_terminal

    config = _config_from_args(args)
    try:
        outcome = asyncio.run(run_probe(config))
    except FileNotFoundError as exc:
        print(f"mcp-probe: {exc}", file=sys.stderr)
        return int(ExitCode.PROBE_ERROR)
    except Exception as exc:  # unreachable / non-conformant target
        print(f"mcp-probe: probe error: {exc}", file=sys.stderr)
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

    return int(outcome.exit_code)


def _cmd_snapshot(args: argparse.Namespace) -> int:
    from mcp_probe.pipeline import run_probe
    from mcp_probe.snapshot import build_snapshot, load_snapshot, write_snapshot

    overrides = {"target": args.target, "snapshot_path": getattr(args, "snapshot_path", None)}
    config = load_config(cli_overrides={k: v for k, v in overrides.items() if v is not None})
    path = config.snapshot_path
    if load_snapshot(path) is not None and not args.update:
        print(f"mcp-probe: snapshot exists at {path}; pass --update to overwrite", file=sys.stderr)
        return int(ExitCode.GATE_FAILURE)
    try:
        outcome = asyncio.run(run_probe(config))
    except Exception as exc:
        print(f"mcp-probe: probe error: {exc}", file=sys.stderr)
        return int(ExitCode.PROBE_ERROR)
    snap = build_snapshot(outcome.report.surface, outcome.report.families)
    write_snapshot(path, snap)
    print(f"mcp-probe: wrote snapshot → {path} ({len(outcome.report.surface.tools)} tools)")
    return int(ExitCode.OK)


def _cmd_badge(args: argparse.Namespace) -> int:
    import json

    from mcp_probe.report.badge import badge_svg, shields_endpoint

    grade, score, rubric = "not-measured", None, ""
    if args.from_report:
        doc = json.loads(Path(args.from_report).read_text(encoding="utf-8"))
        grade = doc.get("overall", {}).get("grade", "not-measured")
        score = doc.get("overall", {}).get("score")
        rubric = doc.get("rubric_version", "")
    elif args.target:
        from mcp_probe.pipeline import run_probe

        config = load_config(cli_overrides={"target": args.target})
        outcome = asyncio.run(run_probe(config))
        grade = outcome.report.overall_grade
        score = outcome.report.overall_score
        rubric = outcome.report.rubric_version
    else:
        print("mcp-probe: badge needs a target or --from report.json", file=sys.stderr)
        return int(ExitCode.PROBE_ERROR)

    svg = badge_svg(grade, rubric_version=rubric, score=score if args.with_score else None)
    Path(args.out).write_text(svg, encoding="utf-8")
    print(f"mcp-probe: wrote badge → {args.out} (grade {grade})")
    if args.endpoint_out:
        Path(args.endpoint_out).write_text(
            json.dumps(shields_endpoint(grade)) + "\n", encoding="utf-8"
        )
    return int(ExitCode.OK)


def _write_stampede_seed(report: Any, path: str) -> None:
    """Emit the stampede handoff seed (ARCHITECTURE §9). Full contract in handoff.py."""
    from mcp_probe.handoff import build_stampede_seed

    Path(path).write_text(build_stampede_seed(report), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
