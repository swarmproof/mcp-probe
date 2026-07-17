"""Core data model — the shared vocabulary every engine speaks.

This transcribes ARCHITECTURE.md §2. The design stance (ADR-001) is that check
engines are **pure functions** of a :class:`ServerSurface` (plus an optional live
client) yielding a :class:`FamilyScore`; they never mutate shared state. The
:class:`Scorer` and the renderers are the only aggregators. Keeping the discovery
types **frozen** enforces that: an engine physically cannot rewrite the surface it
was handed, which is what makes the fast path trivially deterministic (NFR-2) and
every engine testable against a fixed fixture with no network or LLM.

All findings/scores carry stable string IDs (``code``, ``owasp_id``, ``rubric_version``)
so results are comparable across runs and releases (ADR-008).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from typing import Any, Literal, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Discovery types — the immutable description of a server's surface.
# ---------------------------------------------------------------------------

Transport = Literal["stdio", "streamable-http", "sse"]

# Provenance of a finding — builtin checks vs. folded-in external scanners (REQ-S5).
FindingSource = Literal["builtin", "mcp-scan", "cisco", "mcp-xray"]


@dataclass(frozen=True)
class ToolDef:
    """A single tool as advertised by the server (MCP ``tools/list`` entry)."""

    name: str
    description: str | None
    input_schema: dict[str, Any]  # JSON Schema
    output_schema: dict[str, Any] | None = None  # if declared
    annotations: dict[str, Any] = field(default_factory=dict)  # readOnlyHint, destructiveHint, ...
    title: str | None = None

    @property
    def is_read_only(self) -> bool:
        """True when the server explicitly declares the tool side-effect-free."""
        return bool(self.annotations.get("readOnlyHint"))

    @property
    def is_destructive(self) -> bool:
        """Declared-destructive per annotations. Heuristic name-based detection lives
        in the Contract/Security engines; this reflects only the server's own hint."""
        # MCP defaults destructiveHint to True when unspecified for non-read-only tools,
        # but for gating we only treat an *explicit* True as destructive here.
        return self.annotations.get("destructiveHint") is True


@dataclass(frozen=True)
class ResourceDef:
    uri: str
    name: str | None = None
    description: str | None = None
    mime_type: str | None = None


@dataclass(frozen=True)
class PromptDef:
    name: str
    description: str | None = None
    arguments: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ServerSurface:
    """The immutable, canonical description of everything a server exposes.

    ``surface_hash`` is a canonical-JSON SHA-256 over the tool names + schemas +
    descriptions. It is the shared key for **both** snapshot diffing (§6) and
    legibility caching (§5) — reordering tools must not change it, but editing a
    description must (ADR-004, REQ-C7). Build via :meth:`compute_hash`.
    """

    tools: tuple[ToolDef, ...]
    resources: tuple[ResourceDef, ...] = ()
    prompts: tuple[PromptDef, ...] = ()
    server_info: dict[str, Any] = field(default_factory=dict)  # name, version
    capabilities: dict[str, Any] = field(default_factory=dict)  # negotiated caps
    protocol_version: str = ""  # "2025-11-25" | "2026-06-18" | ...
    transport: Transport = "stdio"
    surface_hash: str = ""

    def tool(self, name: str) -> ToolDef | None:
        return next((t for t in self.tools if t.name == name), None)

    @staticmethod
    def canonical_payload(tools: tuple[ToolDef, ...]) -> str:
        """Order-independent canonical JSON of the semantically-significant tool fields.

        Excludes annotations/titles deliberately: the hash tracks what an agent *reads*
        (names, descriptions, schemas), so a description edit invalidates caches while a
        cosmetic reordering does not.
        """
        items = sorted(
            (
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.input_schema,
                    "output_schema": t.output_schema,
                }
                for t in tools
            ),
            key=lambda d: d["name"],
        )
        return json.dumps(items, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def compute_hash(cls, tools: tuple[ToolDef, ...]) -> str:
        digest = hashlib.sha256(cls.canonical_payload(tools).encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    def with_hash(self) -> ServerSurface:
        """Return a copy with ``surface_hash`` populated from the current tools."""
        from dataclasses import replace

        return replace(self, surface_hash=self.compute_hash(self.tools))


# ---------------------------------------------------------------------------
# Findings & scoring.
# ---------------------------------------------------------------------------


class Severity(IntEnum):
    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def parse(cls, value: str | int | Severity) -> Severity:
        if isinstance(value, Severity):
            return value
        if isinstance(value, int):
            return cls(value)
        return cls[value.strip().upper()]

    def __str__(self) -> str:  # serialize as the lowercase name in JSON
        return self.name.lower()


@dataclass
class Finding:
    """A single graded observation. ``code`` is a stable identifier (e.g. ``C5-nondeterminism``,
    ``S1-owasp-mcp05``) referenced by tests and the JSON contract."""

    family: str  # "contract" | "legibility" | "cost" | "performance" | "security"
    code: str
    severity: Severity
    message: str
    tool: str | None = None
    remediation: str | None = None  # concrete fix — proposed rewrite / Tool Search hint / ...
    owasp_id: str | None = None  # for security findings
    source: FindingSource = "builtin"  # provenance (REQ-S5)
    evidence: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "code": self.code,
            "severity": str(self.severity),
            "message": self.message,
        }
        # Emit optional fields only when set, to keep the JSON stable and terse.
        if self.tool is not None:
            d["tool"] = self.tool
        if self.remediation is not None:
            d["remediation"] = self.remediation
        if self.owasp_id is not None:
            d["owasp_id"] = self.owasp_id
        d["source"] = self.source
        if self.evidence is not None:
            d["evidence"] = self.evidence
        return d

    @classmethod
    def from_dict(cls, family: str, d: dict[str, Any]) -> Finding:
        return cls(
            family=family,
            code=d["code"],
            severity=Severity.parse(d["severity"]),
            message=d["message"],
            tool=d.get("tool"),
            remediation=d.get("remediation"),
            owasp_id=d.get("owasp_id"),
            source=d.get("source", "builtin"),
            evidence=d.get("evidence"),
        )


# Sentinel used when a live-only family could not be measured (static mode / no LLM /
# missing scanner). It is NOT the same as a score of 0 (ADR-006): unmeasured families
# are excluded from the weighted mean rather than dragging it down.
NOT_MEASURED = "not-measured"


@dataclass
class FamilyScore:
    family: str
    score: float | None  # 0..100, or None when NOT_MEASURED
    grade: str  # "A".."F", or NOT_MEASURED
    hard_gate_tripped: bool = False  # broken contract / critical security → caps overall at C
    findings: list[Finding] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)  # family-specific numbers for the report
    measured: bool = True

    @classmethod
    def not_measured(cls, family: str, reason: str = "") -> FamilyScore:
        return cls(
            family=family,
            score=None,
            grade=NOT_MEASURED,
            measured=False,
            metrics={"reason": reason} if reason else {},
        )

    def to_dict(self, weight: float | None = None) -> dict[str, Any]:
        d: dict[str, Any] = {"grade": self.grade}
        if self.measured:
            d["score"] = round(self.score, 1) if self.score is not None else None
        else:
            d["measured"] = False
        if weight is not None:
            d["weight"] = weight
        if self.hard_gate_tripped:
            d["hard_gate"] = True
        if self.metrics:
            d["metrics"] = self.metrics
        d["findings"] = [f.to_dict() for f in self.findings]
        return d


