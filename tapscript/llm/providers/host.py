"""Borrow the model from whatever agent is already running.

When someone drives this project from Claude Code, openclaw, Cursor or a
similar tool, there is already a capable model in the room and it already has
credentials. Making the user paste a second API key to reach a second model is
a worse experience than asking the one in front of them.

Three ways to reach a host, in order of how well they tend to work:

``command``
    Run a subprocess. The prompt goes in on stdin, the reply comes back on
    stdout. Works with any agent that has a headless mode::

        tapscript config set llm.host_command "claude -p"
        tapscript config set llm.host_command "openclaw run --quiet"
        tapscript config set llm.host_command "ollama run llama3.2"

``file``
    Write the request as JSON into the bridge directory and wait for the host
    to write the answer next to it. Works with any agent that can read and
    write files, which is all of them. The protocol is in
    ``docs/host-bridge.md``.

``stdio``
    Emit one JSON line on stdout between sentinels and read one JSON line back
    from stdin. For hosts that pipe us directly.

Tool calling is expressed as a small JSON protocol, since a host agent replies
in text rather than in a provider's function-calling format.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from ...runtime.paths import default_paths
from ..base import Provider
from ..types import (
    CompletionRequest,
    CompletionResponse,
    Message,
    ProviderError,
    ToolCall,
    Usage,
)

REQUEST_SENTINEL = "<<<TAPSCRIPT_BRIDGE_REQUEST>>>"
RESPONSE_SENTINEL = "<<<TAPSCRIPT_BRIDGE_RESPONSE>>>"

TOOL_PROTOCOL = """
When you want to use one of the listed tools, reply with a JSON object and
nothing else:

    {"tool": "<tool name>", "arguments": {...}}

When you are answering rather than calling a tool, reply with:

    {"text": "<your answer>"}

