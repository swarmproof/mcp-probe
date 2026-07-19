"""Legibility engine ``[llm]`` — the moat (ARCHITECTURE §5).

Composes: offline description lints (always) + an offline lexical confusable-shortlist +,
when a model is configured, a seeded comprehension probe that measures right-tool-selection
rate and builds an N×N disambiguation matrix, plus proposed rewrites for confused tools.
Results are cached by (surface_hash, model, seed, goal_set) so a rerun is a byte-identical
cache hit that invokes the model zero times (REQ-L4/L6).

Score = selection_rate × (1 − mean confusion) × 100 − lint penalty (PRD §7.3). With no
model, the behavioural part is reported "not measured" and the score falls back to the
lints — honest, and still useful offline.
"""

from __future__ import annotations

from mcp_probe.engines.base import EngineBase, clamp
from mcp_probe.legibility.cache import LegibilityCache, cache_key
from mcp_probe.legibility.lints import lint_descriptions
from mcp_probe.legibility.model import ModelProvider
from mcp_probe.legibility.similarity import confusable_shortlist
from mcp_probe.models import FamilyScore, Finding, ProbeContext, ServerSurface, Severity

# Templated goal phrasings per tool → multiple trials → fractional confusion rates.
GOAL_TEMPLATES = (
    "I need to {intent}",
    "How do I {intent}?",
    "Help me {intent}",
)

_LINT_PENALTY = {
    Severity.INFO: 0,
    Severity.LOW: 2,
    Severity.MEDIUM: 5,
    Severity.HIGH: 10,
    Severity.CRITICAL: 15,
}


def _intent(description: str | None, name: str) -> str:
    text = (description or name).strip().rstrip(".")
    return text[0].lower() + text[1:] if text else name


def build_goals(surface: ServerSurface) -> list[tuple[str, str]]:
    """Return (goal_text, golden_tool_name) pairs derived from each tool's own description.
    Each tool implies goals it *should* win; identical descriptions collide → confusion."""
    goals: list[tuple[str, str]] = []
    for t in surface.tools:
        intent = _intent(t.description, t.name)
        for template in GOAL_TEMPLATES:
            goals.append((template.format(intent=intent), t.name))
    return goals


