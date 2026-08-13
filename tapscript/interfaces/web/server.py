"""The web interface.

``http.server`` from the standard library, threaded so a slow agent call does
not block the page. It binds to loopback by default and refuses cross-origin
requests, because it is a local tool rather than a service.

The page itself is ``app.html`` next to this file -- a real file you can edit,
not a string embedded in Python.
"""

from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ...runtime.config import Config, load_config
from ...version import __version__

WEB_ROOT = Path(__file__).parent
MAX_BODY = 4 * 1024 * 1024


def check_importable() -> tuple[bool, str]:
    """Spec check: the interface can be constructed and its page exists."""
    page = WEB_ROOT / "app.html"
    if not page.exists():
        return False, "app.html is missing from the install"
    handler = build_handler(load_config())
    if not callable(handler):
        return False, "handler could not be built"
    return True, f"page is {page.stat().st_size} bytes"


class Api:
    """The behaviour behind each endpoint, separated from the HTTP plumbing."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.lock = threading.Lock()

    # -- reads ---------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        from ...llm.registry import auto_select, provider_status
        from ...runtime.capabilities import probe

        report = probe()
        configured = [status for status in provider_status(self.config.paths) if status.configured]
        return {
            "version": __version__,
            "workspace": str(self.config.paths.workspace),
            "capabilities": {capability.name: capability.present for capability in report},
            "providers": [status.info.id for status in configured],
            "provider": self.config.get("llm", "provider", "") or auto_select(self.config.paths, report),
            "model": self.config.get("llm", "model", ""),
        }

    def library(self, query: str, limit: int) -> dict[str, Any]:
        from ...library import Library

        library = Library(paths=self.config.paths)
        entries = library.search(query, limit=limit) if query else library.entries(limit=limit)
        return {"total": len(library), "entries": [entry.as_dict() for entry in entries]}

    def read_entry(self, name: str) -> dict[str, Any]:
        from ...library import Library

        entry = Library(paths=self.config.paths).find(name)
        if entry is None:
            return {"error": f"no entry called {name!r}"}
        return {"name": entry.name, "title": entry.title, "path": str(entry.path), "content": entry.read()}

    def examples(self) -> dict[str, Any]:
        from ..cli import STARTER

        return {"starter": STARTER.format(title="New Piece")}

    # -- writes --------------------------------------------------------------

    def compile(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ...pipeline import compile_text, slugify

        content = str(payload.get("content", ""))
        if not content.strip():
            return {"error": "nothing to compile"}

        want_audio = bool(payload.get("audio", True))
        from ...notation import parse

        score = parse(content)
        stem = slugify(score.meta.title or "sketch")
        output = self.config.paths.output_dir

        with self.lock:
            result = compile_text(
                content,
                midi=output / f"{stem}.mid",
                audio=(output / f"{stem}.wav") if want_audio else None,
                config=self.config,
            )

        response = result.summary()
        response["ok"] = result.ok
        response["messages"] = result.messages
        if result.midi_path:
            response["midi_url"] = f"/files/{result.midi_path.name}"
        if result.audio_path:
            response["audio_url"] = f"/files/{result.audio_path.name}"
        return response

    def transpose(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ...transform import transpose

        content = str(payload.get("content", ""))
        key = str(payload.get("key", "")).strip()
        if not content.strip() or not key:
            return {"error": "content and key are both required"}
        try:
            target: Any = int(key) if key.lstrip("+-").isdigit() else key
            return {"content": transpose(content, target)}
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    def agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ...agent.kernel import Agent
        from ...agent.tools import ToolRegistry
        from ...llm.registry import get_provider
        from ...llm.types import ProviderError

        prompt = str(payload.get("prompt", "")).strip()
        if not prompt:
            return {"error": "no prompt"}

        events: list[dict[str, Any]] = []
        try:
            provider = get_provider(
                self.config,
                provider_id=str(payload.get("provider", "")),
                model=str(payload.get("model", "")),
            )
        except ProviderError as exc:
            return {"error": str(exc)}

        agent = Agent(
            provider=provider,
            tools=ToolRegistry(config=self.config),
            config=self.config,
            role=str(payload.get("role", "composer")),
            on_event=lambda event: events.append(event.as_dict()),
        )
        with self.lock:
            result = agent.run(prompt)
        return {
            "reply": result.reply,
            "error": result.error,
            "steps": result.steps,
            "tools": result.tool_calls,
            "events": [event for event in events if event["kind"] in ("tool_call", "message", "error")],
        }


def build_handler(config: Config):
    """Create the request handler class bound to one configuration."""
    api = Api(config)

    class Handler(BaseHTTPRequestHandler):
        server_version = f"tapscript/{__version__}"
        protocol_version = "HTTP/1.1"

        # -- plumbing --------------------------------------------------------

        def log_message(self, format: str, *args: Any) -> None:  # quieter default
            if config.get("web", "access_log", False):
                super().log_message(format, *args)

        def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload, default=str).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def _same_origin(self) -> bool:
            """Reject cross-origin writes; this is a local tool, not an API."""
            origin = self.headers.get("Origin")
            if origin is None:
                return True
            host = self.headers.get("Host", "")
            return urlparse(origin).netloc == host

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length <= 0 or length > MAX_BODY:
                return {}
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return {}

        # -- routes ----------------------------------------------------------

        def do_GET(self) -> None:  # noqa: N802 - required by the base class
            parsed = urlparse(self.path)
            route = parsed.path
            query = parse_qs(parsed.query)

            if route in ("/", "/index.html"):
                page = WEB_ROOT / "app.html"
                try:
                    self._send(200, page.read_bytes(), "text/html; charset=utf-8")
                except OSError:
                    self._send(500, b"app.html is missing", "text/plain")
                return

            if route == "/api/status":
                self._json(api.status())
                return

            if route == "/api/library":
                self._json(
                    api.library(
                        query=query.get("q", [""])[0],
                        limit=int(query.get("limit", ["40"])[0] or 40),
                    )
                )
                return

            if route == "/api/entry":
                self._json(api.read_entry(query.get("name", [""])[0]))
                return

            if route == "/api/examples":
                self._json(api.examples())
                return

            if route.startswith("/files/"):
                self._serve_output(route[len("/files/") :])
                return

            self._json({"error": "not found"}, status=404)

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

        def do_POST(self) -> None:  # noqa: N802
            if not self._same_origin():
                self._json({"error": "cross-origin requests are not accepted"}, status=403)
                return

            route = urlparse(self.path).path
            payload = self._body()

            if route == "/api/compile":
                self._json(api.compile(payload))
                return
            if route == "/api/transpose":
                self._json(api.transpose(payload))
                return
            if route == "/api/agent":
                self._json(api.agent(payload))
                return

            self._json({"error": "not found"}, status=404)

        def _serve_output(self, name: str) -> None:
            """Serve a rendered file, and only from the output directory."""
            safe = Path(name).name  # no traversal
            target = (config.paths.output_dir / safe).resolve()
            if config.paths.output_dir.resolve() not in target.parents or not target.is_file():
                self._json({"error": "not found"}, status=404)
                return
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self._send(
                200,
                target.read_bytes(),
                content_type,
                {"Cache-Control": "no-store", "Content-Disposition": f'inline; filename="{safe}"'},
            )

    return Handler


def serve(
    config: Config | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    out=None,
) -> int:
    """Run the web interface until interrupted."""
    config = config or load_config()
    config.paths.ensure_runtime()
    handler = build_handler(config)

    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        message = f"could not bind {host}:{port}: {exc}"
        if out:
            out.fail(message)
            out.dim("try a different port with --port")
        else:
            print(message)
        return 1

    url = f"http://{host}:{server.server_port}"
    if out:
        out.head("tapscript web")
        out.say(f"  {url}")
        out.dim(f"  workspace {config.paths.workspace}")
        if host not in ("127.0.0.1", "localhost", "::1"):
            out.warn("bound to a non-loopback address -- anyone who can reach this port can use it")
        out.say()
        out.dim("  ctrl-c to stop")
    else:
        print(url)

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if out:
            out.say()
            out.dim("stopped")
    finally:
        server.server_close()
    return 0
