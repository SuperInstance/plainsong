"""The intermediate representation.

Parsing produces a :class:`Score` -- a faithful structural picture of the text,
with timing left implicit. Arranging turns that into an :class:`Arrangement`
of timed notes. Renderers consume the arrangement and never see the text.

Keeping the two apart means a parser bug cannot produce silent notes and a
timing bug cannot corrupt round-tripped notation.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .theory import Chord, Key
from .timegrid import TimeGrid

if TYPE_CHECKING:  # imported for typing only -- perform/ depends on this module
    from ..perform.stage import Placement, Stage

# Line roles the parser recognises.
ROLE_CHORDS = "chords"
ROLE_MELODY = "melody"
ROLE_LYRICS = "lyrics"
ROLE_PLAYER = "player"
ROLE_VELOCITY = "velocity"
ROLE_ANNOTATION = "annot"
"""A named annotation layer (``Breath:``, ``Gaze:`` ... any row the writer
names). ``Vel:`` is the built-in one; see ``notation/annotations.py``.

The string is ``annot`` because ``annotation`` was taken -- by ROLE_NOTE,
years before named layers existed -- for free-text lines a file carries
without playing."""
ROLE_NOTE = "annotation"

SEVERITIES = ("info", "warning", "error")


@dataclass(frozen=True)
class Diagnostic:
    """Something worth telling the author about, tied to a source line."""

    severity: str
    message: str
    line: int = 0
    column: int = 0
    hint: str = ""
    source: str = ""

    def format(self, path: str = "") -> str:
        where = f"{path}:{self.line}" if path else f"line {self.line}"
        text = f"{where}: {self.severity}: {self.message}"
        if self.hint:
            text += f"\n    hint: {self.hint}"
        return text

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "hint": self.hint,
            "source": self.source,
        }


@dataclass
class Cell:
    """One bar's worth of tokens on one line."""

    tokens: list[str] = field(default_factory=list)
    line: int = 0

    def __bool__(self) -> bool:
        return bool(self.tokens)

    @property
    def text(self) -> str:
        return " ".join(self.tokens)


@dataclass
class Line:
    """A labelled row of notation: chords, melody, lyrics or a named player."""

    role: str
    cells: list[Cell] = field(default_factory=list)
    name: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    line_number: int = 0
    raw: str = ""
    barred: bool = True
    """False when the row was written without pipes.

    An unbarred row has no bar structure to divide, so its tokens are laid out
    at the fixed subdivision unit and the notation reads as duration-by-spacing
    (``C4~~~`` is four units long). A barred row divides each bar between the
    tokens written inside it.
    """

    @property
    def bar_count(self) -> int:
        return len(self.cells)

    @property
    def token_count(self) -> int:
        return sum(len(cell.tokens) for cell in self.cells)


@dataclass
class Section:
    """A named block: verse, chorus, bridge."""

    name: str
    description: str = ""
    lines: list[Line] = field(default_factory=list)
    line_number: int = 0

    @property
    def bar_count(self) -> int:
        return max((line.bar_count for line in self.lines), default=0)

    def lines_with_role(self, role: str) -> list[Line]:
        return [line for line in self.lines if line.role == role]

    def players(self) -> list[Line]:
        return self.lines_with_role(ROLE_PLAYER)


@dataclass
class Meter:
    """Time signature."""

    numerator: int = 4
    denominator: int = 4

    @property
    def beats_per_bar(self) -> float:
        """Beats per bar, where a beat is a quarter note."""
        return self.numerator * 4 / self.denominator

    def __str__(self) -> str:
        return f"{self.numerator}/{self.denominator}"

    @classmethod
    def readable(cls, text: str) -> bool:
        """Whether `parse` will get a metre out of this rather than defaulting.

        The parser needs to tell "you wrote 4/4" from "you wrote nonsense and
        got 4/4", and it cannot do that from the result alone.
        """
        try:
            numerator, slash, denominator = text.strip().partition("/")
        except AttributeError:
            return False
        if not slash and not numerator.strip().isdigit():
            return False
        try:
            meter = cls(int(numerator), int(denominator or 4))
        except (ValueError, AttributeError):
            return False
        return meter.numerator >= 1 and meter.denominator in (1, 2, 4, 8, 16, 32)

    @classmethod
    def parse(cls, text: str) -> Meter:
        if not cls.readable(text):
            return cls()
        numerator, _, denominator = text.strip().partition("/")
        return cls(int(numerator), int(denominator or 4))


