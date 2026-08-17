"""Layered configuration.

Precedence, lowest to highest:

    built-in defaults  ->  user config file  ->  project config file
    ->  environment variables  ->  command-line flags

TOML is read with the standard library (``tomllib``, Python 3.11+). Writing uses
a small emitter in this module rather than a third-party dependency, so the
package keeps a zero-install footprint.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import Paths, default_paths

try:  # tomllib arrived in the standard library in 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - the 3.10 path
    from . import _toml as tomllib


DEFAULTS: dict[str, Any] = {
    "core": {
        "dialect": "auto",
        "bar_fill": "rescale",
        "voicing": "guide",
        "lyrics": "independent",
        "default_tempo": 100,
        "default_key": "C",
        "default_meter": "4/4",
    },
    "render": {
        "sample_rate": 44100,
        "ticks_per_beat": 480,
        "humanize": True,
        "humanize_seed": 42,
        "humanize_velocity": 6,
        "swing": 0,
        "audio_backend": "auto",
        "normalize": 0.89,
    },
    "llm": {
        "provider": "",
        "model": "",
        "temperature": 0.7,
        "max_tokens": 4096,
        "timeout": 120,
        "max_retries": 3,
    },
    "agent": {
        "max_steps": 24,
        "auto_approve": False,
        "workspace_only": True,
        "transcript": True,
    },
    "web": {
        "host": "127.0.0.1",
        "port": 8765,
        "open_browser": False,
    },
}

# Environment overrides: PLAINSONG_<SECTION>_<KEY>, plus a few friendly aliases.
ENV_ALIASES = {
    "PLAINSONG_PROVIDER": ("llm", "provider"),
    "PLAINSONG_MODEL": ("llm", "model"),
    "PLAINSONG_PORT": ("web", "port"),
    "PLAINSONG_HOST": ("web", "host"),
}


def _coerce(value: str, reference: Any) -> Any:
    """Coerce an environment string to the type of the default it overrides."""
    if isinstance(reference, bool):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(reference, int):
        try:
            return int(value)
        except ValueError:
            return reference
    if isinstance(reference, float):
        try:
            return float(value)
        except ValueError:
            return reference
    return value


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge *overlay* onto *base*, copying nested dicts rather than aliasing.

    The copy matters: without it a merge of the built-in defaults would hand out
    the module-level dictionaries themselves, and the first ``config.set`` would
    rewrite the defaults for the rest of the process.
    """
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict):
            out[key] = _deep_merge(out[key] if isinstance(out.get(key), dict) else {}, value)
        else:
            out[key] = value
    return out


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"{path}: {exc}") from exc


class ConfigError(Exception):
    """Raised when a configuration file cannot be read or is invalid."""


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def dumps_toml(data: dict[str, Any]) -> str:
    """Emit a flat two-level mapping as TOML. Sufficient for our config shape."""
    lines: list[str] = []
    scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
    for key, value in scalars.items():
        lines.append(f"{key} = {_toml_value(value)}")
    if scalars:
        lines.append("")
    for section, values in data.items():
        if not isinstance(values, dict):
            continue
        lines.append(f"[{section}]")
        for key, value in values.items():
            if isinstance(value, dict):
                continue
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


@dataclass
class Config:
    """Resolved settings plus the provenance of where they came from."""

    data: dict[str, Any] = field(default_factory=dict)
    paths: Paths = field(default_factory=default_paths)
    sources: list[str] = field(default_factory=list)

    def get(self, section: str, key: str, fallback: Any = None) -> Any:
        return self.data.get(section, {}).get(key, fallback)

    def set(self, section: str, key: str, value: Any) -> None:
        self.data.setdefault(section, {})[key] = value

    def section(self, name: str) -> dict[str, Any]:
        return dict(self.data.get(name, {}))

    def save(self, path: Path | None = None) -> Path:
        """Persist the current settings, minus anything equal to the default."""
        target = path or self.paths.config_file
        target.parent.mkdir(parents=True, exist_ok=True)
        diff: dict[str, Any] = {}
        for section, values in self.data.items():
            defaults = DEFAULTS.get(section, {})
            changed = {k: v for k, v in values.items() if defaults.get(k) != v}
            if changed:
                diff[section] = changed
        header = (
            "# plainsong configuration\n"
            "# Values omitted here fall back to the built-in defaults.\n"
            "# See `plainsong config --explain` for the full resolved set.\n\n"
        )
        target.write_text(header + dumps_toml(diff), encoding="utf-8")
        try:
            target.chmod(0o600)
        except OSError:
            pass
        return target


def load_config(overrides: dict[str, Any] | None = None, paths: Paths | None = None) -> Config:
    """Build the effective configuration for this run."""
    paths = paths or default_paths()
    data = _deep_merge({}, DEFAULTS)
    sources = ["defaults"]

    user_file = paths.config_file
    if user_file.exists():
        data = _deep_merge(data, _read_toml(user_file))
        sources.append(str(user_file))

    project_file = paths.project_config_file
    if project_file and project_file.exists():
        data = _deep_merge(data, _read_toml(project_file))
        sources.append(str(project_file))

    env_overlay: dict[str, Any] = {}
    for env_name, (section, key) in ENV_ALIASES.items():
        if env_name in os.environ:
            reference = DEFAULTS.get(section, {}).get(key, "")
            env_overlay.setdefault(section, {})[key] = _coerce(os.environ[env_name], reference)
    for section, values in DEFAULTS.items():
        for key, reference in values.items():
            env_name = f"PLAINSONG_{section.upper()}_{key.upper()}"
            if env_name in os.environ:
                env_overlay.setdefault(section, {})[key] = _coerce(os.environ[env_name], reference)
    if env_overlay:
        data = _deep_merge(data, env_overlay)
        sources.append("environment")

    if overrides:
        cleaned = {
            section: {k: v for k, v in values.items() if v is not None}
            for section, values in overrides.items()
        }
        cleaned = {k: v for k, v in cleaned.items() if v}
        if cleaned:
            data = _deep_merge(data, cleaned)
            sources.append("flags")

    return Config(data=data, paths=paths, sources=sources)