class LegibilityEngine(EngineBase):
    name = "legibility"
    requires_live = False
    requires_llm = True

    def __init__(self, model: ModelProvider | None = None) -> None:
        self._model = model

    async def run(self, ctx: ProbeContext) -> FamilyScore:
        lints = lint_descriptions(ctx.surface)
        lint_penalty = min(30, sum(_LINT_PENALTY.get(f.severity, 0) for f in lints))
        shortlist = confusable_shortlist(ctx.surface)

        model = self._model or ctx.model
        if model is None:
            # No model → behavioural part not measured; score from lints only (honest).
            score = clamp(100 - lint_penalty)
            from mcp_probe.scoring import grade_for_score

            return FamilyScore(
                family=self.name,
                score=score,
                grade=grade_for_score(score),
                findings=lints,
                metrics={
                    "selection_rate": None,
                    "behavioural": "not measured (no model configured)",
                    "lexical_confusable_pairs": shortlist[:5],
                },
            )

        probe = self._run_or_cache(ctx, model)
        selection_rate = probe["selection_rate"]
        top_confusion = probe["top_confusion"]
        mean_conf = probe["mean_confusion"]

        # Build findings from the (possibly cached) probe data — no model calls here, so a
        # cache hit invokes the model zero times (REQ-L6).
        findings = list(lints) + self._findings_from_probe(probe)

        base = selection_rate * (1 - mean_conf) * 100
        score = clamp(base - lint_penalty)
        from mcp_probe.scoring import grade_for_score

        metrics = {
            "selection_rate": round(selection_rate, 3),
            "top_confusion": top_confusion,
            "mean_confusion": round(mean_conf, 3),
            "model": model.model_id,
            "seed": model.seed,
            "goal_set_version": getattr(ctx.config, "goal_set_version", "1"),
            "canonical": model.is_canonical,
            "cache_hit": probe["cache_hit"],
            "lexical_confusable_pairs": shortlist[:5],
            "matrix": probe.get("matrix"),
            "tool_order": probe.get("tool_order"),
            "per_tool_total": probe.get("per_tool_total"),
        }
        return FamilyScore(
            family=self.name, score=score, grade=grade_for_score(score),
            findings=findings, metrics=metrics,
        )

    def _run_or_cache(self, ctx: ProbeContext, model: ModelProvider) -> dict:
        gsv = getattr(ctx.config, "goal_set_version", "1")
        key = cache_key(ctx.surface.surface_hash, model.model_id, model.seed, gsv)
        cache = LegibilityCache(getattr(ctx.config, "cache_dir", ".mcp-probe/cache"))
        cached = cache.get(key)
        if cached is not None:
            cached["cache_hit"] = True
            return cached  # model NOT invoked → determinism + ~$0 rerun (REQ-L6)

        result = self._comprehension_probe(ctx.surface, model)
        result["rewrites"] = self._generate_rewrites(ctx.surface, model, result)
        result["cache_hit"] = False
        cache.put(key, {k: v for k, v in result.items() if k != "cache_hit"})
        return result

    def _comprehension_probe(self, surface: ServerSurface, model: ModelProvider) -> dict:
        goals = build_goals(surface)
        tool_pairs = [(t.name, t.description or "") for t in surface.tools]
        names = [t.name for t in surface.tools]
        per_tool_total: dict[str, int] = {n: 0 for n in names}
        confusion: dict[str, dict[str, int]] = {n: {} for n in names}
        correct = 0

        for goal_text, golden in goals:
            chosen = model.choose_tool(goal_text, tool_pairs)
            per_tool_total[golden] += 1
            if chosen == golden:
                correct += 1
            else:
                confusion[golden][chosen] = confusion[golden].get(chosen, 0) + 1

        total = len(goals) or 1
        selection_rate = correct / total

        # top confusion pair: (true, chosen, rate) with the highest off-diagonal rate.
        top_confusion = None
        best_rate = 0.0
        conf_rates: list[float] = []
        for true_tool, chosens in confusion.items():
            denom = per_tool_total[true_tool] or 1
            for chosen_tool, count in chosens.items():
                rate = count / denom
                conf_rates.append(rate)
                if rate > best_rate:
                    best_rate = rate
                    top_confusion = [true_tool, chosen_tool, round(rate, 3)]
        mean_conf = (sum(conf_rates) / len(conf_rates)) if conf_rates else 0.0

        low_tools = [t for t, tot in per_tool_total.items()
                     if tot and (tot - sum(confusion[t].values())) / tot < 0.6]

        return {
            "selection_rate": selection_rate,
            "top_confusion": top_confusion,
            "mean_confusion": mean_conf,
            "low_tools": low_tools,
            # Full N×N disambiguation matrix (the screenshot-worthy artifact). Only the
            # off-diagonal (confused) counts are stored; the renderer derives the diagonal
            # from per_tool_total. Kept for surfaces small enough to display (<= 15 tools).
            "matrix": {t: dict(c) for t, c in confusion.items()} if len(names) <= 15 else None,
            "tool_order": names if len(names) <= 15 else None,
            "per_tool_total": per_tool_total if len(names) <= 15 else None,
        }

    def _generate_rewrites(self, surface, model, probe) -> list[dict]:
        """Call the model to propose rewrites for confused/low tools. Runs ONCE, before
        the result is cached, so reruns don't re-invoke the model (REQ-L6)."""
        targets = set(probe["low_tools"])
        confusers: dict[str, list[str]] = {}
        top = probe["top_confusion"]
        if top:
            a, b, _rate = top
            targets.update([a, b])
            confusers.setdefault(a, []).append(b)
            confusers.setdefault(b, []).append(a)
        rewrites: list[dict] = []
        for name in sorted(targets):
            tool = surface.tool(name)
            if tool is None:
                continue
            rewrite = model.propose_rewrite(name, tool.description or "", confusers.get(name, []))
            rewrites.append({"tool": name, "rewrite": rewrite})
        return rewrites

    @staticmethod
    def _findings_from_probe(probe: dict) -> list[Finding]:
        """Pure: reconstruct findings from probe data (cached or fresh). No model calls."""
        findings: list[Finding] = []
        top = probe.get("top_confusion")
        if top:
            a, b, rate = top
            findings.append(
                Finding(
                    family="legibility", code="L2-confusion", severity=Severity.HIGH, tool=a,
                    message=f"agents chose '{b}' when '{a}' was correct {rate:.0%} of the time",
                    remediation="disambiguate the two descriptions (see proposed rewrite)",
                    evidence={"pair": [a, b], "rate": rate},
                )
            )
        for entry in probe.get("rewrites", []):
            findings.append(
                Finding(
                    family="legibility", code="L5-rewrite", severity=Severity.LOW,
                    tool=entry["tool"],
                    message=f"'{entry['tool']}' is hard to select; a clearer description would help",
                    remediation=f"proposed: {entry['rewrite']}",
                )
            )
        return findings