@dataclass
class Metadata:
    """Everything above the first section header."""

    title: str = ""
    key: Key = field(default_factory=lambda: Key(0, "major"))
    tempo: float = 100.0
    meter: Meter = field(default_factory=Meter)
    swing: float = 0.0
    subdivision: str = "8th"
    extra: dict[str, str] = field(default_factory=dict)
    stage: Stage | None = None
    """Set when the file declares a ``[Stage]`` block. ``None`` means written
    times are taken at face value, which is what everything did before
    arrival-centric timing existed."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "key": self.key.name(),
            "mode": self.key.mode,
            "tempo": self.tempo,
            "meter": str(self.meter),
            "swing": self.swing,
            "subdivision": self.subdivision,
            **self.extra,
        }


@dataclass
class Score:
    """A parsed piece of notation."""

    meta: Metadata = field(default_factory=Metadata)
    sections: list[Section] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    dialect: str = "absolute"
    source: str = ""
    path: str = ""

    @property
    def bar_count(self) -> int:
        return sum(section.bar_count for section in self.sections)

    @property
    def has_errors(self) -> bool:
        return any(diag.severity == "error" for diag in self.diagnostics)

    def errors(self) -> list[Diagnostic]:
        return [diag for diag in self.diagnostics if diag.severity == "error"]

    def warnings(self) -> list[Diagnostic]:
        return [diag for diag in self.diagnostics if diag.severity == "warning"]

    def player_names(self) -> list[str]:
        seen: list[str] = []
        for section in self.sections:
            for line in section.players():
                if line.name not in seen:
                    seen.append(line.name)
        return seen

    def annotation_rows(self, name: str = "") -> list["Line"]:
        """The named annotation rows of the piece, in written order.

        *name* filters case-insensitively (``score.annotation_rows("breath")``);
        empty means every layer. Empty for a piece that writes none -- a row
        a composer does not write does not exist, and nothing phantom is
        constructed to stand in for it. ``Vel:`` rows are not included: they
        are the built-in layer, parsed to their own role.
        """
        key = name.strip().lower()
        return [
            line
            for section in self.sections
            for line in section.lines
            if line.role == ROLE_ANNOTATION and (not key or line.name.lower() == key)
        ]

    def summary(self) -> dict[str, Any]:
        return {
            "title": self.meta.title or "(untitled)",
            "key": self.meta.key.name(),
            "tempo": self.meta.tempo,
            "meter": str(self.meta.meter),
            "dialect": self.dialect,
            "sections": len(self.sections),
            "bars": self.bar_count,
            "players": self.player_names(),
            "errors": len(self.errors()),
            "warnings": len(self.warnings()),
        }


# --------------------------------------------------------------------------
# Timed representation
# --------------------------------------------------------------------------


@dataclass
class Note:
    """A sounding note, positioned in beats from the start of the piece.

    ``start`` is the written time and always has been. When a piece declares a
    stage, the solver fills in two more: ``emission``, when the player has to
    act, and ``arrival``, when the sound reaches the listener the render is
    made for. Both stay ``None`` otherwise, and both fall back to ``start``, so
    nothing downstream has to know whether a stage was declared.
    """

    start: float
    duration: float
    pitch: int
    velocity: int = 80
    emission: float | None = None
    arrival: float | None = None

    @property
    def end(self) -> float:
        return self.start + self.duration

    @property
    def emission_time(self) -> float:
        """When the player acts. What a MIDI file or a performer needs."""
        return self.start if self.emission is None else self.emission

    @property
    def arrival_time(self) -> float:
        """When the sound is heard. What an audio render has to place."""
        return self.start if self.arrival is None else self.arrival


@dataclass
class Track:
    """One instrument's worth of notes."""

    name: str
    role: str = ROLE_PLAYER
    program: int = 0
    channel: int = 0
    is_drum: bool = False
    notes: list[Note] = field(default_factory=list)
    instrument: str = "piano"
    placement: Placement | None = None
    """Where this voice stands, when the piece declares a stage."""

    def add(self, note: Note) -> None:
        self.notes.append(note)

    @property
    def duration(self) -> float:
        # Without a stage, arrival_time is start and this is the written end.
        return max(
            (max(note.end, note.arrival_time + note.duration) for note in self.notes),
            default=0.0,
        )

    def sort(self) -> None:
        self.notes.sort(key=lambda note: (note.start, note.pitch))


