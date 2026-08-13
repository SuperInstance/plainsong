"""Many hands on one score.

A session is a directory. Each contributor owns one voice and writes only its
own part; the parts are merged into a score whenever anyone asks for it. That
is the whole design, and it is what makes several agents working at once mostly
uneventful: they write disjoint files, so there is nothing to merge line by
line.

    <workspace>/ensemble/<name>/
        manifest.json      the header, the form, the voices and the version
        parts/<voice>.tap  one file per voice, written by its owner
        score.tap          the merged result -- generated, never hand-edited
        log.jsonl          one line per accepted change, oldest first

Concurrency
-----------
The session carries a version that increases by one on every accepted write. A
write states the version it was made against; it is refused if *that voice* has
changed since. Writing to another voice moves the session version but cannot
invalidate your work, so two agents on two voices both succeed, and two agents
on one voice from the same base end with one winner and one rebase. Ownership
is the softer half of the same idea: claiming a voice stops two agents choosing
the same one in the first place, while the version check is what actually keeps
the file honest.

No lock is held while an agent is thinking. The lock here is taken to swap a
file and dropped microseconds later, because a model call takes seconds and a
lock that spans one is a lock that will be found abandoned.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..notation.ir import ROLE_CHORDS, ROLE_LYRICS, ROLE_MELODY, ROLE_NOTE, ROLE_PLAYER, Score
from ..runtime.paths import Paths, default_paths

MANIFEST = "manifest.json"
LOG = "log.jsonl"
SCORE = "score.tap"
PARTS = "parts"
LOCK = ".lock"

LOCK_TIMEOUT = 10.0
"""Seconds after which a lock file is assumed to belong to a crashed writer."""

LOCK_POLL = 0.005
MAX_PART_BYTES = 400_000

ROLE_VOICES = {"chords": ROLE_CHORDS, "melody": ROLE_MELODY, "lyrics": ROLE_LYRICS}
ROW_LABEL = {ROLE_CHORDS: "Chords:", ROLE_MELODY: "Melody:", ROLE_LYRICS: "Lyrics:"}

# Rows are written out in the order a lead sheet reads: harmony, tune, words,
# then the players. Fixed here so the merge is a function of the parts alone.
VOICE_ORDER = ("chords", "melody", "lyrics")

NAME_ALLOWED = set("abcdefghijklmnopqrstuvwxyz0123456789-_")


class EnsembleError(Exception):
    """Something the calling agent can fix, phrased for the calling agent."""


class Conflict(EnsembleError):
    """A write was made against a version the voice has moved past."""

    def __init__(self, message: str, state: dict[str, Any]) -> None:
        super().__init__(message)
        self.state = state


def now() -> str:
    """UTC, to the second. Every timestamp in a session uses this."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensemble_root(paths: Paths | None = None) -> Path:
    """Where sessions live. Derived, never hardcoded."""
    return (paths or default_paths()).workspace / "ensemble"


def safe_name(name: str, what: str = "session") -> str:
    """A name that is safe as a directory or file name, or an error."""
    cleaned = str(name).strip().lstrip("@").lower().replace(" ", "-")
    if not cleaned or not set(cleaned) <= NAME_ALLOWED:
        raise EnsembleError(
            f"{what} names may use letters, digits, '-' and '_' only; got {name!r}"
        )
    return cleaned


def voice_kind(voice: str) -> str:
    """``chords``, ``melody`` and ``lyrics`` are labelled rows; the rest are players."""
    return "row" if voice in ROLE_VOICES else "player"


def voice_label(voice: str) -> str:
    """How the voice is written in notation: ``Chords:`` or ``@bass``."""
    role = ROLE_VOICES.get(voice)
    return ROW_LABEL[role] if role else f"@{voice}"


