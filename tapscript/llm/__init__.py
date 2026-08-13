"""Model access, independent of who provides the model."""

from .base import Provider
from .catalog import ProviderInfo, load_catalog, provider_ids
from .credentials import forget_key, mask, resolve_key, store_key
from .registry import ProviderStatus, auto_select, build_provider, get_provider, provider_status
from .types import (
    CompletionRequest,
    CompletionResponse,
    Delta,
    Message,
    ProviderError,
    ToolCall,
    ToolSpec,
    Usage,
)

__all__ = [
    "CompletionRequest",
    "CompletionResponse",
    "Delta",
    "Message",
    "Provider",
    "ProviderError",
    "ProviderInfo",
    "ProviderStatus",
    "ToolCall",
    "ToolSpec",
    "Usage",
    "auto_select",
    "build_provider",
    "forget_key",
    "get_provider",
    "load_catalog",
    "mask",
    "provider_ids",
    "provider_status",
    "resolve_key",
    "store_key",
]