@dataclass
class LyricEvent:
    """A syllable positioned in time, carried through for display and export."""

    start: float
    text: str

    duration: float = 0.0
    """How long the syllable is held. Zero when lyrics carry a time of their
    own rather than being bound to notes; when bound, a word lasts until the
    next word's note, so fewer words than notes is a melisma without a mark."""


@dataclass(frozen=True)
class Annotation:
    """One annotation value, resolved to the event it marks.

    Built by the arranger from the time grid the target row was already
    placed on, so the address and the note went through the same arithmetic:
    a consumer joins on ``(voice, bar, onset)`` -- or simply compares against
    the grid -- rather than trusting the column a writer laid out. ``target``
    is the token the value stands over and ``target_kind`` what it is
    (``note``, ``chord``, ``sustain``, ``rest``); a value over a rest is still
    data, and a consumer that only wants attacks filters on the kind.
    """

    name: str
    """The dimension as written (``Breath``), not lowercased."""

    token: str
    """The value as written (``deep``, ``0.6``)."""

    voice: str
    """The target row's key on the time grid: ``melody`` or ``player:bass``."""

    role: str
    """The target row's role: ``melody``, ``chords`` or ``player``."""

    bar: int
    """Absolute bar index from the start of the piece."""

    unit: float
    """Position within the bar, 0.0 <= unit < 1.0."""

    onset: float
    """Beats from the start of the piece: the beat window's start."""

    width: float
    """Beats the marked token occupies: the beat window's length."""

    target: str
    """The target token the value stands over, as written."""

    target_kind: str
    """What the target token is: note | chord | sustain | rest."""

    line_number: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "token": self.token,
            "voice": self.voice,
            "role": self.role,
            "bar": self.bar,
            "unit": round(self.unit, 6),
            "onset": round(self.onset, 6),
            "width": round(self.width, 6),
            "target": self.target,
            "target_kind": self.target_kind,
            "line": self.line_number,
        }


@dataclass
class ChordEvent:
    """A chord symbol positioned in time, for lead sheets and analysis."""

    start: float
    duration: float
    chord: Chord


@dataclass
class Arrangement:
    """A score resolved into time. This is what renderers consume."""

    meta: Metadata
    tracks: list[Track] = field(default_factory=list)
    lyrics: list[LyricEvent] = field(default_factory=list)
    chords: list[ChordEvent] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    section_starts: list[tuple[str, float]] = field(default_factory=list)
    stage: Stage | None = None
    frame: str = ""
    """The listener the emission and arrival times were solved for. Empty when
    no stage was declared."""

    lead_in: float = 0.0
    """Beats the whole piece was pushed later so that nobody has to act before
    it starts. Emission and arrival times both include it, so subtract it to
    compare a solved time against the beat it was written on."""

    grid: TimeGrid = field(default_factory=TimeGrid)
    """Every written token on one coordinate system, sounding or not -- the
    only place a lyric and the note above it can be compared. Renderers, the
    merge in `plainsong-mcp`, and alignment linting all read this rather than
    each deriving positions of their own. See `notation/timegrid.py`."""

    annotations: list[Annotation] = field(default_factory=list)
    """Named annotation values, resolved to the events they mark. Empty for
    a piece that writes no such rows; nothing phantom is constructed."""

    @property
    def total_beats(self) -> float:
        return max((track.duration for track in self.tracks), default=0.0)

    @property
    def duration_seconds(self) -> float:
        return self.total_beats * 60.0 / max(self.meta.tempo, 1e-6)

    @property
    def note_count(self) -> int:
        return sum(len(track.notes) for track in self.tracks)

    def iter_notes(self) -> Iterator[tuple[Track, Note]]:
        for track in self.tracks:
            for note in track.notes:
                yield track, note

    def summary(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "tracks": [
                {
                    "name": track.name,
                    "role": track.role,
                    "instrument": track.instrument,
                    "program": track.program,
                    "notes": len(track.notes),
                }
                for track in self.tracks
            ],
            "beats": round(self.total_beats, 3),
            "seconds": round(self.duration_seconds, 2),
            "notes": self.note_count,
            "lyrics": len(self.lyrics),
        }
        if self.stage is not None:
            data["stage"] = {"frame": self.frame, "listener": self.stage.listener}
        return data