def _write_atomic(path: Path, text: str) -> None:
    """Replace *path* in one step, so a crash cannot leave half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


class _FileLock:
    """A short-lived exclusive lock on one session directory.

    ``O_CREAT | O_EXCL`` is atomic on every platform we run on and needs
    nothing installed. It is held only around a read-modify-write of the
    manifest -- never across anything that talks to a model.
    """

    def __init__(self, directory: Path, timeout: float = LOCK_TIMEOUT) -> None:
        self.path = directory / LOCK
        self.timeout = timeout

    def __enter__(self) -> _FileLock:
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                handle = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(handle, f"{os.getpid()} {now()}\n".encode())
                os.close(handle)
                return self
            except FileExistsError:
                if self._is_stale():
                    self.path.unlink(missing_ok=True)
                    continue
                if time.monotonic() > deadline:
                    raise EnsembleError(
                        "the session is locked by another writer; try again in a moment"
                    ) from None
                time.sleep(LOCK_POLL)

    def __exit__(self, *exc: Any) -> None:
        self.path.unlink(missing_ok=True)

    def _is_stale(self) -> bool:
        try:
            age = time.time() - self.path.stat().st_mtime
        except OSError:
            return False
        return age > self.timeout


@dataclass
class VoiceState:
    """One voice's ownership and its last accepted write."""

    voice: str
    owner: str = ""
    claimed_at: str = ""
    version: int = 0
    updated: str = ""
    bars: int = 0
    notes: int = 0
    summary: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "voice": voice_label(self.voice),
            "name": self.voice,
            "kind": voice_kind(self.voice),
            "owner": self.owner,
            "held": bool(self.owner),
            "claimed_at": self.claimed_at,
            "version": self.version,
            "updated": self.updated,
            "bars": self.bars,
            "notes": self.notes,
            "summary": self.summary,
        }


@dataclass
class Manifest:
    """The session header: what the piece is, and where each voice stands."""

    name: str = ""
    version: int = 0
    created: str = ""
    updated: str = ""
    title: str = ""
    key: str = "C"
    tempo: float = 100.0
    meter: str = "4/4"
    subdivision: str = "8th"
    swing: str = "0%"
    bars: int = 8
    sections: list[dict[str, Any]] = field(default_factory=list)
    voices: dict[str, VoiceState] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "created": self.created,
            "updated": self.updated,
            "title": self.title,
            "key": self.key,
            "tempo": self.tempo,
            "meter": self.meter,
            "subdivision": self.subdivision,
            "swing": self.swing,
            "bars": self.bars,
            "sections": self.sections,
            "voices": {name: state.as_dict() for name, state in sorted(self.voices.items())},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        voices = {}
        for name, raw in (data.get("voices") or {}).items():
            voices[name] = VoiceState(
                voice=name,
                owner=raw.get("owner", ""),
                claimed_at=raw.get("claimed_at", ""),
                version=int(raw.get("version", 0)),
                updated=raw.get("updated", ""),
                bars=int(raw.get("bars", 0)),
                notes=int(raw.get("notes", 0)),
                summary=raw.get("summary", ""),
            )
        return cls(
            name=data.get("name", ""),
            version=int(data.get("version", 0)),
            created=data.get("created", ""),
            updated=data.get("updated", ""),
            title=data.get("title", ""),
            key=data.get("key", "C"),
            tempo=float(data.get("tempo", 100.0)),
            meter=data.get("meter", "4/4"),
            subdivision=data.get("subdivision", "8th"),
            swing=data.get("swing", "0%"),
            bars=int(data.get("bars", 8)),
            sections=list(data.get("sections") or []),
            voices=voices,
        )

    def header(self) -> str:
        """The metadata block every part is validated against and the score carries."""
        return (
            f"**TRACK: {self.title or self.name}**\n"
            "[MetaData]\n"
            f"key: {self.key} | tempo: {self.tempo:g} | swing: {self.swing} | "
            f"subdivision: {self.subdivision}\n"
            f"time: {self.meter}\n"
        )

    def section_names(self) -> list[str]:
        return [str(section.get("name", "")) for section in self.sections]


