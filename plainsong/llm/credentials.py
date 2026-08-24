"""API key resolution and storage.

Lookup order for a provider's key:

1. A key passed in directly by the caller.
2. Any environment variable the catalogue lists for that provider.
3. ``credentials.toml`` in the config directory, written by ``plainsong setup``.

Keys are never written into ``config.toml`` -- that file is meant to be
shareable and is often committed. The credentials file is separate and is
created with owner-only permissions.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..runtime.config import dumps_toml
from ..runtime.paths import Paths, default_paths
from .catalog import ProviderInfo

try:  # tomllib arrived in the standard library in 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - the 3.10 path
    from ..runtime import _toml as tomllib


def _read_store(paths: Paths) -> dict[str, str]:
    path = paths.secrets_file
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    keys = data.get("keys", {})
    return {str(k): str(v) for k, v in keys.items() if isinstance(v, str)}


def resolve_key(info: ProviderInfo, explicit: str = "", paths: Paths | None = None) -> str:
    """Find the API key for a provider, or return an empty string."""
    if explicit:
        return explicit.strip()
    for name in info.env:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    stored = _read_store(paths or default_paths())
    return stored.get(info.id, "").strip()


def key_source(info: ProviderInfo, paths: Paths | None = None) -> str:
    """Where the key came from, for display. Empty when there is none."""
    for name in info.env:
        if os.environ.get(name, "").strip():
            return f"environment ({name})"
    paths = paths or default_paths()
    if _read_store(paths).get(info.id, "").strip():
        return f"stored ({paths.secrets_file})"
    return ""


def store_key(provider_id: str, api_key: str, paths: Paths | None = None) -> Path:
    """Save a key to the credentials file, replacing any previous value."""
    paths = paths or default_paths()
    store = _read_store(paths)
    store[provider_id] = api_key.strip()
    target = paths.secrets_file
    target.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# plainsong credentials\n"
        "# Written by `plainsong setup`. Keep this file out of version control.\n"
        "# Environment variables take precedence over anything stored here.\n\n"
    )
    target.write_text(header + dumps_toml({"keys": store}), encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target


def forget_key(provider_id: str, paths: Paths | None = None) -> bool:
    """Remove a stored key. Returns whether one was there."""
    paths = paths or default_paths()
    store = _read_store(paths)
    if provider_id not in store:
        return False
    del store[provider_id]
    paths.secrets_file.write_text(
        "# plainsong credentials\n\n" + dumps_toml({"keys": store}), encoding="utf-8"
    )
    return True


def mask(api_key: str) -> str:
    """Show enough of a key to recognise it, not enough to use it."""
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}...{api_key[-4:]}"
