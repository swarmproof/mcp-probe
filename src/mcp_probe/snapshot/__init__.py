"""Snapshot / regression: commit a baseline, diff every run against it (ARCHITECTURE §6)."""

from mcp_probe.snapshot.store import (
    SnapshotDiff,
    build_snapshot,
    diff_against_baseline,
    load_snapshot,
    write_snapshot,
)

__all__ = [
    "SnapshotDiff",
    "build_snapshot",
    "diff_against_baseline",
    "load_snapshot",
    "write_snapshot",
]