Plain prose is accepted too and is treated as the text form.
""".strip()


def _render_prompt(request: CompletionRequest) -> str:
    """Flatten a conversation into a single prompt a host agent can act on."""
    blocks: list[str] = []
    for message in request.messages:
        if message.role == "system":
            blocks.append(f"# Instructions\n{message.content}")
        elif message.role == "user":
            blocks.append(f"# User\n{message.content}")
        elif message.role == "assistant":
            if message.content:
                blocks.append(f"# Assistant\n{message.content}")
            for call in message.tool_calls:
                blocks.append(
                    f"# Assistant tool call\n{json.dumps({'tool': call.name, 'arguments': call.arguments})}"
                )
        elif message.role == "tool":
            blocks.append(f"# Tool result ({message.name or message.tool_call_id})\n{message.content}")

    if request.tools:
        catalogue = "\n".join(
            f"- {tool.name}: {tool.description}\n  parameters: {json.dumps(tool.parameters)}"
            for tool in request.tools
        )
        blocks.append(f"# Available tools\n{catalogue}\n\n{TOOL_PROTOCOL}")

    return "\n\n".join(blocks)


def _parse_reply(text: str) -> tuple[str, list[ToolCall]]:
    """Read a host reply, which may be a tool call, JSON text, or prose."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            if lines[-1].strip().startswith("```"):
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            stripped = "\n".join(lines).strip()

    candidate = stripped
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end > start:
            candidate = candidate[start : end + 1]

    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return stripped, []

    if not isinstance(data, dict):
        return stripped, []
    if "tool" in data:
        arguments = data.get("arguments")
        return "", [
            ToolCall(
                id=f"host-{uuid.uuid4().hex[:8]}",
                name=str(data["tool"]),
                arguments=arguments if isinstance(arguments, dict) else {},
            )
        ]
    if "text" in data:
        return str(data["text"]), []
    return stripped, []


class HostProvider(Provider):
    """A model reached through the surrounding agent rather than an API."""

    def __init__(self, info, api_key: str = "", model: str = "", **options) -> None:
        super().__init__(info, api_key, model, **options)
        self.mode = str(options.get("host_mode") or os.environ.get("TAPSCRIPT_HOST_MODE") or "command")
        self.command = str(options.get("host_command") or os.environ.get("TAPSCRIPT_HOST_COMMAND") or "")
        self.poll_timeout = int(options.get("host_timeout", 900))
        self.bridge_dir = Path(options.get("bridge_dir") or default_paths().bridge_dir)
        if not self.command and self.mode == "command":
            # Without a command configured, the file handshake is the only
            # mode that can work unattended.
            self.mode = "file"

    def describe(self) -> str:
        if self.mode == "command":
            return f"host agent via `{self.command}`"
        return f"host agent via {self.mode} bridge ({self.bridge_dir})"

    # -- modes ---------------------------------------------------------------

    def _run_command(self, prompt: str) -> str:
        argv = shlex.split(self.command)
        if not argv:
            raise ProviderError(
                "no host command configured",
                provider=self.id,
                hint='set one with `tapscript config set llm.host_command "claude -p"`',
            )
        try:
            completed = subprocess.run(
                argv,
                input=prompt.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.poll_timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProviderError(
                f"host command not found: {argv[0]}",
                provider=self.id,
                hint="check `tapscript config get llm.host_command`",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(
                f"host command timed out after {self.poll_timeout}s", provider=self.id, retryable=True
            ) from exc

        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", "replace").strip()
            raise ProviderError(
                f"host command exited {completed.returncode}: {detail[:300]}", provider=self.id
            )
        return completed.stdout.decode("utf-8", "replace")

    def _run_file(self, prompt: str, request: CompletionRequest) -> str:
        requests_dir = self.bridge_dir / "requests"
        responses_dir = self.bridge_dir / "responses"
        requests_dir.mkdir(parents=True, exist_ok=True)
        responses_dir.mkdir(parents=True, exist_ok=True)

        request_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
        payload = {
            "id": request_id,
            "created": time.time(),
            "prompt": prompt,
            "messages": [message.as_dict() for message in request.messages],
            "tools": [
                {"name": tool.name, "description": tool.description, "parameters": tool.parameters}
                for tool in request.tools
            ],
            "protocol": "tapscript.bridge/1",
        }
        request_path = requests_dir / f"{request_id}.json"
        request_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        response_path = responses_dir / f"{request_id}.json"
        deadline = time.time() + self.poll_timeout
        while time.time() < deadline:
            if response_path.exists():
                try:
                    data = json.loads(response_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    time.sleep(0.2)
                    continue
                request_path.unlink(missing_ok=True)
                response_path.unlink(missing_ok=True)
                if isinstance(data, dict):
                    if data.get("error"):
                        raise ProviderError(str(data["error"]), provider=self.id)
                    return str(data.get("text", data.get("content", "")))
                return str(data)
            time.sleep(0.25)

        request_path.unlink(missing_ok=True)
        raise ProviderError(
            f"no reply from the host agent within {self.poll_timeout}s",
            provider=self.id,
            hint=f"the host should answer requests in {self.bridge_dir} -- see docs/host-bridge.md",
        )

    def _run_stdio(self, prompt: str, request: CompletionRequest) -> str:
        import sys

        payload = {
            "prompt": prompt,
            "tools": [tool.name for tool in request.tools],
            "protocol": "tapscript.bridge/1",
        }
        sys.stdout.write(f"\n{REQUEST_SENTINEL}\n{json.dumps(payload)}\n{REQUEST_SENTINEL}\n")
        sys.stdout.flush()

        collected: list[str] = []
        inside = False
        for line in sys.stdin:
            stripped = line.strip()
            if stripped == RESPONSE_SENTINEL:
                if inside:
                    break
                inside = True
                continue
            if inside:
                collected.append(line)
        raw = "".join(collected).strip()
        if not raw:
            raise ProviderError("no reply on stdin", provider=self.id)
        try:
            data = json.loads(raw)
            return str(data.get("text", raw)) if isinstance(data, dict) else raw
        except json.JSONDecodeError:
            return raw

    # -- provider interface --------------------------------------------------

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        prompt = _render_prompt(request)
        if self.mode == "command":
            raw = self._run_command(prompt)
        elif self.mode == "stdio":
            raw = self._run_stdio(prompt, request)
        else:
            raw = self._run_file(prompt, request)

        text, tool_calls = _parse_reply(raw)
        return CompletionResponse(
            text=text,
            tool_calls=tool_calls,
            model=f"host:{self.mode}",
            provider=self.id,
            usage=Usage(),
            finish_reason="tool_calls" if tool_calls else "stop",
            raw={"reply": raw},
        )

    def check(self) -> tuple[bool, str]:
        if self.mode == "command" and not self.command:
            return False, 'no host command set (`tapscript config set llm.host_command "claude -p"`)'
        if self.mode == "file":
            return True, f"file bridge ready at {self.bridge_dir}"
        return super().check()


def write_bridge_response(bridge_dir: Path, request_id: str, text: str) -> Path:
    """Helper for host agents answering a file-bridge request."""
    responses = Path(bridge_dir) / "responses"
    responses.mkdir(parents=True, exist_ok=True)
    target = responses / f"{request_id}.json"
    target.write_text(json.dumps({"id": request_id, "text": text}), encoding="utf-8")
    return target


def pending_bridge_requests(bridge_dir: Path) -> list[dict[str, Any]]:
    """Helper for host agents polling the file bridge."""
    requests_dir = Path(bridge_dir) / "requests"
    if not requests_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(requests_dir.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out
