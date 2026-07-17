"""Performance internals — the concurrency-core stand-in + pure metric helpers.

Reuses the *shape* of stampede's concurrency-core (a Scheduler running a concurrency
curve over uniform tasks). Vendored-minimal here until the shared primitive is extracted
(ARCHITECTURE §10). The metric helpers (percentiles, degradation classifier, leak
detector) are pure functions so they unit-test without any I/O.
"""

from mcp_probe.perf.load import (
    ConcurrencyCurve,
    LoadResult,
    classify_degradation,
    detect_leak,
    percentile,
    run_load,
)

__all__ = [
    "ConcurrencyCurve",
    "LoadResult",
    "classify_degradation",
    "detect_leak",
    "percentile",
    "run_load",
]
