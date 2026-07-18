"""Cost engine ``[fast]`` — the context tax every agent pays just to see your tools.

Cost carries the heaviest rubric weight (30%) because it is paid on *every* turn whether
or not anything works (the mcp-xray insight, PRD §7.1). Fully offline & deterministic
(REQ-$1–$4).

* **Toolset tokens** (REQ-$1): serialize the whole toolset and count it.
* **Per-tool weight** (REQ-$2): *leave-one-out* attribution — recount with each tool
  removed; the delta is that tool's marginal cost. Robust to shared-prefix effects, so
  the numbers sum sanely and bloated outliers surface honestly.
* **$-per-task** (REQ-$3): toolset tokens × configurable price points.
* **Score**: budget-relative. ≤~2k toolset tokens ≈ 100; a quadratic-in-log penalty
  drives GitHub-scale (~55k) into single digits. Anchored so 8.1k ≈ 71 (ARCHITECTURE §7
  example) and 55k ≈ 8. The curve is part of the versioned rubric.
"""

from __future__ import annotations

import math

from mcp_probe.engines.base import EngineBase, clamp
from mcp_probe.models import FamilyScore, Finding, ProbeContext, Severity
from mcp_probe.tokens import TokenCounter, get_counter, serialize_toolset

# Below this, a toolset is "lean" and scores ~100.
TOKEN_BUDGET = 2000
# A single tool heavier than this is flagged as bloated (REQ-$2).
PER_TOOL_BLOAT = 700
# Penalty curve constants, anchored to the documented landmarks (see module docstring).
_A, _B = 10.7, 1.8

# Default price points ($ per 1M input tokens). Estimates, versioned with the rubric;
# override via config. The headline usd_per_task uses the first entry.
DEFAULT_PRICE_POINTS: dict[str, float] = {
    "premium": 3.00,  # Sonnet-class input
    "mid": 1.00,
    "cheap": 0.15,  # small/haiku-class input
}


def cost_score(toolset_tokens: int) -> float:
    if toolset_tokens <= TOKEN_BUDGET:
        return 100.0
    ratio = toolset_tokens / TOKEN_BUDGET
    log2r = math.log2(ratio)
    penalty = _A * log2r + _B * log2r * log2r
    return clamp(100.0 - penalty)


class CostEngine(EngineBase):
    name = "cost"
    requires_live = False  # fully static-ok
    requires_llm = False

    def __init__(self, counter: TokenCounter | None = None) -> None:
        self._counter = counter

    async def run(self, ctx: ProbeContext) -> FamilyScore:
        tools = ctx.surface.tools
        counter = self._counter or get_counter(getattr(ctx.config, "tokenizer", "o200k_base"))

        if not tools:
            return FamilyScore(
                family=self.name,
                score=100.0,
                grade="A",
                metrics={"toolset_tokens": 0, "counter": counter.name, "tools": 0},
            )

        toolset_tokens = counter.count(serialize_toolset(tools))

        # Leave-one-out marginal attribution (REQ-$2).
        per_tool: dict[str, int] = {}
        for t in tools:
            without = tuple(x for x in tools if x.name != t.name)
            without_tokens = counter.count(serialize_toolset(without)) if without else 0
            per_tool[t.name] = max(0, toolset_tokens - without_tokens)

        findings: list[Finding] = []
        for name, weight in sorted(per_tool.items(), key=lambda kv: kv[1], reverse=True):
            if weight > PER_TOOL_BLOAT:
                findings.append(
                    Finding(
                        family=self.name,
                        code="$2-bloat",
                        severity=Severity.MEDIUM if weight < 2 * PER_TOOL_BLOAT else Severity.HIGH,
                        tool=name,
                        message=f"tool '{name}' costs ~{weight} tokens of context on every turn",
                        remediation=(
                            "tighten the description/schema, split the tool, or adopt "
                            "Tool Search / lazy-loading to defer its context cost"
                        ),
                        evidence={"tokens": weight},
                    )
                )

        price_points = self._resolve_price_points(ctx)
        usd_by_point = {
            label: round(toolset_tokens / 1_000_000 * price, 4)
            for label, price in price_points.items()
        }
        headline_label = next(iter(price_points))
        usd_per_task = usd_by_point[headline_label]

        score = cost_score(toolset_tokens)
        # Offline counters are OpenAI-family tokenizers; they UNDERCOUNT Claude by ~15-20%
        # (more on code / non-English). Label the number so it's never mistaken for a
        # billing-grade Claude count. The authoritative path is a provider count_tokens.
        estimate_note = (
            "estimate (OpenAI tokenizer; undercounts Claude ~15-20%)"
            if counter.name != "provider"
            else None
        )
        metrics = {
            "toolset_tokens": toolset_tokens,
            "per_tool_tokens": dict(sorted(per_tool.items(), key=lambda kv: kv[1], reverse=True)),
            "usd_per_task": usd_per_task,
            "usd_by_price_point": usd_by_point,
            "counter": counter.name,
            "counter_note": estimate_note,
            "tools": len(tools),
        }
        from mcp_probe.scoring import grade_for_score

        return FamilyScore(
            family=self.name,
            score=score,
            grade=grade_for_score(score),
            findings=findings,
            metrics=metrics,
        )

    @staticmethod
    def _resolve_price_points(ctx: ProbeContext) -> dict[str, float]:
        configured = getattr(ctx.config, "price_points", ()) or ()
        if not configured:
            return DEFAULT_PRICE_POINTS
        # config price points are "label:usd" strings, e.g. "premium:3.0"
        out: dict[str, float] = {}
        for item in configured:
            if ":" in item:
                label, _, val = item.partition(":")
                try:
                    out[label] = float(val)
                except ValueError:
                    continue
        return out or DEFAULT_PRICE_POINTS
