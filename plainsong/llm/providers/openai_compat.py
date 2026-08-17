"""Adapter for the OpenAI chat-completions shape.

This one adapter covers most of the catalogue: OpenAI, DeepSeek, OpenRouter,
xAI, Groq, Mistral, Together, Fireworks, Cerebras, Ollama, LM Studio, vLLM,
llama.cpp and Azure. They differ in base URL, auth header and model names --
all of which are data in the catalogue, not code here.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlencode

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


class OpenAICompatibleProvider(Provider):
    """Chat completions over the OpenAI wire format."""

    def _headers(self) -> dict[str, str]:
        headers = dict(self.info.headers)
        if self.api_key:
            if self.info.auth_header.lower() == "authorization":
                headers["Authorization"] = f"Bearer {self.api_key}"
            else:
                headers[self.info.auth_header] = self.api_key
        return headers

    def _url(self, path: str) -> str:
        url = f"{self.base_url}{path}"
        if self.info.query_params:
            url += "?" + urlencode(self.info.query_params)
        return url

    def _messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "tool":
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.tool_call_id,
                        "content": message.content,
                    }
                )
                continue
            entry: dict[str, Any] = {"role": message.role, "content": message.content}
            if message.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    }
                    for call in message.tool_calls
                ]
                # The API rejects a null content alongside tool calls.
                entry["content"] = message.content or ""
            out.append(entry)
        return out

    def _payload(self, request: CompletionRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self.model,
            "messages": self._messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.stop:
            payload["stop"] = request.stop
        if request.tools and self.supports_tools:
            payload["tools"] = [tool.as_openai() for tool in request.tools]
            payload["tool_choice"] = "auto"
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        payload.update(request.extra)
        return payload

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        data = request_json(
            self._url("/chat/completions"),
            payload=self._payload(request),
            headers=self._headers(),
            timeout=self.timeout,
            max_retries=self.max_retries,
            provider=self.id,
        )
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("provider returned no choices", provider=self.id)
        choice = choices[0]
        message = choice.get("message") or {}

        tool_calls: list[ToolCall] = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            raw_arguments = function.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except json.JSONDecodeError:
                arguments = {"_raw": raw_arguments}
            tool_calls.append(
                ToolCall(id=call.get("id", ""), name=function.get("name", ""), arguments=arguments or {})
            )

        usage_data = data.get("usage") or {}
        return CompletionResponse(
            text=message.get("content") or "",
            tool_calls=tool_calls,
            model=data.get("model", request.model or self.model),
            provider=self.id,
            usage=Usage(
                input_tokens=int(usage_data.get("prompt_tokens", 0) or 0),
                output_tokens=int(usage_data.get("completion_tokens", 0) or 0),
            ),
            finish_reason=choice.get("finish_reason", ""),
            raw=data,
        )

    def stream(self, request: CompletionRequest) -> Iterator[Delta]:
        if not self.supports_streaming:
            yield from super().stream(request)
            return
        payload = self._payload(request)
        payload["stream"] = True
        for event in request_stream(
            self._url("/chat/completions"),
            payload=payload,
            headers=self._headers(),
            timeout=max(self.timeout, 300),
            provider=self.id,
        ):
            for choice in event.get("choices") or []:
                delta = choice.get("delta") or {}
                text = delta.get("content")
                if text:
                    yield Delta(text=text)
        yield Delta(done=True)