@dataclass
class Session:
    """One shared score on disk."""

    directory: Path

    # -- locations -----------------------------------------------------------

    @property
    def name(self) -> str:
        return self.directory.name

    @property
    def manifest_path(self) -> Path:
        return self.directory / MANIFEST

    @property
    def score_path(self) -> Path:
        return self.directory / SCORE

    @property
    def log_path(self) -> Path:
        return self.directory / LOG

    def part_path(self, voice: str) -> Path:
        return self.directory / PARTS / f"{voice}.tap"

    def exists(self) -> bool:
        return self.manifest_path.is_file()

    # -- state ---------------------------------------------------------------

    def manifest(self) -> Manifest:
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise EnsembleError(f"no session called {self.name!r} ({exc.strerror})") from None
        except json.JSONDecodeError as exc:
            raise EnsembleError(f"the manifest of {self.name!r} is unreadable: {exc}") from None
        return Manifest.from_dict(data)

    def _save(self, manifest: Manifest) -> None:
        manifest.updated = now()
        _write_atomic(self.manifest_path, json.dumps(manifest.as_dict(), indent=2) + "\n")

    def part(self, voice: str) -> str:
        path = self.part_path(voice)
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def parts(self) -> dict[str, str]:
        """Every part on disk, keyed by voice."""
        directory = self.directory / PARTS
        if not directory.is_dir():
            return {}
        return {
            path.stem: path.read_text(encoding="utf-8")
            for path in sorted(directory.glob("*.tap"))
        }

    def entries(self, limit: int = 0) -> list[dict[str, Any]]:
        """The change log, oldest first; *limit* keeps the last N."""
        if not self.log_path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a torn line from a crashed writer is not worth failing over
        return rows[-limit:] if limit > 0 else rows

    def _append_log(self, entry: dict[str, Any]) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    # -- claims --------------------------------------------------------------

    def join(self, voice: str, agent: str, takeover: bool = False) -> dict[str, Any]:
        """Claim a voice for *agent*. One owner at a time."""
        voice = safe_name(voice, "voice")
        agent = _agent_name(agent)
        with _FileLock(self.directory):
            manifest = self.manifest()
            state = manifest.voices.setdefault(voice, VoiceState(voice=voice))
            if state.owner and state.owner != agent and not takeover:
                raise EnsembleError(
                    f"{voice_label(voice)} is held by {state.owner} since {state.claimed_at}. "
                    f"Free voices: {', '.join(self._free(manifest)) or '(none named)'}. "
                    "Pass takeover=true only if you know they have stopped."
                )
            previous = state.owner
            state.owner = agent
            state.claimed_at = now()
            manifest.version += 1
            self._save(manifest)
            self._append_log(
                {
                    "version": manifest.version,
                    "time": state.claimed_at,
                    "agent": agent,
                    "voice": voice,
                    "action": "takeover" if previous and previous != agent else "join",
                    "summary": f"{agent} took {voice_label(voice)}"
                    + (f" from {previous}" if previous and previous != agent else ""),
                }
            )
        return self.read(voice=voice, agent=agent)

    def leave(self, voice: str, agent: str) -> dict[str, Any]:
        """Release a voice so somebody else can take it."""
        voice = safe_name(voice, "voice")
        agent = _agent_name(agent)
        with _FileLock(self.directory):
            manifest = self.manifest()
            state = manifest.voices.get(voice)
            if state is None or not state.owner:
                raise EnsembleError(f"{voice_label(voice)} is not claimed by anyone")
            if state.owner != agent:
                raise EnsembleError(f"{voice_label(voice)} is held by {state.owner}, not {agent}")
            state.owner = ""
            state.claimed_at = ""
            manifest.version += 1
            self._save(manifest)
            self._append_log(
                {
                    "version": manifest.version,
                    "time": now(),
                    "agent": agent,
                    "voice": voice,
                    "action": "leave",
                    "summary": f"{agent} released {voice_label(voice)}",
                }
            )
        return {"session": self.name, "voice": voice_label(voice), "released": True}

    def _free(self, manifest: Manifest) -> list[str]:
        return [
            voice_label(name)
            for name, state in sorted(manifest.voices.items())
            if not state.owner
        ]

    # -- writing -------------------------------------------------------------

    def write_part(
        self,
        voice: str,
        agent: str,
        content: str,
        base_version: int,
        summary: str = "",
    ) -> dict[str, Any]:
        """Accept a part, or explain why it was refused.

        The notation is parsed before anything reaches disk, exactly as
        ``write_score`` does, and it is checked against the session header so a
        part cannot be valid alone and wrong in the piece.
        """
        voice = safe_name(voice, "voice")
        agent = _agent_name(agent)
        if len(content.encode("utf-8")) > MAX_PART_BYTES:
            raise EnsembleError(f"a part may not exceed {MAX_PART_BYTES} bytes")

        with _FileLock(self.directory):
            manifest = self.manifest()
            state = manifest.voices.setdefault(voice, VoiceState(voice=voice))

            if state.owner and state.owner != agent:
                raise EnsembleError(
                    f"{voice_label(voice)} is held by {state.owner}. Join it first, or "
                    f"choose another voice: {', '.join(self._free(manifest)) or '(none named)'}"
                )
            if int(base_version) != state.version:
                raise Conflict(
                    f"{voice_label(voice)} has moved on: you wrote against version "
                    f"{base_version}, it is now at {state.version}. Read it again, put your "
                    "change on top of what is there, and write with the version you get back.",
                    self._state_for(manifest, voice, agent),
                )

            document = self._compose(manifest, voice, content)
            score, problems = _validate(document, voice)
            if problems:
                raise EnsembleError(
                    f"{voice_label(voice)} was not written -- the notation has problems:\n"
                    + "\n".join(f"  {problem}" for problem in problems)
                )

            _write_atomic(self.part_path(voice), _normalise(content))
            manifest.version += 1
            state.version = manifest.version
            state.updated = now()
            state.bars = score.bar_count
            state.notes = _note_count(score)
            state.summary = summary.strip().splitlines()[0][:200] if summary.strip() else ""
            _absorb_sections(manifest, score)
            self._save(manifest)
            self._append_log(
                {
                    "version": manifest.version,
                    "time": state.updated,
                    "agent": agent,
                    "voice": voice,
                    "action": "write",
                    "bars": state.bars,
                    "summary": state.summary or f"{agent} wrote {voice_label(voice)}",
                }
            )
            merged = self.merge(manifest)
            _write_atomic(self.score_path, merged)

        return {
            "session": self.name,
            "voice": voice_label(voice),
            "accepted": True,
            "version": state.version,
            "bars": state.bars,
            "notes": state.notes,
            "part": str(self.part_path(voice)),
            "score": str(self.score_path),
        }

    def _compose(self, manifest: Manifest, voice: str, content: str) -> str:
        """A part in the session's header, which is what it has to be valid in."""
        body = _normalise(content)
        if not any(line.startswith("[") for line in body.splitlines()):
            first = manifest.section_names()[0] if manifest.sections else "A"
            body = f"[{first}]\n{body}"
        return f"{manifest.header()}\n{body}"

    def _state_for(self, manifest: Manifest, voice: str, agent: str) -> dict[str, Any]:
        state = manifest.voices.get(voice) or VoiceState(voice=voice)
        return {
            "session": self.name,
            "version": manifest.version,
            "voice": voice_label(voice),
            "voice_version": state.version,
            "owner": state.owner,
            "yours": state.owner == agent,
            "content": self.part(voice),
        }

    # -- merging -------------------------------------------------------------

    def merge(self, manifest: Manifest | None = None) -> str:
        """The parts, in one score.

        Deterministic: the same parts and the same header always produce the
        same bytes. Sections come out in the order the manifest declares them
        and then in the order they first appear scanning voices in row order;
        rows come out in row order within each section.
        """
        manifest = manifest or self.manifest()
        parts = self.parts()
        collected: dict[str, list[tuple[str, list[str]]]] = {}
        order: list[str] = [name for name in manifest.section_names() if name]
        descriptions: dict[str, str] = {
            str(section.get("name", "")): str(section.get("description", ""))
            for section in manifest.sections
            if section.get("description")
        }

        for voice in _row_order(parts):
            score, _ = _validate(self._compose(manifest, voice, parts[voice]), voice)
            for section in score.sections:
                rows = [line.raw.rstrip() for line in section.lines if line.raw.strip()]
                if not rows:
                    continue
                if section.name not in order:
                    order.append(section.name)
                descriptions.setdefault(section.name, section.description)
                collected.setdefault(section.name, []).append((voice, rows))

        lines = [manifest.header()]
        for name in order:
            entries = collected.get(name)
            if not entries:
                continue
            description = descriptions.get(name, "")
            lines.append(f"[{name}] ({description})" if description else f"[{name}]")
            for _voice, rows in entries:
                lines.extend(rows)
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def score(self) -> str:
        """The merged score, rebuilt if a part has changed under it."""
        return self.merge()

    # -- reading -------------------------------------------------------------

    def read(
        self,
        voice: str = "",
        agent: str = "",
        bars: str = "",
        history: int = 8,
    ) -> dict[str, Any]:
        """Everything a joining agent needs to write its next bars, in one call.

        The header, the form, who holds what, and -- for the bars it is about to
        write -- the chords and what every other voice already plays there.
        """
        manifest = self.manifest()
        voice = safe_name(voice, "voice") if voice else ""
        merged = self.merge(manifest)
        window = _window(merged, manifest, bars)

        mine: dict[str, Any] | None = None
        if voice:
            existing = manifest.voices.get(voice) or VoiceState(voice=voice)
            mine = {
                "voice": voice_label(voice),
                "owner": existing.owner,
                "yours": bool(agent) and existing.owner == _agent_name(agent),
                "base_version": existing.version,
                "content": self.part(voice),
            }

        return {
            "session": self.name,
            "version": manifest.version,
            "directory": str(self.directory),
            "meta": {
                "title": manifest.title or manifest.name,
                "key": manifest.key,
                "tempo": manifest.tempo,
                "meter": manifest.meter,
                "subdivision": manifest.subdivision,
                "swing": manifest.swing,
                "bars": manifest.bars,
            },
            "sections": manifest.sections,
            "voices": [found.as_dict() for _, found in sorted(manifest.voices.items())],
            "free_voices": self._free(manifest),
            "you": mine,
            "window": window,
            "recent": self.entries(limit=max(0, history)),
            "score_path": str(self.score_path),
        }

    def status(self) -> dict[str, Any]:
        """The short form: version, voices, bars, and whether the score compiles."""
        manifest = self.manifest()
        merged = self.merge(manifest)
        from ..notation import parse

        score = parse(merged)
        return {
            "session": self.name,
            "version": manifest.version,
            "title": manifest.title or manifest.name,
            "key": manifest.key,
            "tempo": manifest.tempo,
            "meter": manifest.meter,
            "voices": [found.as_dict() for _, found in sorted(manifest.voices.items())],
            "held": [
                voice_label(name)
                for name, state in sorted(manifest.voices.items())
                if state.owner
            ],
            "bars": score.bar_count,
            "errors": [diag.format() for diag in score.errors()],
            "warnings": len(score.warnings()),
            "changes": len(self.entries()),
        }

    def render(self, audio: bool = False, config: Any = None) -> dict[str, Any]:
        """Compile the merged score into the session directory."""
        from ..pipeline import compile_text

        merged = self.merge()
        _write_atomic(self.score_path, merged)
        result = compile_text(
            merged,
            midi=self.directory / f"{self.name}.mid",
            audio=(self.directory / f"{self.name}.wav") if audio else None,
            config=config,
            path=str(self.score_path),
        )
        return {
            "session": self.name,
            "ok": result.ok,
            "score": str(self.score_path),
            "midi": str(result.midi_path) if result.midi_path else "",
            "audio": str(result.audio_path) if result.audio_path else "",
            "summary": result.summary(),
            "describe": result.describe(),
        }


