"""Connect + Discover: transport negotiation, version-aware handshake, surface building.

The single hardest correctness surface (ARCHITECTURE §3) because the MCP spec is
mid-transition. The concrete SDK-backed transports live in ``transport.py``; the
client *interface* and the discovery/surface logic live here and in ``client.py`` so
engines depend on a stable façade, not the SDK directly.
"""

from mcp_probe.connect.client import (
    ConnectRecord,
    FakeClient,
    InvokeResult,
    MCPClientProtocol,
)
from mcp_probe.connect.discover import surface_from_dump, surface_from_tools

__all__ = [
    "ConnectRecord",
    "FakeClient",
    "InvokeResult",
    "MCPClientProtocol",
    "surface_from_dump",
    "surface_from_tools",
]
