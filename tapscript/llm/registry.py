"""Building a provider from configuration.

``get_provider(config)`` is the only function most callers need. It works out
which provider to use, finds its key, and hands back something that satisfies
:class:`~tapscript.llm.base.Provider`.

Selection order when nothing is configured:

1. ``--provider`` on the command line, or ``llm.provider`` in the config.
2. A provider whose key is already in the environment.
3. The host agent, if we appear to be running inside one.
4. A local server (Ollama, LM Studio) that is actually answering.
5. The offline stub, so nothing ever hard-fails for want of a model.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from ..runtime.capabilities import CapabilityReport, probe
from ..runtime.config import Config, load_config
from ..runtime.paths import Paths
from .base import Provider
from .catalog import ProviderInfo, load_catalog
from .credentials import key_source, mask, resolve_key
from .providers import ADAPTERS
from .types import ProviderError

AUTO_ORDER = ("anthropic", "openai", "deepseek", "openrouter", "xai", "gemini", "groq", "mistral")
LOCAL_ORDER = ("ollama", "lmstudio", "vllm")


@dataclass
class ProviderStatus:
    """What we know about one provider without calling it."""

    info: ProviderInfo
    configured: bool
    source: str = ""
    masked_key: str = ""
    reachable: bool | None = None

    def as_dict(self) -> dict:
        return {
            **self.info.as_dict(),
            "configured": self.configured,
            "source": self.source,
            "key": self.masked_key,
            "reachable": self.reachable,
        }


def _port_open(url: str, timeout: float = 0.35) -> bool:
    """Is something listening? Used to spot a local model server."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def provider_status(paths: Paths | None = None, probe_local: bool = False) -> list[ProviderStatus]:
    """Report every catalogue entry and whether it is ready to use."""
    catalog = load_catalog(paths)
    statuses: list[ProviderStatus] = []
    for info in catalog.values():
        key = resolve_key(info, paths=paths)
        configured = bool(key) or info.api_key_optional or not info.needs_key
        status = ProviderStatus(
            info=info,
            configured=configured,
            source=key_source(info, paths) if key else ("no key required" if configured else ""),
            masked_key=mask(key),
        )
        if probe_local and info.local and info.base_url:
            status.reachable = _port_open(info.base_url)
        statuses.append(status)
    return sorted(statuses, key=lambda status: (not status.configured, status.info.id))


def auto_select(paths: Paths | None = None, report: CapabilityReport | None = None) -> str:
    """Pick a provider without asking the user anything."""
    catalog = load_catalog(paths)
    report = report or probe()

    for provider_id in AUTO_ORDER:
        info = catalog.get(provider_id)
        if info and resolve_key(info, paths=paths):
            return provider_id

    if report.has("host_agent"):
        return "host"

    for provider_id in LOCAL_ORDER:
        info = catalog.get(provider_id)
        if info and info.base_url and _port_open(info.base_url):
            return provider_id

    return "echo"


def build_provider(
    provider_id: str,
    model: str = "",
    api_key: str = "",
    paths: Paths | None = None,
    **options,
) -> Provider:
    """Instantiate one provider by id."""
    catalog = load_catalog(paths)
    info = catalog.get(provider_id.strip().lower())
    if info is None:
        known = ", ".join(sorted(catalog))
        raise ProviderError(
            f"unknown provider {provider_id!r}",
            hint=f"available: {known}\nadd your own in <config-dir>/providers.json",
        )

    adapter = ADAPTERS.get(info.api)
    if adapter is None:
        raise ProviderError(
            f"provider {info.id!r} needs an API shape this build does not have: {info.api!r}",
            hint=f"supported shapes: {', '.join(sorted(ADAPTERS))}",
        )

    key = resolve_key(info, api_key, paths)
    if info.needs_key and not key:
        env_names = " or ".join(info.env) or "an API key"
        raise ProviderError(
            f"no API key for {info.label}",
            provider=info.id,
            hint=(
                f"set {env_names}, or run `tapscript setup`."
                + (f"\nkeys: {info.docs}" if info.docs else "")
            ),
        )
    if info.needs_base_url and not (options.get("base_url") or info.base_url):
        raise ProviderError(
            f"{info.label} needs a base URL",
            provider=info.id,
            hint="set it with `tapscript config set llm.base_url https://...`",
        )

    return adapter(info, api_key=key, model=model or info.default_model, paths=paths, **options)


def get_provider(
    config: Config | None = None,
    provider_id: str = "",
    model: str = "",
    report: CapabilityReport | None = None,
) -> Provider:
    """Build the provider this run should use."""
    config = config or load_config()
    paths = config.paths
    chosen = (provider_id or config.get("llm", "provider", "")).strip()
    if not chosen or chosen == "auto":
        chosen = auto_select(paths, report)

    options = {
        "timeout": int(config.get("llm", "timeout", 120)),
        "max_retries": int(config.get("llm", "max_retries", 3)),
    }
    for key in ("base_url", "host_command", "host_mode", "host_timeout"):
        value = config.get("llm", key, "")
        if value:
            options[key] = value

    return build_provider(
        chosen,
        model=model or config.get("llm", "model", ""),
        paths=paths,
        **options,
    )
