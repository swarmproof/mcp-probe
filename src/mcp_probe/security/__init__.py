"""Security-lite: own the easy 80% (builtin lints), integrate for the hard 20%."""

from mcp_probe.security.patterns import (
    OWASP,
    LLMTop10,
    scan_dangerous_capabilities,
    scan_injection,
    scan_secrets,
)

__all__ = ["OWASP", "LLMTop10", "scan_injection", "scan_secrets", "scan_dangerous_capabilities"]