# --------------------------------------------------------------------------
# opening and listing
# --------------------------------------------------------------------------


def open_session(
    name: str,
    root: Path | None = None,
    paths: Paths | None = None,
    title: str = "",
    key: str = "C",
    tempo: float = 100.0,
    meter: str = "4/4",
    subdivision: str = "8th",
    swing: str = "0%",
    bars: int = 8,
    sections: list[Any] | None = None,
    voices: list[str] | None = None,
) -> Session:
    """Open a session, creating it if it is not there. Opening twice is safe."""
    name = safe_name(name)
    directory = (root or ensemble_root(paths)) / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / PARTS).mkdir(exist_ok=True)
    session = Session(directory)

    with _FileLock(directory):
        if session.exists():
            return session
        manifest = Manifest(
            name=name,
            version=1,
            created=now(),
            title=title or name,
            key=key,
            tempo=float(tempo),
            meter=meter,
            subdivision=subdivision,
            swing=swing,
            bars=int(bars),
            sections=_sections(sections, bars),
        )
        for voice in voices or []:
            key_name = safe_name(voice, "voice")
            manifest.voices[key_name] = VoiceState(voice=key_name)
        session._save(manifest)
        session._append_log(
            {
                "version": 1,
                "time": manifest.created,
                "agent": "",
                "voice": "",
                "action": "open",
                "summary": f"session opened in {manifest.key} at {manifest.tempo:g} bpm",
            }
        )
    return session


