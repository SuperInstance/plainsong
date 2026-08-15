"""Connectors: the edges of the system.

A connector is a named way of getting something out of TapScript, or into it.
Writing a wav file is one. Playing to a MIDI port is another. So is posting a
render to a webhook, or watching a folder and compiling whatever lands there.

Connectors exist so that adapting this to a particular setup does not mean
editing the compiler. The build agent writes them into
``<workspace>/connectors/`` and they are discovered from there -- a generated
connector is a normal connector, with no special status.

A connector module defines one or more :class:`Connector` subclasses and is
found by name. Nothing is imported until it is asked for.
"""

from __future__ import annotations

import importlib.util
import sys
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..notation.ir import Arrangement
from ..runtime.config import Config, load_config


@dataclass
class ConnectorResult:
    """What a connector did."""

    ok: bool
    detail: str = ""
    outputs: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.ok


class Connector(ABC):
    """One way in or out."""

    name: str = ""
    summary: str = ""
    #: Capability names that must be present for this connector to work.
    requires: tuple[str, ...] = ()

    def __init__(self, config: Config | None = None, **options: Any) -> None:
        self.config = config or load_config()
        self.options = options

    def available(self) -> tuple[bool, str]:
        """Can this connector run on this machine?"""
        from ..runtime.capabilities import probe

        report = probe()
        missing = [name for name in self.requires if not report.has(name)]
        if missing:
            remedies = []
            for name in missing:
                capability = report.get(name)
                if capability and capability.remedy:
                    remedies.append(f"{name}: {capability.remedy}")
            return False, "; ".join(remedies) or f"missing: {', '.join(missing)}"
        return True, "ready"

    @abstractmethod
    def send(self, arrangement: Arrangement, **options: Any) -> ConnectorResult:
        """Do the thing this connector exists to do."""

    def describe(self) -> dict[str, Any]:
        ok, detail = self.available()
        return {
            "name": self.name,
            "summary": self.summary,
            "requires": list(self.requires),
            "available": ok,
            "detail": detail,
        }


class ConnectorRegistry:
    """Everything that can be connected to, built in or generated."""

    def __init__(self) -> None:
        self._classes: dict[str, type[Connector]] = {}
        self._loaded_paths: set[Path] = set()

    def register(self, connector: type[Connector]) -> type[Connector]:
        """Register a connector class. Usable as a decorator."""
        if not connector.name:
            raise ValueError(f"{connector.__name__} needs a name")
        self._classes[connector.name] = connector
        return connector

    def names(self) -> list[str]:
        return sorted(self._classes)

    def get(self, name: str) -> type[Connector] | None:
        return self._classes.get(name)

    def create(self, name: str, config: Config | None = None, **options: Any) -> Connector:
        connector = self._classes.get(name)
        if connector is None:
            raise KeyError(f"no connector called {name!r}; have: {', '.join(self.names())}")
        return connector(config=config, **options)

    def describe_all(self, config: Config | None = None) -> list[dict[str, Any]]:
        described = []
        for name in self.names():
            try:
                described.append(self.create(name, config).describe())
            except Exception as exc:
                described.append({"name": name, "available": False, "detail": str(exc)})
        return described

    def load_directory(self, directory: Path) -> list[str]:
        """Import every module in *directory* so its connectors register."""
        directory = Path(directory)
        if not directory.is_dir():
            return []
        loaded: list[str] = []
        for path in sorted(directory.glob("*.py")):
            if path.name.startswith("_") or path in self._loaded_paths:
                continue
            module_name = f"tapscript_connector_{path.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
            except Exception:
                # A broken generated connector must not stop the others loading.
                continue
            self._loaded_paths.add(path)
            loaded.append(path.stem)
        return loaded


registry = ConnectorRegistry()


def discover(config: Config | None = None) -> ConnectorRegistry:
    """Load built-in connectors plus anything in the workspace and plugins dir."""
    config = config or load_config()
    from . import builtin  # noqa: F401  (importing registers the built-ins)

    for directory in (config.paths.workspace / "connectors", config.paths.plugins_dir):
        registry.load_directory(directory)
    return registry


def run(
    name: str,
    arrangement: Arrangement,
    config: Config | None = None,
    **options: Any,
) -> ConnectorResult:
    """Convenience: find a connector, check it, run it."""
    config = config or load_config()
    registry = discover(config)
    connector = registry.create(name, config, **options)
    ok, detail = connector.available()
    if not ok:
        return ConnectorResult(False, detail=detail)
    return connector.send(arrangement, **options)


def iter_connectors(config: Config | None = None) -> Iterable[dict[str, Any]]:
    return discover(config).describe_all(config)
