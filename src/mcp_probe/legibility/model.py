"""The provider-agnostic small-model layer (REQ-L1, NFR-6).

One narrow interface — pick a tool for a goal, propose a rewrite — implemented by a
deterministic :class:`StubModel` (tests, no network) and by real providers (Ollama /
OpenAI-compatible / Anthropic) built lazily so the base install needs no SDK. The
canonical scorer is a pinned local model at temperature 0 with a fixed seed (ADR-004);
cloud models are allowed but marked non-canonical by the engine.

The interface is intentionally a *single decision* (which one tool?), not full task
execution — that is what makes it cheap and reliable on small models.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ModelProvider(Protocol):
    model_id: str
    seed: int
    call_count: int
    is_canonical: bool

    def choose_tool(self, goal: str, tools: list[tuple[str, str]]) -> str:
        """Given a goal and (name, description) pairs, return the chosen tool name."""
        ...

    def propose_rewrite(self, name: str, description: str, confusers: list[str]) -> str:
        """Return a rewritten description that disambiguates ``name`` from ``confusers``."""
        ...


class StubModel:
    """Deterministic scripted model for tests and the determinism harness (TEST-PLAN §3).

    ``choices`` maps a goal string to the tool it will pick (or a callable(goal, tools)).
    Missing goals fall back to the first tool. Counts calls so tests can assert a cache
    hit invoked the model zero times."""

    is_canonical = True

    def __init__(self, choices: dict | None = None, *, model_id: str = "stub", seed: int = 42) -> None:
        self._choices = choices or {}
        self.model_id = model_id
        self.seed = seed
        self.call_count = 0

    def choose_tool(self, goal: str, tools: list[tuple[str, str]]) -> str:
        self.call_count += 1
        pick = self._choices.get(goal)
        if callable(pick):
            return pick(goal, tools)
        if isinstance(pick, str):
            return pick
        return tools[0][0] if tools else ""

    def propose_rewrite(self, name: str, description: str, confusers: list[str]) -> str:
        self.call_count += 1
        extra = f" Distinct from {', '.join(confusers)}." if confusers else ""
        return f"{description.rstrip('.')}.{extra}"


def build_model(spec: str | None, *, seed: int = 42) -> ModelProvider | None:
    """Construct a provider from a ``provider:model`` spec (e.g. ``ollama:qwen2.5-3b``,
    ``anthropic:claude-haiku-4-5``, ``openai:gpt-4o-mini``). Returns None if unset."""
    if not spec:
        return None
    provider, _, model = spec.partition(":")
    provider = provider.lower()
    if provider == "ollama":
        return _OpenAICompatModel(
            model or "qwen2.5:3b", seed=seed,
            base_url="http://localhost:11434/v1", canonical=True,
        )
    if provider in ("openai", "openai-compatible"):
        return _OpenAICompatModel(model or "gpt-4o-mini", seed=seed, canonical=False)
    if provider == "anthropic":
        return _AnthropicModel(model or "claude-haiku-4-5", seed=seed)
    raise ValueError(f"unknown model provider: {provider}")


_CHOOSE_PROMPT = (
    "You are an agent choosing exactly one tool to accomplish a goal.\n"
    "Goal: {goal}\n\nTools:\n{tools}\n\n"
    "Reply with ONLY the exact name of the single best tool."
)


class _OpenAICompatModel:
    """OpenAI-compatible chat provider (also serves Ollama's /v1 endpoint)."""

    def __init__(
        self, model: str, *, seed: int, base_url: str | None = None, canonical: bool = False
    ) -> None:
        self.model_id = model
        self.seed = seed
        self.call_count = 0
        self.is_canonical = canonical
        self._base_url = base_url

    def _client(self):
        from openai import OpenAI

        if self._base_url:
            # Local OpenAI-compatible endpoints (Ollama, LM Studio) ignore the key, but the
            # SDK requires a non-empty one.
            import os

            return OpenAI(base_url=self._base_url, api_key=os.environ.get("OPENAI_API_KEY", "local"))
        return OpenAI()

    def choose_tool(self, goal: str, tools: list[tuple[str, str]]) -> str:
        self.call_count += 1
        listing = "\n".join(f"- {n}: {d}" for n, d in tools)
        resp = self._client().chat.completions.create(
            model=self.model_id,
            temperature=0,
            seed=self.seed,
            messages=[{"role": "user", "content": _CHOOSE_PROMPT.format(goal=goal, tools=listing)}],
        )
        return _match_name((resp.choices[0].message.content or "").strip(), tools)

    def propose_rewrite(self, name: str, description: str, confusers: list[str]) -> str:
        self.call_count += 1
        prompt = (
            f"Rewrite this MCP tool description so an agent won't confuse '{name}' with "
            f"{confusers}. Keep it under 2 sentences.\n\nCurrent: {description}"
        )
        resp = self._client().chat.completions.create(
            model=self.model_id, temperature=0, seed=self.seed,
            messages=[{"role": "user", "content": prompt}],
        )
        return (resp.choices[0].message.content or "").strip()


class _AnthropicModel:
    def __init__(self, model: str, *, seed: int) -> None:
        self.model_id = model
        self.seed = seed
        self.call_count = 0
        self.is_canonical = False

    def _client(self):
        from anthropic import Anthropic

        return Anthropic()

    def choose_tool(self, goal: str, tools: list[tuple[str, str]]) -> str:
        self.call_count += 1
        listing = "\n".join(f"- {n}: {d}" for n, d in tools)
        msg = self._client().messages.create(
            model=self.model_id, max_tokens=32, temperature=0,
            messages=[{"role": "user", "content": _CHOOSE_PROMPT.format(goal=goal, tools=listing)}],
        )
        text = "".join(getattr(b, "text", "") for b in msg.content).strip()
        return _match_name(text, tools)

    def propose_rewrite(self, name: str, description: str, confusers: list[str]) -> str:
        self.call_count += 1
        msg = self._client().messages.create(
            model=self.model_id, max_tokens=120, temperature=0,
            messages=[{"role": "user", "content":
                       f"Rewrite this tool description so '{name}' isn't confused with "
                       f"{confusers} (<=2 sentences):\n{description}"}],
        )
        return "".join(getattr(b, "text", "") for b in msg.content).strip()


def _match_name(reply: str, tools: list[tuple[str, str]]) -> str:
    """Map a model's free-text reply back to a real tool name (robust to chatter)."""
    names = [n for n, _ in tools]
    if reply in names:
        return reply
    for n in names:
        if n in reply:
            return n
    return names[0] if names else ""