def find_session(name: str, root: Path | None = None, paths: Paths | None = None) -> Session:
    """An existing session, or an error naming the ones that do exist."""
    directory = (root or ensemble_root(paths)) / safe_name(name)
    session = Session(directory)
    if not session.exists():
        known = ", ".join(list_sessions(root, paths)) or "(none yet)"
        raise EnsembleError(f"no session called {name!r}. Open sessions: {known}")
    return session


def list_sessions(root: Path | None = None, paths: Paths | None = None) -> list[str]:
    """Every session in the workspace, alphabetically."""
    base = root or ensemble_root(paths)
    if not base.is_dir():
        return []
    return sorted(
        entry.name for entry in base.iterdir() if (entry / MANIFEST).is_file()
    )


def _sections(sections: list[Any] | None, bars: int) -> list[dict[str, Any]]:
    """Normalise the form given at open time into a list of section records."""
    if not sections:
        return [{"name": "A", "description": f"{bars} bars", "bars": int(bars)}]
    normalised: list[dict[str, Any]] = []
    for entry in sections:
        if isinstance(entry, str):
            normalised.append({"name": entry.strip("[] "), "description": "", "bars": int(bars)})
            continue
        if isinstance(entry, dict):
            normalised.append(
                {
                    "name": str(entry.get("name", "A")).strip("[] "),
                    "description": str(entry.get("description", "")),
                    "bars": int(entry.get("bars", bars)),
                }
            )
    return normalised or [{"name": "A", "description": "", "bars": int(bars)}]


