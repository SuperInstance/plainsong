"""The bundled notation library.

Whatever ``.song`` files ship with a checkout -- the fake book, the examples,
the teaching material -- are indexed here so the CLI, the web interface and the
agent can all search the same set without walking the tree three different
ways.

The index is built lazily and cached on disk, because a full checkout holds
several thousand files.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .notation.ir import Score
from .runtime.paths import Paths, default_paths

SEARCH_DIRECTORIES = ("library", "docs/songs", "examples")
"""Places to look under the project root, for people working from a clone."""

BUNDLED_SONGBOOK = "songbook"
"""The chord charts that ship with the package.

They live inside `plainsong/` for the same reason the specs do: a wheel carries
only what is under the package. Kept in `docs/`, the whole library was invisible
to anyone who installed rather than cloned -- `plainsong library "waltz"` said
"nothing found" and `plainsong play stand-by-me`, which the README advertises,
could not work at all.
"""


def bundled_songbook() -> Path:
    return Path(__file__).resolve().parent / BUNDLED_SONGBOOK


INDEX_VERSION = 2

HEADER_RE = re.compile(r"^(?:\*\*)?TRACK\s*:\s*(?P<title>.+?)(?:\*\*)?$", re.IGNORECASE | re.MULTILINE)
KEY_RE = re.compile(r"^key\s*:\s*(?P<key>[^|\n]+)", re.IGNORECASE | re.MULTILINE)
TEMPO_RE = re.compile(r"tempo\s*:\s*(?P<tempo>\d+)", re.IGNORECASE)


@dataclass
class LibraryEntry:
    """One notation file in the library."""

    path: Path
    name: str
    title: str = ""
    key: str = ""
    tempo: int = 0
    collection: str = ""
    size: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "name": self.name,
            "title": self.title or self.name,
            "key": self.key,
            "tempo": self.tempo,
            "collection": self.collection,
            "size": self.size,
        }

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8", errors="replace")


@dataclass
class Library:
    """An index over the notation files in a checkout."""

    root: Path | None = None
    paths: Paths = field(default_factory=default_paths)
    _entries: list[LibraryEntry] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.root is None:
            self.root = self.paths.project_root or Path.cwd()

    # -- index ---------------------------------------------------------------

    @property
    def index_file(self) -> Path:
        return self.paths.cache_dir / "library-index.json"

    def _collection_for(self, path: Path, directory: Path) -> str:
        """A short label for where an entry came from.

        Relative to the project root for a clone, and to the bundled songbook
        otherwise -- the bundled files sit inside site-packages, so relating
        them to the root either raises or prints an absolute path nobody wants
        to read in a table.
        """
        assert self.root is not None
        bundled = bundled_songbook()
        if directory == bundled:
            # Name it for what it is, not for where pip happened to put it. The
            # alternative is a site-packages path in every row of the table.
            try:
                return f"{BUNDLED_SONGBOOK}/{path.parent.relative_to(bundled)}".rstrip("/.")
            except ValueError:
                return BUNDLED_SONGBOOK
        try:
            return str(path.parent.relative_to(self.root))
        except ValueError:
            return path.parent.name

    def _scan(self) -> list[LibraryEntry]:
        entries: list[LibraryEntry] = []
        assert self.root is not None
        directories = [bundled_songbook()] + [self.root / name for name in SEARCH_DIRECTORIES]
        seen: set[Path] = set()
        for directory in directories:
            if not directory.is_dir() or directory in seen:
                continue
            seen.add(directory)
            for path in sorted(directory.rglob("*.song")):
                try:
                    head = path.read_text(encoding="utf-8", errors="replace")[:600]
                    size = path.stat().st_size
                except OSError:
                    continue
                title_match = HEADER_RE.search(head)
                key_match = KEY_RE.search(head)
                tempo_match = TEMPO_RE.search(head)
                entries.append(
                    LibraryEntry(
                        path=path,
                        name=path.stem,
                        title=title_match.group("title").strip() if title_match else path.stem,
                        key=key_match.group("key").split("|")[0].strip() if key_match else "",
                        tempo=int(tempo_match.group("tempo")) if tempo_match else 0,
                        collection=self._collection_for(path, directory),
                        size=size,
                    )
                )
        return entries

    def _load_cache(self) -> list[LibraryEntry] | None:
        try:
            data = json.loads(self.index_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if data.get("version") != INDEX_VERSION or data.get("root") != str(self.root):
            return None
        if time.time() - data.get("built", 0) > 86400:
            return None
        entries = []
        for item in data.get("entries", []):
            path = Path(item["path"])
            if not path.exists():
                return None  # the checkout moved; rebuild
            entries.append(
                LibraryEntry(
                    path=path,
                    name=item["name"],
                    title=item.get("title", ""),
                    key=item.get("key", ""),
                    tempo=int(item.get("tempo", 0)),
                    collection=item.get("collection", ""),
                    size=int(item.get("size", 0)),
                )
            )
        return entries

    def _save_cache(self, entries: list[LibraryEntry]) -> None:
        try:
            self.index_file.parent.mkdir(parents=True, exist_ok=True)
            self.index_file.write_text(
                json.dumps(
                    {
                        "version": INDEX_VERSION,
                        "root": str(self.root),
                        "built": time.time(),
                        "entries": [entry.as_dict() for entry in entries],
                    }
                ),
                encoding="utf-8",
            )
        except OSError:
            pass  # a cache that cannot be written is not an error

    def refresh(self) -> list[LibraryEntry]:
        self._entries = self._scan()
        self._save_cache(self._entries)
        return self._entries

    def all(self) -> list[LibraryEntry]:
        if self._entries is None:
            self._entries = self._load_cache() or self.refresh()
        return self._entries

    # -- access --------------------------------------------------------------

    def entries(self, limit: int = 0, collection: str = "") -> list[LibraryEntry]:
        items = self.all()
        if collection:
            items = [entry for entry in items if entry.collection.startswith(collection)]
        if limit and limit < len(items):
            step = max(1, len(items) // limit)
            items = items[::step][:limit]
        return items

    def collections(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.all():
            top = entry.collection.split("/")[0] if entry.collection else "."
            counts[top] = counts.get(top, 0) + 1
        return dict(sorted(counts.items()))

    def search(self, query: str, limit: int = 25) -> list[LibraryEntry]:
        """Match on title, filename, key or collection."""
        needle = query.strip().lower()
        if not needle:
            return self.all()[:limit]
        terms = needle.split()
        scored: list[tuple[int, LibraryEntry]] = []
        for entry in self.all():
            haystack = f"{entry.title} {entry.name} {entry.collection} {entry.key}".lower()
            if not all(term in haystack for term in terms):
                continue
            score = 0
            if needle in entry.title.lower():
                score += 10
            if entry.title.lower().startswith(needle):
                score += 5
            if needle in entry.name.lower():
                score += 3
            scored.append((score, entry))
        scored.sort(key=lambda pair: (-pair[0], pair[1].title))
        return [entry for _score, entry in scored[:limit]]

    def find(self, reference: str) -> LibraryEntry | None:
        """Resolve a path, a filename or a title to one entry."""
        candidate = Path(reference)
        if candidate.exists() and candidate.suffix == ".song":
            return LibraryEntry(path=candidate, name=candidate.stem, title=candidate.stem, collection="")
        lowered = reference.strip().lower()
        for entry in self.all():
            if lowered in (entry.name.lower(), entry.title.lower(), str(entry.path).lower()):
                return entry
        matches = self.search(reference, limit=1)
        return matches[0] if matches else None

    def parse(self, entry: LibraryEntry) -> Score:
        from .notation import parse as parse_notation

        return parse_notation(entry.read(), path=str(entry.path))

    def __iter__(self) -> Iterator[LibraryEntry]:
        return iter(self.all())

    def __len__(self) -> int:
        return len(self.all())
