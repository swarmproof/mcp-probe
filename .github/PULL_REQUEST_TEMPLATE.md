<!-- Thanks for contributing to mcp-quality! Keep PRs focused and atomic. -->

## What & why

<!-- What does this change, and why? Link the issue it closes. -->

Closes #

## Changes

<!-- Bullet the key changes. Reference stable IDs where relevant (REQ-*, NFR-*, ADR-*,
     finding codes like C12 / A1 / L7). -->

-

## Checklist

- [ ] Commits follow [Conventional Commits](https://www.conventionalcommits.org/) and are atomic
- [ ] `ruff check src/ tests/` and `mypy src/` are clean
- [ ] `pytest -m "not live_llm"` passes; new behavior has tests
- [ ] New/changed behavior that can run against a real server has a fixture-spawning **e2e**
      (or the boundary is documented if it genuinely can't)
- [ ] Docs updated (README / CHANGELOG / `docs/DECISIONS.md`) where behavior or contracts changed
- [ ] No unmeasured check is scored as `0` (degrades to **not measured** — ADR-006)
