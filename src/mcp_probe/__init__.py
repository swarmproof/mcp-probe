"""mcp-probe — the CI quality suite for MCP servers.

Lint, contract-test, benchmark, and load-test your MCP server before you ship it.
The ``pytest`` + ``lighthouse`` for the servers agents depend on.

See ``docs/ARCHITECTURE.md`` for the system design and ``docs/PRD.md`` for the
numbered requirements this package implements.
"""

__version__ = "0.1.0"

# The scoring rubric is versioned so historical scores stay comparable (NFR-7, ADR-008).
# Bump on any change to weights, grade bands, or sub-score composition.
RUBRIC_VERSION = "2026.07.1"

# The machine-readable report contract consumed by CI, registries, and the badge.
REPORT_SCHEMA = "mcp-probe/report@1"

__all__ = ["__version__", "RUBRIC_VERSION", "REPORT_SCHEMA"]
