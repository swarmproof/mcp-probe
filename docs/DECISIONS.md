# Implementation decisions & deviations from spec

This records where the v0.1 implementation deliberately diverges from `SPEC.md` /
`docs/*.md`, and why. It complements the `⊕ Beyond original spec` markers in the design
docs. Each entry is a decision a future maintainer (or the author) should be able to
revisit with full context.

## D1 — OWASP mapping uses the real OWASP MCP Top 10 (2025, Beta)

**Spec assumption:** the docs reference an "OWASP MCP Top 10" and finding codes like
`S1-owasp-mcp05` (i.e. `MCP01`–`MCP10` identifiers).

**What we did:** security findings anchor to the **OWASP MCP Top 10 (2025)**
(`OWASP/www-project-mcp-top-10`) as the primary `owasp_id`:
tool-poisoning/hidden-instruction → **MCP03:2025**, secrets → **MCP01:2025**,
command-execution capability → **MCP05:2025**. The mapping lives in one place
(`src/mcp_probe/security/patterns.py::OWASP`); `LLMTop10` holds the OWASP-LLM-Apps IDs for
optional dual-mapping.

**Status: corrected.** An initial build mapped to the LLM Top 10 because the MCP Top 10
hadn't been confirmed; research against `owasp.org/www-project-mcp-top-10` verified it
exists (author Vandana Verma Sehgal, 2025 edition). **Caveat:** the project is in **Beta**,
so the `MCPxx:2025` IDs may shift before GA — re-verify before mcp-probe's own 1.0.

## D2 — No `server/discover` stateless handshake probe (validated)

**Spec assumption:** ARCHITECTURE §3 describes negotiating a `2026-07-28` stateless path
(`server/discover` + per-request `_meta`) and falling back to the legacy `initialize`
handshake.

**What we did:** the connect engine negotiates the real `initialize` handshake, records
the server's reported `protocolVersion`, and leaves `stateless_discover_ok = None`
(unprobed).

**Status: validated by research.** `server/discover` is real (SEP-2575, status Final) but
ships only in the **2026-07-28 release candidate** — the latest *released/stable* spec is
**2025-11-25**, and the installed SDK (`mcp` v1.28.x, `LATEST_PROTOCOL_VERSION =
"2025-11-25"`) has no `server/discover` client method. So coding `initialize` as the
primary path and treating stateless discovery as a future (2026-07-28+) path is exactly
right. The `ConnectRecord.stateless_discover_ok` field is already present, so the probe
drops in when the RC finalises and the SDK exposes it. The forward-compat lint (REQ-C10)
still fires for legacy/SSE-only transports today.

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

**Authoritative opt-in (implemented):** `--token-model anthropic:<model>` uses the
Anthropic `count_tokens` endpoint (which accepts a `tools` array) for the exact,
billing-grade Claude count of the headline total — the only accurate Claude count, since
no offline Claude tokenizer exists. Per-tool weights stay on the fast offline leave-one-out
and are rescaled to the authoritative total (one API call, no rate-limit risk). It is
strictly opt-in and falls back silently to the labeled offline estimate when
`ANTHROPIC_API_KEY` is absent, the SDK isn't installed, or the call fails — so the fast
path stays keyless and CI never depends on it.

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
