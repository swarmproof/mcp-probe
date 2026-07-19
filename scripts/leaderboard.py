#!/usr/bin/env python
"""Score a set of public MCP servers and emit a ranked leaderboard (launch content).

This is a *use* of v0.1, not new engine code: it drives ``run_probe`` over a curated list
of credential-free public reference servers (run via npx/uvx), then writes a ranked
Markdown table + JSON. Servers that need API keys are listed but not scored (honest — we
don't fake a grade we couldn't measure). Failures (download timeout, non-conformant) are
recorded, never crash the batch.

Usage:
    python scripts/leaderboard.py                 # fast path + security-lite (keyless)
    python scripts/leaderboard.py --legibility    # add legibility via local Ollama
    python scripts/leaderboard.py --only everything,memory   # subset
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mcp_probe import RUBRIC_VERSION, __version__  # noqa: E402
from mcp_probe.config import ProbeConfig  # noqa: E402
from mcp_probe.pipeline import run_probe  # noqa: E402


@dataclass
class ServerSpec:
    key: str
    label: str
    command: str
    note: str = ""


# Credential-free public reference servers (github.com/modelcontextprotocol/servers + PyPI).
SERVERS: list[ServerSpec] = [
    ServerSpec("everything", "server-everything", "npx -y @modelcontextprotocol/server-everything"),
    ServerSpec("memory", "server-memory", "npx -y @modelcontextprotocol/server-memory"),
    ServerSpec("sequentialthinking", "server-sequential-thinking",
               "npx -y @modelcontextprotocol/server-sequential-thinking"),
    ServerSpec("filesystem", "server-filesystem", "npx -y @modelcontextprotocol/server-filesystem /tmp"),
    ServerSpec("time", "mcp-server-time", "uvx mcp-server-time"),
    ServerSpec("fetch", "mcp-server-fetch", "uvx mcp-server-fetch"),
    ServerSpec("git", "mcp-server-git", "uvx mcp-server-git"),
]

# Popular servers that gate on credentials — listed for context, not scored (honest).
CREDENTIAL_GATED = ["server-github", "server-slack", "server-brave-search", "server-google-maps", "server-postgres"]


@dataclass
class Row:
    spec: ServerSpec
    grade: str = "—"
    score: float | None = None
    tools: int = 0
    toolset_tokens: int | None = None
    top_confusion: list | None = None
    hard_gate: str | None = None
    error: str = ""
    elapsed_s: float = 0.0
    families: dict = field(default_factory=dict)


async def probe_one(spec: ServerSpec, *, families: tuple[str, ...], model: str | None) -> Row:
    row = Row(spec=spec)
    start = time.monotonic()
    cfg = ProbeConfig(
        target=spec.command,
        transport="stdio",
        families=families,
        model=model,
        stdio_timeout=150.0,  # npx/uvx first-run downloads can be slow
        concurrency=8,
    )
    try:
        outcome = await asyncio.wait_for(run_probe(cfg), timeout=240)
        r = outcome.report
        row.grade = r.overall_grade
        row.score = r.overall_score
        row.hard_gate = r.hard_gate
        cost = r.families.get("cost")
        if cost:
            row.toolset_tokens = cost.metrics.get("toolset_tokens")
        row.tools = len(r.surface.tools)
        leg = r.families.get("legibility")
        if leg:
            row.top_confusion = leg.metrics.get("top_confusion")
        row.families = {n: (f.grade if f.measured else "n/m") for n, f in r.families.items()}
    except TimeoutError:
        row.error = "timeout"
    except Exception as exc:  # unreachable / non-conformant / download failure
        row.error = f"{type(exc).__name__}: {exc}"[:120]
    row.elapsed_s = round(time.monotonic() - start, 1)
    return row


def _score_key(row: Row) -> float:
    return row.score if row.score is not None else -1.0


def render_markdown(rows: list[Row], model: str | None) -> str:
    ranked = sorted(rows, key=_score_key, reverse=True)
    lines = [
        "# MCP Quality Leaderboard",
        "",
        f"> Scored with **mcp-probe {__version__}** (rubric `{RUBRIC_VERSION}`). "
        "Fast path (Contract + Cost) + Security-lite"
        + (", Legibility via local Ollama" if model else "")
        + ". Keyless, offline-deterministic. Servers requiring API keys are listed but not scored.",
        "",
        "| # | Server | Grade | Score | Tools | Toolset tokens | Top confusion | Notes |",
        "|---|--------|-------|-------|-------|----------------|---------------|-------|",
    ]
    for i, row in enumerate(ranked, 1):
        if row.error:
            lines.append(
                f"| — | `{row.spec.label}` | — | — | — | — | — | ⚠ {row.error} ({row.elapsed_s}s) |"
            )
            continue
        tok = f"{row.toolset_tokens:,}" if row.toolset_tokens is not None else "—"
        conf = "—"
        if row.top_confusion:
            a, b, r = row.top_confusion
            conf = f"`{a}`⇄`{b}` {r:.0%}"
        note = f"hard-gate: {row.hard_gate}" if row.hard_gate else ""
        lines.append(
            f"| {i} | `{row.spec.label}` | **{row.grade}** | {row.score:.0f} | {row.tools} "
            f"| {tok} | {conf} | {note} |"
        )
    lines += [
        "",
        "### Not scored (require credentials)",
        ", ".join(f"`{s}`" for s in CREDENTIAL_GATED),
        "",
        "### Reading the grades",
        "- A **contract hard-gate** usually means the determinism probe (REQ-C5) called a "
        "tool twice with identical args and got different results. For a *stateful* tool "
        "(e.g. sequential-thinking accumulates state) that's by-design — the fix is to "
        "declare the output volatile, not to change behaviour. mcp-probe flags undeclared "
        "nondeterminism; whether it's a defect is the author's call.",
        "- **Toolset tokens** is the context tax every agent pays each turn just to see the "
        "tools — the single most actionable number here.",
        "",
        "_Reproduce: `python scripts/leaderboard.py`. Grades reflect the servers' published "
        "tool surface at scan time; a lower grade is an invitation to a PR, not a verdict._",
    ]
    return "\n".join(lines) + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legibility", action="store_true", help="add legibility via Ollama")
    parser.add_argument("--model", default="ollama:mistral-small:latest")
    parser.add_argument("--only", default="", help="comma-separated server keys to run")
    parser.add_argument("--out", default="docs/leaderboard.md")
    args = parser.parse_args()

    families = ("contract", "cost", "security")
    model = None
    if args.legibility:
        families = ("contract", "cost", "security", "legibility")
        model = args.model

    specs = SERVERS
    if args.only:
        wanted = set(args.only.split(","))
        specs = [s for s in SERVERS if s.key in wanted]

    rows: list[Row] = []
    for spec in specs:  # sequential: parallel npx downloads thrash disk/network
        print(f"probing {spec.label} …", file=sys.stderr)
        row = await probe_one(spec, families=families, model=model)
        if row.error:
            status = row.error
        elif row.score is not None:
            status = f"{row.grade} ({row.score:.0f})"
        else:
            status = "?"
        print(f"  → {status}  [{row.elapsed_s}s]", file=sys.stderr)
        rows.append(row)

    md = render_markdown(rows, model)
    Path(args.out).write_text(md, encoding="utf-8")
    Path(args.out).with_suffix(".json").write_text(
        json.dumps(
            [
                {
                    "server": r.spec.label, "command": r.spec.command, "grade": r.grade,
                    "score": r.score, "tools": r.tools, "toolset_tokens": r.toolset_tokens,
                    "top_confusion": r.top_confusion, "families": r.families, "error": r.error,
                }
                for r in rows
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {args.out}", file=sys.stderr)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
