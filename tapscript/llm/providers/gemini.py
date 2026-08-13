"""Adapter for the Google Gemini generative language API.

Differences this handles: the key travels as a query parameter, turns are
``contents`` with ``parts``, the assistant role is called ``model``, the system
prompt is ``system_instruction``, and tools are wrapped in a
``functionDeclarations`` list.
"""

from __future__ import annotations

import uuid
from typing import Any

from ..base import Provider
from ..transport import request_json
from ..types import (
    CompletionRequest,
    CompletionResponse,
    Message,
    ProviderError,
    ToolCall,
    Usage,
)


class GeminiProvider(Provider):
    """Gemini models."""

    def _convert(self, messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []

        for message in messages:
            if message.role == "system":
                if message.content:
                    system_parts.append(message.content)
                continue

            if message.role == "tool":
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": message.name or message.tool_call_id,
                                    "response": {"result": message.content},
                                }
                            }
                        ],
                    }
                )
                continue

            parts: list[dict[str, Any]] = []
            if message.content:
                parts.append({"text": message.content})
            for call in message.tool_calls:
                parts.append({"functionCall": {"name": call.name, "args": call.arguments}})
            if not parts:
                continue
            contents.append({"role": "model" if message.role == "assistant" else "user", "parts": parts})

        return "\n\n".join(system_parts), contents

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        system, contents = self._convert(request.messages)
        model = request.model or self.model
        payload: dict[str, Any] = {
            "contents": contents or [{"role": "user", "parts": [{"text": "(no input)"}]}],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        if system:
            payload["system_instruction"] = {"parts": [{"text": system}]}
        if request.stop:
            payload["generationConfig"]["stopSequences"] = request.stop
        if request.json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        if request.tools and self.supports_tools:
            payload["tools"] = [{"functionDeclarations": [tool.as_gemini() for tool in request.tools]}]
        payload.update(request.extra)

        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
        data = request_json(
            url,
            payload=payload,
            timeout=self.timeout,
            max_retries=self.max_retries,
            provider=self.id,
        )

        candidates = data.get("candidates") or []
        if not candidates:
            feedback = data.get("promptFeedback") or {}
            reason = feedback.get("blockReason")
            if reason:
                raise ProviderError(f"request blocked: {reason}", provider=self.id)
            raise ProviderError("provider returned no candidates", provider=self.id)

        candidate = candidates[0]
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for part in (candidate.get("content") or {}).get("parts") or []:
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                call = part["functionCall"]
                tool_calls.append(
                    ToolCall(
                        id=f"gemini-{uuid.uuid4().hex[:8]}",
                        name=call.get("name", ""),
                        arguments=call.get("args") or {},
                    )
                )

        usage_data = data.get("usageMetadata") or {}
        return CompletionResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            model=model,
            provider=self.id,
            usage=Usage(
                input_tokens=int(usage_data.get("promptTokenCount", 0) or 0),
                output_tokens=int(usage_data.get("candidatesTokenCount", 0) or 0),
            ),
            finish_reason=candidate.get("finishReason", ""),
            raw=data,
        )
