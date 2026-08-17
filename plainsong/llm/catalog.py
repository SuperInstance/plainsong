"""The provider catalogue.

Providers are data. A service that speaks an API shape we already support --
and most do speak OpenAI's -- is added by dropping an entry into
``<config-dir>/providers.json``, with no code change and no release.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..runtime.paths import Paths, default_paths

BUILTIN_CATALOG = Path(__file__).with_name("catalog.json")


@dataclass
class ProviderInfo:
    """One entry in the catalogue."""

    id: str
    label: str
    api: str = "openai"
    base_url: str = ""
    env: list[str] = field(default_factory=list)
    default_model: str = ""
    models: list[str] = field(default_factory=list)
    docs: str = ""
    tools: bool = True
    streaming: bool = True
    local: bool = False
    api_key_optional: bool = False
    needs_base_url: bool = False
    auth_header: str = "Authorization"
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)

    @property
    def needs_key(self) -> bool:
        return bool(self.env) and not self.api_key_optional

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "api": self.api,
            "base_url": self.base_url,
            "env": list(self.env),
            "default_model": self.default_model,
            "models": list(self.models),
            "docs": self.docs,
            "local": self.local,
            "needs_key": self.needs_key,
        }


def _from_dict(provider_id: str, data: dict[str, Any]) -> ProviderInfo:
    return ProviderInfo(
        id=provider_id,
        label=data.get("label", provider_id),
        api=data.get("api", "openai"),
        base_url=data.get("base_url", ""),
        env=list(data.get("env", [])),
        default_model=data.get("default_model", ""),
        models=list(data.get("models", [])),
        docs=data.get("docs", ""),
        tools=bool(data.get("tools", True)),
        streaming=bool(data.get("streaming", True)),
        local=bool(data.get("local", False)),
        api_key_optional=bool(data.get("api_key_optional", False)),
        needs_base_url=bool(data.get("needs_base_url", False)),
        auth_header=data.get("auth_header", "Authorization"),
        headers=dict(data.get("headers", {})),
        query_params=dict(data.get("query_params", {})),
    )


def load_catalog(paths: Paths | None = None) -> dict[str, ProviderInfo]:
    """Built-in providers, plus any the user has added."""
    paths = paths or default_paths()
    catalog: dict[str, ProviderInfo] = {}

    with BUILTIN_CATALOG.open("r", encoding="utf-8") as handle:
        builtin = json.load(handle)
    for provider_id, data in builtin.get("providers", {}).items():
        catalog[provider_id] = _from_dict(provider_id, data)

    for extra_path in (paths.config_dir / "providers.json", Path.cwd() / "providers.json"):
        if not extra_path.exists():
            continue
        try:
            with extra_path.open("r", encoding="utf-8") as handle:
                extra = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        entries = extra.get("providers", extra)
        if not isinstance(entries, dict):
            continue
        for provider_id, data in entries.items():
            if isinstance(data, dict):
                catalog[provider_id] = _from_dict(provider_id, data)

    return catalog


def get_provider_info(provider_id: str, paths: Paths | None = None) -> ProviderInfo | None:
    return load_catalog(paths).get(provider_id.strip().lower())


def provider_ids(paths: Paths | None = None) -> list[str]:
    return sorted(load_catalog(paths))
