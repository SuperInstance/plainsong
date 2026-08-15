"""The Model Context Protocol server.

Everything TapScript can do, offered to any agent that speaks MCP: the tools
the built-in agent uses, the notation library and the specs as resources, the
two agent prompts, and the ensemble session that lets several agents write one
score at once.

The tool list is not written here. It is
:meth:`~tapscript.agent.tools.ToolRegistry.specs`, which already produces JSON
Schema, so a tool added anywhere in the codebase appears over the protocol
without this file changing. That is the same reason the interfaces all call
``pipeline.compile_text``: one definition, three ways in.

Two transports carry the same messages. Stdio is what every client supports and
is the default. HTTP is for the cases stdio cannot reach -- a fleet of agents on
one session, a client on another process -- and follows the posture of the web
interface: loopback by default, cross-origin refused, and a loud warning if it
is bound anywhere else.
"""

from __future__ import annotations

import json
import sys
import threading
from typing import Any
from urllib.parse import urlparse

from ..runtime.config import Config, load_config
from ..version import __version__
from . import protocol
from . import tools as mcp_tools
from .protocol import Dispatcher, RpcError
from .resources import NotFound, Resources

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

RESOURCE_NOT_FOUND = -32002
"""MCP's own code for a URI that resolves to nothing. The standard codes carry
everything else."""

SERVER_NAME = "tapscript"

PROMPTS = {
    "composer": "Write and revise notation. Reads the reference, writes, compiles, reports.",
    "builder": "Adapt this installation to the machine it is on and verify the result.",
}

INSTRUCTIONS = """TapScript compiles plain-text music notation to MIDI and audio.

Read tapscript://notation-reference before writing notation for the first time.
Write music with write_score or ensemble_write_part rather than write_file: both
parse the notation before anything reaches disk.

Several agents can write one score at once. Open or read a session with
ensemble_read, claim one voice with ensemble_join, and write only that voice.
Every write carries the version you read it at, so a part that moved under you
is refused rather than overwritten.
"""

MAX_BODY = 4 * 1024 * 1024


