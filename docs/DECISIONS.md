# Implementation decisions & deviations from spec

This records where the v0.1 implementation deliberately diverges from `SPEC.md` /
`docs/*.md`, and why. It complements the `⊕ Beyond original spec` markers in the design
docs. Each entry is a decision a future maintainer (or the author) should be able to
revisit with full context.

## D1 — OWASP mapping uses the LLM Top 10 (2025), not an "MCP Top 10"

**Spec assumption:** the docs reference an "OWASP MCP Top 10" and finding codes like
`S1-owasp-mcp05` (i.e. `MCP01`–`MCP10` identifiers).

**What we did:** security findings anchor to the **OWASP Top 10 for LLM Applications
2025** (`LLM01:2025` Prompt Injection, `LLM02:2025` Sensitive Information Disclosure,
`LLM06:2025` Excessive Agency). The MCP-specific threat name (tool poisoning, rug-pull,
excessive agency) is carried in the finding message; `owasp_id` points at the real,
stable standard.

**Why:** at build time, a *finalised, authoritative* "OWASP MCP Top 10" with stable
`MCPxx` IDs was not confirmed. Anchoring to the established LLM Top 10 keeps `owasp_id`
meaningful and lets findings dedup cleanly against external scanners (mcp-scan/Cisco),
which also map to it. **Revisit** if/when an official OWASP MCP Top 10 ships — the mapping
lives in one place (`src/mcp_probe/security/patterns.py::OWASP`).

## D2 — No `server/discover` stateless handshake probe

**Spec assumption:** ARCHITECTURE §3 describes negotiating a `2026-07-28` stateless path
(`server/discover` + per-request `_meta`) and falling back to the legacy `initialize`
handshake.

**What we did:** the connect engine negotiates the real `initialize` handshake the
official SDK implements, records the server's reported `protocolVersion`, and leaves
`stateless_discover_ok = None` (unprobed) rather than fabricating a probe.

**Why:** the installed official MCP Python SDK exposes no `server/discover` client method
(verified by introspection). Implementing a probe for a method that doesn't exist would
manufacture a false forward-compat signal. The `ConnectRecord` already carries the
`stateless_discover_ok` field, so when the SDK adds the method the probe drops in without
a data-model change. The forward-compat lint (REQ-C10) still fires for legacy/SSE-only
transports via the fields we *can* observe.

## D3 — Offline token counter falls back to a deterministic heuristic

**Spec:** REQ-$4 wants authoritative counts via a provider `count_tokens` and a
deterministic offline tokenizer (tiktoken).

**What we did:** `tiktoken` is the preferred counter, but it fetches its BPE vocab on
first use; in an air-gapped CI (NFR-8) that fetch fails. So `get_counter()` degrades to a
deterministic word/punctuation heuristic that never needs the network. The counter used
is reported in `cost.metrics.counter` so the number's provenance is explicit.

**Why:** NFR-2 (byte-identical fast path) and NFR-8 (air-gapped `static`) are hard
requirements; a counter that silently needs the network would violate both. The heuristic
is lower-fidelity but reproducible; the *relative* per-tool attribution the score depends
on is preserved.

## D4 — Legibility runs offline lints without a model (partial, not blank)

**Spec:** Legibility is `[llm]`, opt-in, off the CI-critical path (ADR-002).

**What we did:** with no model configured, the Legibility engine still runs its static
description lints and lexical confusable-shortlist, scoring from those and marking the
behavioural `selection_rate` as "not measured". It does not blank the whole family.

**Why:** the lints are valuable, offline, and deterministic. Reporting a lint-based
partial score is more useful than "not measured" and still honest (the behavioural metric
is explicitly absent). The full comprehension probe + disambiguation matrix run when a
model is provided.

## D5 — Shared primitives are vendored-minimal, bound to stampede's contracts

Per DELIVERY-PLAN §1.3 (vendor-first): `report-renderer` (terminal/HTML oxblood view),
`trace-format` (OTel GenAI profile sink, `src/mcp_probe/trace.py`), and the
concurrency-core *shape* (`src/mcp_probe/perf/load.py`) are implemented locally rather
than imported from stampede. The **contracts** (RunReport view, `gen_ai.*`/`swarmproof.*`
attributes, Scheduler-over-a-curve shape) match the documented primitives so extraction
at ~stampede v0.2 is mechanical.

## D6 — Python 3.11+ only; dropped the `tomli` fallback

`requires-python = ">=3.11"`, so config parsing uses stdlib `tomllib` directly. The
conditional `tomli` dependency is retained in `pyproject.toml` but is inert on supported
interpreters.