def _agent_name(agent: str) -> str:
    name = str(agent).strip()
    if not name:
        raise EnsembleError("say who you are: pass an agent name")
    return name[:64]


def _normalise(content: str) -> str:
    """One trailing newline, no carriage returns, no trailing blanks on a line.

    Two agents on two platforms must produce the same bytes for the same part,
    or the merged score stops being reproducible.
    """
    lines = [line.rstrip() for line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


def _row_order(parts: dict[str, str]) -> list[str]:
    """Voices in the order their rows are written out: harmony, tune, words, players."""
    labelled = [name for name in VOICE_ORDER if name in parts]
    players = sorted(name for name in parts if name not in ROLE_VOICES)
    return labelled + players


def _note_count(score: Score) -> int:
    """How many notes the part actually makes, which is what an author asks about."""
    from ..notation import arrange

    try:
        return arrange(score).note_count
    except Exception:
        return 0


def _validate(document: str, voice: str) -> tuple[Score, list[str]]:
    """Parse a part in its session header and check it only speaks for its voice."""
    from ..notation import parse

    score = parse(document)
    problems = [diag.format() for diag in score.errors()]
    role = ROLE_VOICES.get(voice)
    for section in score.sections:
        for line in section.lines:
            if line.role == ROLE_NOTE:
                continue
            if role is not None:
                if line.role != role:
                    problems.append(
                        f"line {line.line_number}: this part may only contain "
                        f"{voice_label(voice)} rows, found a {line.role} row"
                    )
                continue
            if line.role != ROLE_PLAYER or line.name.lower() != voice:
                found = f"@{line.name}" if line.role == ROLE_PLAYER else f"{line.role} row"
                problems.append(
                    f"line {line.line_number}: this part may only contain "
                    f"{voice_label(voice)} rows, found {found}"
                )
    return score, problems


def _absorb_sections(manifest: Manifest, score: Score) -> None:
    """Record any section a part introduced, so the form stays visible to joiners."""
    known = set(manifest.section_names())
    for section in score.sections:
        if section.name in known:
            continue
        manifest.sections.append(
            {
                "name": section.name,
                "description": section.description,
                "bars": section.bar_count,
            }
        )
        known.add(section.name)


# --------------------------------------------------------------------------
# the window a joining agent reads
# --------------------------------------------------------------------------


def _window(merged: str, manifest: Manifest, bars: str) -> dict[str, Any]:
    """What every voice plays, bar by bar, over the requested range.

    This is the part a joining agent cannot work without: it is about to write
    bars 5 to 8 of one voice and needs the harmony there and what the others are
    already doing, without reading the whole piece.
    """
    from ..notation import parse

    score = parse(merged)
    table = _bar_table(score)
    first, last = parse_bar_range(bars, len(table))
    rows = [entry for entry in table if first <= entry["bar"] <= last]
    return {
        "from": first,
        "to": last,
        "total_bars": len(table),
        "meter": manifest.meter,
        "bars": rows,
    }


def parse_bar_range(bars: str, total: int) -> tuple[int, int]:
    """Read ``5-8``, ``5``, ``5..8`` or an empty string meaning every bar."""
    text = str(bars or "").strip().replace("..", "-")
    if not text:
        return (1, max(total, 1))
    head, _, tail = text.partition("-")
    try:
        first = max(1, int(head))
        last = int(tail) if tail.strip() else first
    except ValueError:
        return (1, max(total, 1))
    return (first, max(first, last))


def _bar_table(score: Score) -> list[dict[str, Any]]:
    """One entry per bar of the piece: its section and each voice's tokens.

    A row repeated inside a section continues it, so a voice's bars are the
    concatenation of its rows -- the same rule the arranger follows.
    """
    table: list[dict[str, Any]] = []
    offset = 0
    for section in score.sections:
        cells: dict[str, list[Any]] = {}
        for line in section.lines:
            if line.role == ROLE_NOTE or not line.cells:
                continue
            label = voice_label(line.name.lower()) if line.role == ROLE_PLAYER else ROW_LABEL.get(
                line.role, line.role
            )
            cells.setdefault(label, []).extend(line.cells)
        length = max((len(found) for found in cells.values()), default=0)
        for index in range(length):
            entry: dict[str, Any] = {
                "bar": offset + index + 1,
                "section": section.name,
                "voices": {},
            }
            for label, found in sorted(cells.items()):
                if index < len(found):
                    entry["voices"][label] = found[index].text
            table.append(entry)
        offset += length
    return table


def iter_sessions(root: Path | None = None, paths: Paths | None = None) -> Iterator[Session]:
    """Every session in the workspace, as objects."""
    base = root or ensemble_root(paths)
    for name in list_sessions(base):
        yield Session(base / name)
