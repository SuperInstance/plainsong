"""A stable fingerprint of what notation compiles to.

The chord grammar was safe to make the default because every chord token in the
repository was compiled with the old engine and the new one and the results
compared: 181,276 identical, 136 newly readable, 0 changed. That comparison is
the only reason anybody could say the change was additive rather than hoping so.

It was also a script somebody ran by hand once, which means the guarantee it
established stopped being checked the moment the script was closed. `plainsong
check` proves that notation still *compiles*; it says nothing about whether it
compiles to the same notes. A change that moved every chord down a semitone
would pass it cleanly.

So the comparison lives here instead, and runs in CI. A fingerprint is a hash
per file of the notes that file produces -- pitch, position, length, velocity,
and the voice they land in. Two builds agreeing on the fingerprint agree on the
music, and when they disagree the output names exactly which files moved.

It is a user-facing command rather than a private test helper on purpose.
Anybody with a folder of `.song` files they care about has the same problem we
do, and no access to our test suite:

    plainsong fingerprint mysongs > before.txt
    pip install --upgrade plainsong
    plainsong fingerprint mysongs > after.txt
    diff before.txt after.txt

Silence there is a real answer to "did the upgrade change my music", which is
otherwise a question nobody can answer about a compiler.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

__all__ = ["FileFingerprint", "fingerprint_file", "fingerprint_paths", "format_report"]

#: Beats are floats, and a float that differs in its last bit on one platform
#: would make the fingerprint useless for the thing it exists to do. Six places
#: is far finer than any musical distinction and far coarser than the noise.
_PLACES = 6


@dataclass(frozen=True)
class FileFingerprint:
    path: str
    digest: str
    notes: int
    error: str = ""

    def as_dict(self) -> dict[str, object]:
        return {"path": self.path, "digest": self.digest, "notes": self.notes, "error": self.error}


def _canonical(arrangement: object) -> str:
    """A deterministic text form of everything that decides how a piece sounds.

    Sorted rather than taken in arrangement order, because the order tracks are
    emitted in is an implementation detail and changing it is not a change to
    the music. Anything that *is* audible -- which voice, which pitch, when,
    how long, how hard -- is in here.
    """
    lines: list[str] = []
    for track, note in arrangement.iter_notes():  # type: ignore[attr-defined]
        lines.append(
            "\t".join(
                (
                    track.name,
                    track.role,
                    str(track.program),
                    "drum" if track.is_drum else "pitched",
                    str(note.pitch),
                    f"{round(note.start, _PLACES):.6f}",
                    f"{round(note.duration, _PLACES):.6f}",
                    str(note.velocity),
                    # The solved times, which are the whole point of a piece
                    # that declares a stage. Absent otherwise, and absent is
                    # different from equal to the written time.
                    "-" if note.emission is None else f"{round(note.emission, _PLACES):.6f}",
                    "-" if note.arrival is None else f"{round(note.arrival, _PLACES):.6f}",
                )
            )
        )
    lines.sort()
    return "\n".join(lines)


def fingerprint_file(path: Path) -> FileFingerprint:
    from .notation import arrange, parse

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return FileFingerprint(str(path), "-", 0, f"unreadable: {error}")
    try:
        arrangement = arrange(parse(text, path=str(path)))
    except Exception as error:  # noqa: BLE001 - a crash is a fingerprint result
        # A file that stops compiling is exactly the kind of change this is for,
        # so it is recorded rather than raised. The digest of a failure is the
        # failure, which means a *different* crash also shows up as a diff.
        return FileFingerprint(str(path), "-", 0, f"{type(error).__name__}: {error}")
    digest = hashlib.sha256(_canonical(arrangement).encode("utf-8")).hexdigest()[:16]
    return FileFingerprint(str(path), digest, arrangement.note_count)


def fingerprint_paths(paths: list[str]) -> list[FileFingerprint]:
    """Fingerprint every `.song` file under each path, in a stable order."""
    found: list[Path] = []
    for entry in paths:
        candidate = Path(entry)
        if candidate.is_dir():
            found.extend(sorted(candidate.rglob("*.song")))
        elif candidate.is_file():
            found.append(candidate)
    # Sorted by the posix form so Windows and Linux produce the same file, which
    # they otherwise would not: the separator is part of the string.
    return [fingerprint_file(path) for path in sorted(found, key=lambda p: p.as_posix())]


def format_report(entries: list[FileFingerprint]) -> str:
    """The checked-in form: one line per file, plus a total.

    Designed to be read by `diff`, so the interesting property is that a change
    to one piece moves one line. The total is last so that a change to it does
    not shift every line above it.
    """
    lines = [f"{entry.digest}  {entry.notes:>6}  {Path(entry.path).as_posix()}" for entry in entries]
    total = sum(entry.notes for entry in entries)
    failed = sum(1 for entry in entries if entry.error)
    lines.append(f"# {len(entries)} files, {total} notes, {failed} failed")
    return "\n".join(lines) + "\n"