class Server:
    """One MCP server: a tool registry, a resource set, and a dispatcher."""

    def __init__(
        self,
        config: Config | None = None,
        registry: Any = None,
        session_root: Any = None,
        allow_dangerous: bool = False,
    ) -> None:
        from ..agent.tools import ToolRegistry

        self.config = config or load_config()
        self.registry = registry or ToolRegistry(
            config=self.config, allow_dangerous=allow_dangerous
        )
        mcp_tools.register(self.registry, session_root=session_root)
        self.resources = Resources(self.config, session_root=session_root)
        self.initialized = False
        self.client: dict[str, Any] = {}
        self.protocol_version = PROTOCOL_VERSION
        self.lock = threading.Lock()
        self.dispatcher = self._build_dispatcher()

    # -- wiring --------------------------------------------------------------

    def _build_dispatcher(self) -> Dispatcher:
        dispatcher = Dispatcher()
        dispatcher.register("initialize", self.initialize)
        dispatcher.register("notifications/initialized", self.initialized_notice)
        dispatcher.register("ping", lambda params: {})
        dispatcher.register("tools/list", self.list_tools)
        dispatcher.register("tools/call", self.call_tool)
        dispatcher.register("resources/list", self.list_resources)
        dispatcher.register("resources/templates/list", self.list_resource_templates)
        dispatcher.register("resources/read", self.read_resource)
        dispatcher.register("prompts/list", self.list_prompts)
        dispatcher.register("prompts/get", self.get_prompt)
        return dispatcher

    def handle_text(self, line: str) -> str | None:
        """One line of JSON in, one line of JSON out, or nothing for a notification."""
        return self.dispatcher.handle_text(line)

    def handle(self, payload: Any) -> dict[str, Any] | None:
        return self.dispatcher.handle(payload)

    # -- lifecycle -----------------------------------------------------------

    def initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Agree a protocol version and say what this server carries."""
        requested = str(params.get("protocolVersion", "") or "")
        # Speak the client's version when we know it, ours when we do not. A
        # client that cannot live with the answer says so and disconnects.
        self.protocol_version = (
            requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
        )
        self.client = dict(params.get("clientInfo") or {})
        return {
            "protocolVersion": self.protocol_version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {"name": SERVER_NAME, "title": "TapScript", "version": __version__},
            "instructions": INSTRUCTIONS,
        }

    def initialized_notice(self, params: dict[str, Any]) -> None:
        self.initialized = True
        return None

    # -- tools ---------------------------------------------------------------

    def list_tools(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "tools": [
                {
                    "name": spec.name,
                    "description": spec.description,
                    "inputSchema": spec.parameters,
                }
                for spec in sorted(self.registry.specs(), key=lambda spec: spec.name)
            ]
        }

    def call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run one tool. A tool that fails returns a result, not an error."""
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise protocol.invalid_params("tools/call needs a tool name")
        arguments = params.get("arguments", {})
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise protocol.invalid_params("arguments must be an object")
        known = {spec.name for spec in self.registry.specs()}
        if name not in known:
            raise protocol.invalid_params(
                f"unknown tool: {name}", {"tools": sorted(known)}
            )

        # The registry is not built for two callers at once, and a tool that
        # writes files is not something to run twice over.
        with self.lock:
            text, failed = self.registry.call_result(name, arguments)

        result: dict[str, Any] = {
            "content": [{"type": "text", "text": text}],
            "isError": failed,
        }
        structured = _structured(text)
        if structured is not None and not result["isError"]:
            result["structuredContent"] = structured
        return result

    # -- resources -----------------------------------------------------------

    def list_resources(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"resources": self.resources.list()}

    def list_resource_templates(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"resourceTemplates": self.resources.templates()}

    def read_resource(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            raise protocol.invalid_params("resources/read needs a uri")
        try:
            return {"contents": self.resources.read(uri)}
        except NotFound as exc:
            raise RpcError(RESOURCE_NOT_FOUND, str(exc), {"uri": uri}) from None

    # -- prompts -------------------------------------------------------------

    def list_prompts(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "prompts": [
                {
                    "name": name,
                    "description": description,
                    "arguments": [
                        {
                            "name": "task",
                            "description": "What you want done. Appended to the prompt.",
                            "required": False,
                        }
                    ],
                }
                for name, description in PROMPTS.items()
            ]
        }

    def get_prompt(self, params: dict[str, Any]) -> dict[str, Any]:
        from ..agent.kernel import load_prompt

        name = params.get("name")
        if not isinstance(name, str) or name not in PROMPTS:
            raise protocol.invalid_params(
                f"unknown prompt: {name!r}", {"prompts": sorted(PROMPTS)}
            )
        text = load_prompt(name)
        if not text:
            raise RpcError(protocol.INTERNAL_ERROR, f"the {name} prompt is missing from this install")
        arguments = params.get("arguments") or {}
        task = str(arguments.get("task", "")).strip() if isinstance(arguments, dict) else ""
        if task:
            text = f"{text}\n\nThe task:\n\n{task}"
        return {
            "description": PROMPTS[name],
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
        }


def _structured(text: str) -> dict[str, Any] | None:
    """A tool result that is already an object, handed over as data as well as text."""
    if text.lstrip()[:1] != "{":
        return None
    try:
        decoded = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return decoded if isinstance(decoded, dict) else None


# --------------------------------------------------------------------------
# transports
# --------------------------------------------------------------------------


def serve_stdio(server: Server | None = None, config: Config | None = None) -> int:
    """Serve on stdin/stdout. Nothing else may write to stdout while this runs."""
    server = server or Server(config=config)
    return protocol.serve_stdio(server.dispatcher, sys.stdin, sys.stdout)


def build_http_handler(server: Server):
    """The HTTP request handler for one server, carrying the same messages."""
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        server_version = f"tapscript-mcp/{__version__}"
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # quieter default
            if server.config.get("mcp", "access_log", False):
                super().log_message(format, *args)

        def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _host_is_local(self) -> bool:
            """Whether Host names this machine rather than a domain.

            Origin-against-Host alone is defeated by DNS rebinding: point
            `evil.example` at 127.0.0.1 and both headers read `evil.example`,
            matching perfectly. A rebound request always carries the attacker's
            hostname, so requiring a loopback Host breaks it.
            """
            host = self.headers.get("Host", "")
            name = host.rsplit(":", 1)[0].strip("[]").lower() if host else ""
            return name in {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""} or name.startswith(
                "127."
            )

        def _same_origin(self) -> bool:
            """Refuse cross-origin calls. This is a local tool, not a service."""
            if not self._host_is_local():
                return False
            origin = self.headers.get("Origin")
            if origin is None:
                return True
            return urlparse(origin).netloc == self.headers.get("Host", "")

        def do_GET(self) -> None:  # noqa: N802 - required by the base class
            body = json.dumps(
                {
                    "server": SERVER_NAME,
                    "version": __version__,
                    "protocolVersion": server.protocol_version,
                    "transport": "http",
                    "methods": server.dispatcher.method_names(),
                }
            ).encode("utf-8")
            self._send(200, body)

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

        def do_POST(self) -> None:  # noqa: N802
            if not self._same_origin():
                self._send(403, b'{"error":"cross-origin requests are not accepted"}')
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length <= 0 or length > MAX_BODY:
                self._send(400, b'{"error":"a request body is required"}')
                return
            raw = self.rfile.read(length).decode("utf-8", "replace")
            answer = server.handle_text(raw)
            if answer is None:
                self._send(202, b"", "application/json")  # a notification
                return
            self._send(200, answer.encode("utf-8"))

    return Handler


def serve_http(
    server: Server | None = None,
    config: Config | None = None,
    host: str = "127.0.0.1",
    port: int = 8766,
    out: Any = None,
) -> int:
    """Run the HTTP transport until interrupted."""
    from http.server import ThreadingHTTPServer

    config = config or load_config()
    server = server or Server(config=config)
    handler = build_http_handler(server)

    try:
        http = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        message = f"could not bind {host}:{port}: {exc}"
        if out:
            out.fail(message)
        else:
            print(message, file=sys.stderr)
        return 1

    url = f"http://{host}:{http.server_port}"
    lines = [f"tapscript mcp on {url}", f"workspace {config.paths.workspace}"]
    if host not in ("127.0.0.1", "localhost", "::1"):
        lines.append(
            "warning: bound to a non-loopback address -- anyone who can reach this port "
            "can run every tool on this machine's workspace"
        )
    for line in lines:
        if out:
            out.dim(line)
        else:
            print(line, file=sys.stderr)

    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        http.server_close()
    return 0
