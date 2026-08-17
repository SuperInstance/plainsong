"""Plainsong over the Model Context Protocol.

An MCP client -- Claude Code, an editor, an SDK script, a fleet of agents --
gets the compiler, the library, the specs and the ensemble session without
shelling out to the CLI.

    python -m plainsong.mcp              # stdio, what most clients start
    python -m plainsong.mcp --http       # loopback HTTP, for several clients

The pieces: :mod:`protocol` is JSON-RPC and nothing else, :mod:`server` maps MCP
methods onto the system, :mod:`resources` is what can be read, :mod:`tools` is
what can be called, and :mod:`ensemble` is the shared score. Feature
extraction -- turning an arrangement into numbers a model can perceive -- is
music analysis, not protocol, and lives at :mod:`plainsong.features`; this
package only exposes it as a tool.
"""

from __future__ import annotations

from .server import PROTOCOL_VERSION, Server, serve_http, serve_stdio

__all__ = ["PROTOCOL_VERSION", "Server", "serve_http", "serve_stdio"]
