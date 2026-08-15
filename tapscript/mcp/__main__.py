"""``python -m tapscript.mcp`` -- the entry point an MCP client is pointed at.

Stdio by default, because that is what a client configuration file expects to
launch. Everything this prints for a person goes to stderr: stdout carries the
protocol, and one stray line on it desynchronises the client.
"""

from __future__ import annotations

import argparse
import sys

from ..runtime.config import load_config
from ..version import __version__
from .server import Server, serve_http, serve_stdio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tapscript.mcp",
        description="Serve TapScript over the Model Context Protocol.",
    )
    parser.add_argument("--version", action="version", version=f"tapscript {__version__}")
    parser.add_argument("--http", action="store_true", help="serve over HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind address (loopback)")
    parser.add_argument("--port", type=int, default=8766, help="HTTP port")
    parser.add_argument(
        "--workspace", metavar="DIR", help="where tools may write; defaults to the workspace"
    )
    parser.add_argument(
        "--sessions", metavar="DIR", help="where ensemble sessions live; defaults to the workspace"
    )
    parser.add_argument(
        "--allow-dangerous", action="store_true", help="offer tools that need approval"
    )
    parser.add_argument("--list-tools", action="store_true", help="print the tools and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()

    registry = None
    if args.workspace:
        from pathlib import Path

        from ..agent.tools import Sandbox, ToolRegistry

        registry = ToolRegistry(
            sandbox=Sandbox(root=Path(args.workspace)),
            config=config,
            allow_dangerous=args.allow_dangerous,
        )

    from pathlib import Path

    server = Server(
        config=config,
        registry=registry,
        session_root=Path(args.sessions) if args.sessions else None,
        allow_dangerous=args.allow_dangerous,
    )

    if args.list_tools:
        for spec in sorted(server.registry.specs(), key=lambda spec: spec.name):
            print(f"{spec.name:<22} {spec.description.splitlines()[0]}")
        return 0

    if args.http:
        return serve_http(server, config=config, host=args.host, port=args.port)

    print(f"tapscript mcp {__version__} on stdio", file=sys.stderr)
    return serve_stdio(server)


if __name__ == "__main__":
    raise SystemExit(main())
