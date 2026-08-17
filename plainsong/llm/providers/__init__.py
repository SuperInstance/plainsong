"""Provider adapters, one per API shape."""

from .anthropic import AnthropicProvider
from .echo import EchoProvider
from .gemini import GeminiProvider
from .host import HostProvider
from .openai_compat import OpenAICompatibleProvider

# API shape -> adapter. The catalogue names a shape; this maps it to code.
ADAPTERS = {
    "openai": OpenAICompatibleProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "host": HostProvider,
    "echo": EchoProvider,
}

__all__ = [
    "ADAPTERS",
    "AnthropicProvider",
    "EchoProvider",
    "GeminiProvider",
    "HostProvider",
    "OpenAICompatibleProvider",
]
