"""Adapter for the Anthropic messages API.

Differences from the OpenAI shape that this handles: the system prompt is a
top-level field rather than a message, content is a list of typed blocks, tool
results are user-role blocks, and ``max_tokens`` is required.
"""

from __future__ import annotations

from typing import Any, Iterator

from ..base import Provider
from ..transport import request_json, request_stream
from ..types import (
    CompletionRequest,
    CompletionResponse,
    Delta,
    Message,
    ProviderError,
    ToolCall,
    Usage,
)

API_VERSION = "2023-06-01"


class AnthropicProvider(Provider):
    """Claude models."""

    def _headers(self) -> dict[str, str]:
        headers = {"anthropic-version": API_VERSION, **self.info.headers}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _convert(self, messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []

        for message in messages:
            if message.role == "system":
                if message.content:
                    system_parts.append(message.content)
                continue

            if message.role == "tool":
                block = {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id,
                    "content": message.content,
                }
                # Consecutive tool results belong in one user turn.
                if converted and converted[-1]["role"] == "user" and isinstance(converted[-1]["content"], list):
                    existing = converted[-1]["content"]
                    if existing and existing[0].get("type") == "tool_result":
                        existing.append(block)
                        continue
                converted.append({"role": "user", "content": [block]})
                continue

            if message.role == "assistant":
                blocks: list[dict[str, Any]] = []
                if message.content:
                    blocks.append({"type": "text", "text": message.content})
                for call in message.tool_calls:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": call.id,
                            "name": call.name,
                            "input": call.arguments,
                        }
                    )
                if blocks:
                    converted.append({"role": "assistant", "content": blocks})
                continue

            converted.append({"role": "user", "content": message.content})

        return "\n\n".join(system_parts), converted

    def _payload(self, request: CompletionRequest) -> dict[str, Any]:
        system, messages = self._convert(request.messages)
        payload: dict[str, Any] = {
            "model": request.model or self.model,
            "messages": messages or [{"role": "user", "content": "(no input)"}],
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature,
        }
        if system:
            payload["system"] = system
        if request.stop:
            payload["stop_sequences"] = request.stop
        if request.tools and self.supports_tools:
            payload["tools"] = [tool.as_anthropic() for tool in request.tools]
        payload.update(request.extra)
        return payload

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        data = request_json(
            f"{self.base_url}/messages",
            payload=self._payload(request),
            headers=self._headers(),
            timeout=self.timeout,
            max_retries=self.max_retries,
            provider=self.id,
        )
        if data.get("type") == "error":
            raise ProviderError(str(data.get("error", {}).get("message", "unknown error")), provider=self.id)

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in data.get("content") or []:
            kind = block.get("type")
            if kind == "text":
                text_parts.append(block.get("text", ""))
            elif kind == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        arguments=block.get("input") or {},
                    )
                )

        usage_data = data.get("usage") or {}
        return CompletionResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            model=data.get("model", request.model or self.model),
            provider=self.id,
            usage=Usage(
                input_tokens=int(usage_data.get("input_tokens", 0) or 0),
                output_tokens=int(usage_data.get("output_tokens", 0) or 0),
            ),
            finish_reason=data.get("stop_reason", ""),
            raw=data,
        )

    def stream(self, request: CompletionRequest) -> Iterator[Delta]:
        payload = self._payload(request)
        payload["stream"] = True
        for event in request_stream(
            f"{self.base_url}/messages",
            payload=payload,
            headers=self._headers(),
            timeout=max(self.timeout, 300),
            provider=self.id,
        ):
            if event.get("type") == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") == "text_delta":
                    yield Delta(text=delta.get("text", ""))
            elif event.get("type") == "message_stop":
                break
        yield Delta(done=True)
