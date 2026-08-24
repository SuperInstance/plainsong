"""Provider-neutral message types.

Every provider adapter converts to and from these. Nothing above this layer
knows whether it is talking to a hosted API, a model on localhost, or the agent
that launched us.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ToolCall:
    """A model's request to run one tool."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "arguments": self.arguments}


@dataclass
class Message:
    """One turn of a conversation."""

    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str = ""
    name: str = ""

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str = "", tool_calls: list[ToolCall] | None = None) -> Message:
        return cls(role="assistant", content=content, tool_calls=tool_calls or [])

    @classmethod
    def tool(cls, tool_call_id: str, content: str, name: str = "") -> Message:
        return cls(role="tool", content=content, tool_call_id=tool_call_id, name=name)

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            data["tool_calls"] = [call.as_dict() for call in self.tool_calls]
        if self.tool_call_id:
            data["tool_call_id"] = self.tool_call_id
        if self.name:
            data["name"] = self.name
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", "") or "",
            tool_calls=[
                ToolCall(
                    id=call.get("id", ""), name=call.get("name", ""), arguments=call.get("arguments", {})
                )
                for call in data.get("tool_calls", [])
            ],
            tool_call_id=data.get("tool_call_id", ""),
            name=data.get("name", ""),
        )


@dataclass
class ToolSpec:
    """A tool offered to the model, described in JSON Schema."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})

    def as_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def as_anthropic(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def as_gemini(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": _strip_unsupported(self.parameters),
        }


def _strip_unsupported(schema: dict[str, Any]) -> dict[str, Any]:
    """Gemini rejects several JSON Schema keywords. Drop them."""
    unsupported = {"additionalProperties", "$schema", "default", "examples", "title"}
    cleaned: dict[str, Any] = {}
    for key, value in schema.items():
        if key in unsupported:
            continue
        if isinstance(value, dict):
            cleaned[key] = _strip_unsupported(value)
        elif isinstance(value, list):
            cleaned[key] = [_strip_unsupported(item) if isinstance(item, dict) else item for item in value]
        else:
            cleaned[key] = value
    return cleaned


@dataclass
class Usage:
    """Token accounting, when the provider reports it."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: Usage) -> Usage:
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens)


@dataclass
class CompletionRequest:
    """What we ask a model for."""

    messages: list[Message]
    model: str = ""
    tools: list[ToolSpec] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 4096
    stop: list[str] = field(default_factory=list)
    json_mode: bool = False
    stream: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionResponse:
    """What a model gave back."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    usage: Usage = field(default_factory=Usage)
    finish_reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def message(self) -> Message:
        return Message.assistant(self.text, self.tool_calls)

    def json(self) -> Any:
        """Parse the reply as JSON, tolerating fenced code blocks."""
        text = self.text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 2:
                text = "\n".join(lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end > start:
                return json.loads(text[start : end + 1])
            raise


@dataclass
class Delta:
    """One streamed fragment."""

    text: str = ""
    done: bool = False


StreamIterator = Iterator[Delta]


class ProviderError(RuntimeError):
    """A provider could not fulfil a request.

    Carries enough context for the CLI to print something a user can act on --
    which provider, whether it is worth retrying, and the underlying message.
    """

    def __init__(
        self,
        message: str,
        provider: str = "",
        status: int = 0,
        retryable: bool = False,
        hint: str = "",
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status = status
        self.retryable = retryable
        self.hint = hint

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.provider:
            parts[0] = f"[{self.provider}] {parts[0]}"
        if self.hint:
            parts.append(f"hint: {self.hint}")
        return "\n".join(parts)
