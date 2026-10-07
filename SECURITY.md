# Security Policy

`mcp-quality` is a tool people run against servers they're evaluating, often in CI. We take
its security — and the responsible disclosure of issues in it — seriously.

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Report privately via GitHub's **[Private vulnerability reporting](https://github.com/swarmproof/mcp-probe/security/advisories/new)**
(the "Report a vulnerability" button under the repository's **Security** tab). This keeps
the report confidential until a fix is available.

> Maintainers: enable this under **Settings → Code security → Private vulnerability
> reporting**, or replace this section with a dedicated `security@` address.

Please include:
- a description of the issue and its impact,
- steps to reproduce (a minimal `tools/list` dump or server command is ideal),
- the `mcp-quality` version (`mcp-quality --version`) and Python version.

## What to expect

- **Acknowledgement** within a few business days.
- An assessment and, for confirmed issues, a fix on a reasonable timeline based on severity.
- Credit in the release notes if you'd like it (let us know).

## Scope

In scope: the `mcp-quality` package, its CLI, and the `serve` scoring API.

Out of scope: vulnerabilities in the **servers mcp-quality grades** (report those to their
maintainers), and in third-party scanners invoked via `--deep-security` (report upstream).

## Supported versions

Security fixes land on the latest released minor version on PyPI. Please upgrade
(`pip install -U mcp-quality`) before reporting to confirm the issue still reproduces.
