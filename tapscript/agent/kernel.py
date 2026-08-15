"""The agent loop.

Messages in, tool calls out, until the model stops asking for tools or the step
budget runs out. Interfaces subscribe to events rather than reading stdout, so
the same loop drives the CLI, the TUI and the web interface without change.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..llm.base import Provider
from ..llm.types import (
    CompletionRequest,
    CompletionResponse,
    Message,
    ProviderError,
    ToolCall,
    Usage,
)
from ..runtime.config import Config, load_config
from .tools import ToolRegistry

PROMPTS_DIR = Path(__file__).parent / "prompts"

EventHandler = Callable[["AgentEvent"], None]


@dataclass
class AgentEvent:
    """Something the loop did, for anyone watching."""

    kind: str  # step | message | tool_call | tool_result | error | done
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    step: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "text": self.text, "data": self.data, "step": self.step}


@dataclass
class AgentResult:
    """What one run produced."""

    reply: str = ""
    messages: list[Message] = field(default_factory=list)
    steps: int = 0
    usage: Usage = field(default_factory=Usage)
    tool_calls: list[str] = field(default_factory=list)
    stopped_because: str = "done"
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    def summary(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "steps": self.steps,
            "tools_used": self.tool_calls,
            "tokens": {"in": self.usage.input_tokens, "out": self.usage.output_tokens},
            "stopped_because": self.stopped_because,
            "error": self.error,
        }


def load_prompt(name: str) -> str:
    """Read a prompt template shipped with the package."""
    path = PROMPTS_DIR / f"{name}.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


class Agent:
    """A model, a set of tools, and a loop that runs them."""

    def __init__(
        self,
        provider: Provider,
        tools: ToolRegistry | None = None,
        config: Config | None = None,
        system_prompt: str = "",
        role: str = "composer",
        max_steps: int = 0,
        on_event: EventHandler | None = None,
    ) -> None:
        self.provider = provider
        self.config = config or load_config()
        self.tools = tools if tools is not None else ToolRegistry(config=self.config)
        self.role = role
        self.system_prompt = system_prompt or load_prompt(role) or load_prompt("composer")
        self.max_steps = max_steps or int(self.config.get("agent", "max_steps", 24))
        self.on_event = on_event
        self.messages: list[Message] = []
        self.usage = Usage()
        self.session_id = uuid.uuid4().hex[:12]

    # -- events --------------------------------------------------------------

    def _emit(self, kind: str, text: str = "", step: int = 0, **data: Any) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(AgentEvent(kind=kind, text=text, data=data, step=step))
        except Exception:
            pass  # a broken listener must not stop the run

    # -- conversation --------------------------------------------------------

    def _context_note(self) -> str:
        """Facts the model should not have to ask for."""
        from ..runtime.capabilities import probe

        report = probe()
        available = [capability.name for capability in report if capability.present]
        return (
            "Environment: "
            f"working directory {self.tools.sandbox.root}; "
            f"provider {self.provider.describe()}; "
            f"host capabilities: {', '.join(available)}."
        )

    def reset(self) -> None:
        self.messages = []
        self.usage = Usage()

    def _prepare(self, prompt: str) -> list[Message]:
        if not self.messages:
            self.messages.append(Message.system(f"{self.system_prompt}\n\n{self._context_note()}"))
        self.messages.append(Message.user(prompt))
        return self.messages

    def _complete(self, step: int) -> CompletionResponse:
        request = CompletionRequest(
            # A copy: the loop keeps appending to self.messages while a provider
            # may still be holding the request it was given.
            messages=list(self.messages),
            model=self.provider.model,
            tools=self.tools.specs() if self.provider.supports_tools else [],
            temperature=float(self.config.get("llm", "temperature", 0.7)),
            max_tokens=int(self.config.get("llm", "max_tokens", 4096)),
        )
        return self.provider.complete(request)

    def run(self, prompt: str) -> AgentResult:
        """Run the loop until the model stops calling tools."""
        result = AgentResult()
        self._prepare(prompt)
        started = time.time()

        for step in range(1, self.max_steps + 1):
            result.steps = step
            self._emit("step", f"step {step}", step=step)

            try:
                response = self._complete(step)
            except ProviderError as exc:
                result.error = str(exc)
                result.stopped_because = "provider error"
                self._emit("error", str(exc), step=step)
                return result
            except Exception as exc:  # adapter bugs should surface, not hang
                result.error = f"{type(exc).__name__}: {exc}"
                result.stopped_because = "unexpected error"
                self._emit("error", result.error, step=step)
                return result

            self.usage = self.usage + response.usage
            result.usage = self.usage
            self.messages.append(response.message)

            if response.text:
                self._emit("message", response.text, step=step)

            if not response.tool_calls:
                result.reply = response.text
                result.messages = list(self.messages)
                result.stopped_because = "done"
                self._emit("done", response.text, step=step, elapsed=time.time() - started)
                return result

            for call in response.tool_calls:
                self._run_tool(call, step, result)

        result.reply = self._last_text()
        result.messages = list(self.messages)
        result.stopped_because = f"reached the {self.max_steps} step limit"
        self._emit("done", result.reply, step=result.steps)
        return result

    def _run_tool(self, call: ToolCall, step: int, result: AgentResult) -> None:
        self._emit(
            "tool_call",
            f"{call.name}({json.dumps(call.arguments, default=str)[:160]})",
            step=step,
            tool=call.name,
            arguments=call.arguments,
        )
        output = self.tools.call(call.name, call.arguments)
        result.tool_calls.append(call.name)
        self.messages.append(Message.tool(call.id, output, name=call.name))
        self._emit("tool_result", output[:2000], step=step, tool=call.name)

    def _last_text(self) -> str:
        for message in reversed(self.messages):
            if message.role == "assistant" and message.content:
                return message.content
        return ""

    # -- persistence ---------------------------------------------------------

    def transcript(self) -> list[dict[str, Any]]:
        return [message.as_dict() for message in self.messages]

    def save(self, path: Path | None = None) -> Path:
        """Write the conversation so a later run can pick it up."""
        target = Path(path) if path else self.config.paths.sessions_dir / f"{self.session_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "id": self.session_id,
                    "role": self.role,
                    "provider": self.provider.id,
                    "model": self.provider.model,
                    "created": time.time(),
                    "messages": self.transcript(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return target

    def load(self, path: Path) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.session_id = data.get("id", self.session_id)
        self.messages = [Message.from_dict(item) for item in data.get("messages", [])]


def list_sessions(config: Config | None = None) -> list[dict[str, Any]]:
    """Saved sessions, newest first."""
    config = config or load_config()
    directory = config.paths.sessions_dir
    if not directory.is_dir():
        return []
    sessions: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        first_user = next(
            (m.get("content", "") for m in data.get("messages", []) if m.get("role") == "user"), ""
        )
        sessions.append(
            {
                "id": data.get("id", path.stem),
                "path": str(path),
                "role": data.get("role", ""),
                "provider": data.get("provider", ""),
                "model": data.get("model", ""),
                "created": data.get("created", 0),
                "turns": len(data.get("messages", [])),
                "opening": first_user[:80],
            }
        )
    return sorted(sessions, key=lambda item: item.get("created", 0), reverse=True)


def stream_events(events: Iterable[AgentEvent]) -> str:
    """Render a run's events as plain text. Used by the CLI's verbose mode."""
    lines = []
    for event in events:
        if event.kind == "tool_call":
            lines.append(f"  -> {event.text}")
        elif event.kind == "tool_result":
            first = event.text.splitlines()[0] if event.text else ""
            lines.append(f"     {first}")
        elif event.kind in ("message", "done") and event.text:
            lines.append(event.text)
        elif event.kind == "error":
            lines.append(f"error: {event.text}")
    return "\n".join(lines)
