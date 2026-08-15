"""TapScript over the Model Context Protocol.

An MCP client -- Claude Code, an editor, an SDK script, a fleet of agents --
gets the compiler, the library, the specs and the ensemble session without
shelling out to the CLI.

    python -m tapscript.mcp              # stdio, what most clients start
    python -m tapscript.mcp --http       # loopback HTTP, for several clients

The pieces: :mod:`protocol` is JSON-RPC and nothing else, :mod:`server` maps MCP
methods onto the system, :mod:`resources` is what can be read, :mod:`tools` is
what can be called, :mod:`ensemble` is the shared score, and :mod:`features`
turns an arrangement into numbers a model can perceive.
"""

from __future__ import annotations

from .server import PROTOCOL_VERSION, Server, serve_http, serve_stdio

__all__ = ["PROTOCOL_VERSION", "Server", "serve_http", "serve_stdio"]
