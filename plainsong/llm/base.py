"""The provider interface.

Four methods, one shape. Adapters translate to whatever the service expects and
translate the answer back. Everything above this layer -- the agent kernel, the
interfaces -- is written against this and nothing else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from .catalog import ProviderInfo
from .types import CompletionRequest, CompletionResponse, Delta, Message, ProviderError


class Provider(ABC):
    """A model endpoint."""

    def __init__(self, info: ProviderInfo, api_key: str = "", model: str = "", **options) -> None:
        self.info = info
        self.api_key = api_key
        self.model = model or info.default_model
        self.base_url = (options.get("base_url") or info.base_url).rstrip("/")
        self.timeout = int(options.get("timeout", 120))
        self.max_retries = int(options.get("max_retries", 3))
        self.options = options

    @property
    def id(self) -> str:
        return self.info.id

    @property
    def label(self) -> str:
        return self.info.label

    @property
    def supports_tools(self) -> bool:
        return self.info.tools

    @property
    def supports_streaming(self) -> bool:
        return self.info.streaming

    @abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Send a request and return the whole reply."""

    def stream(self, request: CompletionRequest) -> Iterator[Delta]:
        """Yield the reply in fragments. Falls back to one whole-reply chunk."""
        response = self.complete(request)
        if response.text:
            yield Delta(text=response.text)
        yield Delta(done=True)

    def check(self) -> tuple[bool, str]:
        """A cheap round trip that proves the credentials and endpoint work."""
        try:
            response = self.complete(
                CompletionRequest(
                    messages=[Message.user("Reply with the single word: ready")],
                    model=self.model,
                    max_tokens=16,
                    temperature=0.0,
                )
            )
        except ProviderError as exc:
            return False, str(exc)
        except Exception as exc:  # an adapter bug should not look like a network failure
            return False, f"{type(exc).__name__}: {exc}"
        text = response.text.strip() or "(empty reply)"
        return True, text[:120]

    def describe(self) -> str:
        return f"{self.label} / {self.model}"
