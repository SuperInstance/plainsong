"""What the server offers to be read rather than called.

Resources are the things an agent should be able to look at without spending a
tool call and without side effects: the notation reference, what this machine
can do, the specs, the bundled library, and the state of an ensemble session.

Concrete resources are listed; the two large or open-ended sets -- the library
and the sessions -- are also given as URI templates, because listing several
thousand notation files into a client's context would be worse than useless.
``search_library`` is the way in.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from ..runtime.config import Config

SCHEME = "plainsong"

TEXT = "text/plain; charset=utf-8"
MARKDOWN = "text/markdown; charset=utf-8"
JSON = "application/json"


class NotFound(Exception):
    """No resource answers to that URI."""


@dataclass
class Resource:
    """One readable thing."""

    uri: str
    name: str
    description: str
    mime_type: str = TEXT

    def as_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


@dataclass
class Template:
    """A family of resources, parameterised by one segment."""

    uri_template: str
    name: str
    description: str
    mime_type: str = TEXT

    def as_dict(self) -> dict[str, Any]:
        return {
            "uriTemplate": self.uri_template,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


TEMPLATES = [
    Template(
        f"{SCHEME}://library/{{name}}",
        "library entry",
        "One notation file from the bundled library, by name or title. Use the "
        "search_library tool to find names.",
        TEXT,
    ),
    Template(
        f"{SCHEME}://session/{{name}}",
        "ensemble session",
        "The state of one ensemble session: header, form, voices, claims and the "
        "current merged score.",
        JSON,
    ),
    Template(
        f"{SCHEME}://spec/{{id}}",
        "spec",
        "One spec: the outcome it states and the checks that prove it.",
        JSON,
    ),
]


def _default_ensemble() -> Any:
    """This repo's own ensemble implementation.

    Resolved lazily, and only used when ``Resources`` is not given one -- see
    ``tools._default_ensemble`` for why.
    """
    from . import ensemble as ens

    return ens


class Resources:
    """The resource surface for one server."""

    def __init__(self, config: Config, session_root: Any = None, ensemble: Any = None) -> None:
        self.config = config
        self.session_root = session_root
        self._ensemble = ensemble
        self._readers: dict[str, Callable[[str], tuple[str, str]]] = {
            "library": self._read_library,
            "session": self._read_session,
            "spec": self._read_spec,
        }

    def _ens(self) -> Any:
        """The ensemble module this instance was given, or this repo's own."""
        return self._ensemble if self._ensemble is not None else _default_ensemble()

    # -- listing -------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """Concrete resources: the fixed two, plus every spec and session."""
        found = [
            Resource(
                f"{SCHEME}://notation-reference",
                "notation reference",
                "How to write Plainsong notation. Read this before writing any.",
                MARKDOWN,
            ),
            Resource(
                f"{SCHEME}://capabilities",
                "host capabilities",
                "What this machine can do: optional libraries, soundfonts, MIDI ports, "
                "audio playback.",
                JSON,
            ),
        ]
        for spec in self._specs():
            found.append(
                Resource(f"{SCHEME}://spec/{spec.id}", f"spec: {spec.id}", spec.title, JSON)
            )
        for name in self._sessions():
            found.append(
                Resource(
                    f"{SCHEME}://session/{name}",
                    f"session: {name}",
                    "An ensemble session in this workspace.",
                    JSON,
                )
            )
        return [resource.as_dict() for resource in found]

    def templates(self) -> list[dict[str, Any]]:
        return [template.as_dict() for template in TEMPLATES]

    # -- reading -------------------------------------------------------------

    def read(self, uri: str) -> list[dict[str, Any]]:
        """The contents block for one URI."""
        text, mime = self._read(uri)
        return [{"uri": uri, "mimeType": mime, "text": text}]

    def _read(self, uri: str) -> tuple[str, str]:
        prefix = f"{SCHEME}://"
        if not uri.startswith(prefix):
            raise NotFound(f"{uri!r} is not a {SCHEME}:// URI")
        rest = uri[len(prefix) :]
        head, _, tail = rest.partition("/")

        if head == "notation-reference" and not tail:
            return self._notation_reference(), MARKDOWN
        if head == "capabilities" and not tail:
            return self._capabilities(), JSON

        reader = self._readers.get(head)
        if reader is None or not tail:
            raise NotFound(f"no resource at {uri!r}")
        return reader(unquote(tail))

    def _notation_reference(self) -> str:
        from pathlib import Path

        # Ask the package where it lives rather than walking up from this file.
        # Walking up is correct only while this module sits inside plainsong/,
        # which stopped being true when the server was also packaged on its own.
        import plainsong

        reference = Path(plainsong.__file__).resolve().parent / "agent" / "prompts" / "notation.md"
        try:
            return reference.read_text(encoding="utf-8")
        except OSError as exc:
            raise NotFound(f"the notation reference is missing: {exc}") from None

    def _capabilities(self) -> str:
        from ..runtime.capabilities import probe
        from ..version import __version__

        report = probe()
        return json.dumps(
            {
                "version": __version__,
                "summary": report.summary(),
                "workspace": str(self.config.paths.workspace),
                "capabilities": [
                    {
                        "name": capability.name,
                        "present": capability.present,
                        "detail": capability.detail,
                        "remedy": capability.remedy,
                    }
                    for capability in report
                ],
            },
            indent=2,
        )

    def _read_library(self, name: str) -> tuple[str, str]:
        from ..library import Library

        entry = Library(paths=self.config.paths).find(name)
        if entry is None:
            raise NotFound(f"no library entry called {name!r}")
        return entry.read(), TEXT

    def _read_session(self, name: str) -> tuple[str, str]:
        ensemble = self._ens()

        try:
            session = ensemble.find_session(name, root=self.session_root, paths=self.config.paths)
        except ensemble.EnsembleError as exc:
            raise NotFound(str(exc)) from None
        state = session.read()
        state["score"] = session.score()
        return json.dumps(state, indent=2, default=str), JSON

    def _read_spec(self, spec_id: str) -> tuple[str, str]:
        for spec in self._specs():
            if spec.id == spec_id:
                return (
                    json.dumps(
                        {
                            "id": spec.id,
                            "title": spec.title,
                            "why": spec.why,
                            "tags": spec.tags,
                            "source": str(spec.source) if spec.source else "",
                            "checks": [
                                {
                                    "id": check.id,
                                    "kind": check.kind,
                                    "run": check.run,
                                    "optional": check.optional,
                                    "description": check.description,
                                }
                                for check in spec.checks
                            ],
                        },
                        indent=2,
                    ),
                    JSON,
                )
        raise NotFound(f"no spec called {spec_id!r}")

    # -- sources -------------------------------------------------------------

    def _specs(self) -> list[Any]:
        from ..specs import load_specs

        try:
            return load_specs(self.config.paths)
        except Exception:
            return []  # a broken spec file must not take the resource list with it

    def _sessions(self) -> list[str]:
        ensemble = self._ens()

        try:
            return ensemble.list_sessions(self.session_root, self.config.paths)
        except Exception:
            return []