@dataclass
class Report:
    """The aggregated, scored result — rendered to terminal/HTML/JSON/badge.

    Mirrors the JSON contract in ARCHITECTURE §7. ``rubric_version`` and
    ``provenance_hash`` make the score comparable and verifiable over time (ADR-008).
    """

    overall_score: float | None
    overall_grade: str
    families: dict[str, FamilyScore]
    surface: ServerSurface
    rubric_version: str
    tool_version: str
    weights: dict[str, float] = field(default_factory=dict)
    hard_gate: str | None = None  # family name that tripped a hard gate, if any
    regression: dict[str, Any] | None = None
    meta: dict[str, Any] = field(default_factory=dict)  # timings, model+seed, provenance

    def all_findings(self) -> list[Finding]:
        return [f for fam in self.families.values() for f in fam.findings]

    def provenance_hash(self) -> str:
        """Stable hash binding grade → (surface, rubric, per-family scores). Lets the
        badge/registry re-verify a score wasn't hand-edited (Badge spec §8 anti-gaming)."""
        basis = {
            "surface_hash": self.surface.surface_hash,
            "rubric_version": self.rubric_version,
            "overall": self.overall_score,
            "families": {
                name: (fam.score if fam.measured else NOT_MEASURED)
                for name, fam in sorted(self.families.items())
            },
        }
        payload = json.dumps(basis, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# The engine contract.
# ---------------------------------------------------------------------------


@runtime_checkable
class CheckEngine(Protocol):
    """Every check family implements this. Adding a sixth family (or a plugin) is:
    implement this Protocol and register it (pytest-plugin ergonomics, ADR-001)."""

    name: str
    requires_live: bool  # True → skipped/degraded in `static` mode (reported not-measured)
    requires_llm: bool  # True → off the CI-critical fast path (ADR-002)

    async def run(self, ctx: ProbeContext) -> FamilyScore: ...


@dataclass
class ProbeContext:
    """Everything an engine needs, and nothing it can mutate destructively.

    Carries the immutable :class:`ServerSurface`, an optional live client (absent in
    ``static`` mode), the resolved config, an optional model provider (Legibility only),
    the trace sink (OTel GenAI profile), and the loaded snapshot baseline.
    """

    surface: ServerSurface
    config: Any  # ProbeConfig — typed in config.py; Any here to avoid an import cycle
    client: Any | None = None  # MCPClient façade; None in static mode
    model: Any | None = None  # provider-agnostic small-model layer; None on the fast path
    trace: Any | None = None  # trace sink (OTel GenAI profile)
    baseline: dict[str, Any] | None = None  # loaded .mcp-probe/snapshot.json, if present

    @property
    def is_static(self) -> bool:
        return self.client is None


def dataclass_to_dict(obj: Any) -> dict[str, Any]:
    """Utility for round-trip tests of the plain (non-custom-serialized) dataclasses."""
    return asdict(obj)
