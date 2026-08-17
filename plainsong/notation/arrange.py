"""Score to :class:`Arrangement` -- the step that decides when things happen.

Timing rule
-----------
A bar is one bar long. Whatever number of tokens a row puts in it, they divide
that bar between them. Twelve tokens in a bar of four make triplets; five make
quintuplets; a seventeenth token cannot silently spill into the next bar
because there is no next bar to spill into.

The earlier engine instead gave every token a fixed grid slot, so a row that
did not happen to contain exactly the expected number of tokens was either cut
short or written over the following bar. ``bar_fill = "grid"`` restores that
behaviour for files that were written around it; it reports what it drops.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from .. import instruments as gm
from . import theory
from .ir import (
    ROLE_CHORDS,
    ROLE_LYRICS,
    ROLE_MELODY,
    ROLE_NOTE,
    ROLE_PLAYER,
    Arrangement,
    ChordEvent,
    Diagnostic,
    Line,
    LyricEvent,
    Note,
    Score,
    Track,
)
from .parser import REST_TOKENS, SUSTAIN_TOKENS, Slot, token_weight

DEGREE_RE = re.compile(r"^([b#♭♯]?)([1-7])([\^_']*)$")
SUBDIVISION_UNITS = {
    "4th": 1.0, "quarter": 1.0,
    "8th": 0.5, "eighth": 0.5,
    "16th": 0.25, "sixteenth": 0.25,
    "32nd": 0.125,
    "triplet": 1.0 / 3.0,
}

DEFAULT_VELOCITY = {
    ROLE_MELODY: 88,
    ROLE_CHORDS: 64,
    ROLE_PLAYER: 76,
}

DEFAULT_OCTAVE = {
    ROLE_MELODY: 4,
    ROLE_CHORDS: 3,
    ROLE_PLAYER: 3,
}


@dataclass
class ArrangeOptions:
    """Knobs the caller may turn. Defaults match the documented behaviour."""

    bar_fill: str = "rescale"          # rescale | grid
    humanize: bool = True
    humanize_seed: int = 42
    humanize_velocity: int = 6
    swing: float | None = None          # None means take it from the score
    melody_instrument: str = "piano"
    chords_instrument: str = "nylon guitar"
    chord_voicing_octave: int = 3
    max_chord_notes: int = 4
    voicing: str = "guide"
    """Which notes to keep when a chord names more than ``max_chord_notes``.

    ``guide`` gives up the fifth first and the root second, keeping the third,
    the seventh and whatever extension the symbol was written for. ``stack``
    is the old behaviour -- the lowest four notes -- which discarded the named
    extension in half the cases where the cap bit at all, so `D9` sounded like
    `D7`. ``shell``, ``drop2`` and ``spread`` are also available; see
    ``notation/voicing.py`` and `docs/voicing.md` for how they were compared."""
    transpose: int = 0
    frame: str = ""
    """Which listener to solve arrival times for. Empty means the one the
    ``[Stage]`` block names, and ``score`` means no compensation at all. Has no
    effect on a piece that does not declare a stage."""

    compensate: bool | None = None
    """Override the stage's own ``compensate`` setting. ``None`` leaves it
    alone; ``False`` renders the errors instead of correcting them."""


class Arranger:
    """Resolve a :class:`Score` into timed notes."""

    def __init__(self, score: Score, options: ArrangeOptions | None = None) -> None:
        self.score = score
        self.options = options or ArrangeOptions()
        self.diagnostics: list[Diagnostic] = []
        self._unreadable: set[str] = set()
        self._rng = random.Random(self.options.humanize_seed)
        self._tracks: dict[str, Track] = {}
        self._channel_cursor = 0

    # -- track allocation ----------------------------------------------------

    def _next_channel(self, is_drum: bool) -> int:
        if is_drum:
            return 9
        channel = self._channel_cursor
        self._channel_cursor += 1
        if self._channel_cursor % 16 == 9:  # channel 10 is reserved for drums
            self._channel_cursor += 1
        return channel % 16

    def _track_for(self, key: str, name: str, role: str, instrument: str) -> Track:
        existing = self._tracks.get(key)
        if existing is not None:
            return existing
        is_drum = gm.is_drum_name(instrument) or gm.is_drum_name(name)
        track = Track(
            name=name,
            role=role,
            instrument=instrument,
            program=gm.program_for(instrument),
            channel=self._next_channel(is_drum),
            is_drum=is_drum,
        )
        self._tracks[key] = track
        return track

    # -- token resolution ----------------------------------------------------

    def _resolve_token(self, token: str, role: str, octave: int) -> Slot:
        """Turn one written token into a rhythmic slot."""
        bare, weight = token_weight(token)
        lowered = bare.lower()

        if lowered in SUSTAIN_TOKENS or lowered.startswith("(hold"):
            return Slot(kind="sustain", weight=weight, text=bare)
        if lowered in REST_TOKENS or lowered.startswith("(rest") or lowered.startswith("(sil"):
            return Slot(kind="rest", weight=weight, text=bare)
        if bare.startswith("(") and bare.endswith(")"):
            # A stage direction where a note could be: hold what is sounding.
            return Slot(kind="sustain", weight=weight, text=bare)

        if role == ROLE_CHORDS:
            chord = self._resolve_chord(bare)
            if chord is not None:
                return Slot(kind="chord", weight=weight, chord=chord, text=bare)
            self._unreadable.add(bare)
            return Slot(kind="rest", weight=weight, text=bare)

        pitches = self._resolve_pitches(bare, octave)
        if pitches:
            return Slot(kind="note", weight=weight, pitches=pitches, text=bare)

        # A melody row may legitimately carry a chord symbol.
        chord = self._resolve_chord(bare)
        if chord is not None:
            return Slot(kind="chord", weight=weight, chord=chord, text=bare)
        # Nothing understood this token, and it is about to become silence.
        # Saying so matters: `Xm9` and `A B C D` (pitches with no octave) both
        # compiled clean and produced nothing, so the first a writer knew about
        # it was a bar of unexplained silence.
        self._unreadable.add(bare)
        return Slot(kind="rest", weight=weight, text=bare)

    def _resolve_chord(self, token: str) -> theory.Chord | None:
        if self.score.dialect == "relative" and theory.is_roman(token):
            try:
                return theory.parse_roman(token, self.score.meta.key)
            except theory.TheoryError:
                return None
        try:
            return theory.parse_chord(token)
        except theory.TheoryError:
            pass
        if theory.is_roman(token):
            try:
                return theory.parse_roman(token, self.score.meta.key)
            except theory.TheoryError:
                return None
        return None

    def _resolve_pitches(self, token: str, octave: int) -> tuple[int, ...]:
        """Resolve a pitch token, which may stack notes with ``-``."""
        parts = [part for part in token.split("-") if part]
        pitches: list[int] = []
        for part in parts:
            if theory.is_pitch(part):
                try:
                    pitches.append(theory.parse_pitch(part, default_octave=octave))
                    continue
                except theory.TheoryError:
                    pass
            degree = DEGREE_RE.match(part)
            if degree and self.score.dialect == "relative":
                accidental, number, marks = degree.groups()
                shift = {"b": -1, "♭": -1, "#": 1, "♯": 1}.get(accidental, 0)
                octave_shift = marks.count("^") + marks.count("'") - marks.count("_")
                pitches.append(
                    self.score.meta.key.degree_pitch(int(number), octave + octave_shift, shift)
                )
                continue
            return ()
        return tuple(pitch for pitch in pitches if 0 <= pitch <= 127)

    # -- rhythm --------------------------------------------------------------

    def _slot_positions(
        self, slots: list[Slot], bar_start: float, bar_beats: float, line: Line
    ) -> list[tuple[Slot, float, float]]:
        """Place slots inside a bar. Returns (slot, start_beat, length_beats)."""
        if not slots:
            return []
        total_weight = sum(slot.weight for slot in slots)
        if total_weight <= 0:
            return []

        if self.options.bar_fill == "grid":
            unit = SUBDIVISION_UNITS.get(str(self.score.meta.subdivision).lower(), 0.5)
            capacity = bar_beats / unit
            if total_weight > capacity + 1e-9:
                dropped = 0
                running = 0.0
                kept: list[Slot] = []
                for slot in slots:
                    if running + slot.weight > capacity + 1e-9:
                        dropped += 1
                        continue
                    running += slot.weight
                    kept.append(slot)
                self.diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        message=f"bar holds {int(capacity)} slots but the row wrote "
                        f"{total_weight:g}; {dropped} token(s) dropped",
                        line=line.line_number,
                        hint="use the default bar_fill = \"rescale\" to fit the tokens to the bar instead",
                        source=line.raw,
                    )
                )
                slots = kept
                total_weight = sum(slot.weight for slot in slots) or 1.0
            span = capacity * unit
        else:
            span = bar_beats

        # Positions are computed from the bar start rather than accumulated, so
        # rounding cannot drift and the last slot ends exactly on the bar line.
        placed: list[tuple[Slot, float, float]] = []
        running = 0.0
        for slot in slots:
            start = bar_start + (running / total_weight) * span
            running += slot.weight
            end = bar_start + (running / total_weight) * span
            placed.append((slot, start, end - start))
        return placed

    def _swing_offset(self, start: float, swing: float) -> float:
        if swing <= 0:
            return 0.0
        position = start % 1.0
        if abs(position - 0.5) < 0.05:
            return swing * (2.0 / 3.0 - 0.5)
        return 0.0

    def _velocity(self, base: int) -> int:
        if not self.options.humanize or self.options.humanize_velocity <= 0:
            return max(1, min(127, base))
        jitter = self._rng.randint(-self.options.humanize_velocity, self.options.humanize_velocity)
        return max(1, min(127, base + jitter))

    # -- main walk -----------------------------------------------------------

    def arrange(self) -> Arrangement:
        meta = self.score.meta
        bar_beats = meta.meter.beats_per_bar
        swing = self.options.swing if self.options.swing is not None else meta.swing
        lyrics: list[LyricEvent] = []
        chords: list[ChordEvent] = []
        section_starts: list[tuple[str, float]] = []

        cursor = 0.0
        fallback_index = 0
        unit = SUBDIVISION_UNITS.get(str(meta.subdivision).lower(), 0.5)

        for section in self.score.sections:
            playable = [
                line for line in section.lines if line.cells and line.role != ROLE_NOTE
            ]
            if not playable:
                continue
            section_starts.append((section.name, cursor))

            # Rows of different kinds sound together; a row repeated within one
            # section continues it, bar after bar, the way successive lines of a
            # lead sheet read.
            groups: dict[str, list[Line]] = {}
            for line in playable:
                key = f"{line.role}:{line.name}" if line.role == ROLE_PLAYER else line.role
                groups.setdefault(key, []).append(line)

            section_beats = 0.0
            for key, group in groups.items():
                offset = cursor
                for line in group:
                    length = self._line_beats(line, bar_beats, unit)
                    if line.role == ROLE_LYRICS:
                        self._place_lyrics(line, offset, bar_beats, lyrics)
                    else:
                        instrument, velocity, octave = self._line_voice(line, fallback_index)
                        if line.role == ROLE_PLAYER and key not in self._tracks:
                            fallback_index += 1
                        track = self._track_for(key, line.name or line.role, line.role, instrument)
                        self._place_row(
                            line=line,
                            track=track,
                            origin=offset,
                            bar_beats=bar_beats,
                            velocity=velocity,
                            octave=octave,
                            swing=swing,
                            unit=unit,
                            chords_out=chords if line.role == ROLE_CHORDS else None,
                        )
                    offset += length
                section_beats = max(section_beats, offset - cursor)

            cursor += section_beats

        tracks = list(self._tracks.values())
        for track in tracks:
            track.sort()
            if self.options.transpose:
                for note in track.notes:
                    note.pitch = max(0, min(127, note.pitch + self.options.transpose))

        arrangement = Arrangement(
            meta=meta,
            tracks=tracks,
            lyrics=lyrics,
            chords=chords,
            diagnostics=self.score.diagnostics + self.diagnostics,
            section_starts=section_starts,
        )
        self._solve_performance(arrangement)
        return arrangement

    def _solve_performance(self, arrangement: Arrangement) -> None:
        """Fill in emission and arrival times, if the piece declares a stage.

        A piece with no ``[Stage]`` block never gets here, and one that has one
        still keeps every written ``start`` untouched: the solved times sit
        alongside them.
        """
        stage = arrangement.meta.stage
        if stage is None:
            return
        from dataclasses import replace

        from ..perform.solve import apply_to

        if self.options.compensate is not None and self.options.compensate != stage.compensate:
            # A copy, so that turning compensation off for one render does not
            # rewrite the score everybody else is reading.
            stage = replace(stage, compensate=self.options.compensate)
        apply_to(arrangement, frame=self.options.frame, stage=stage)

    def _line_voice(self, line: Line, fallback_index: int) -> tuple[str, int, int]:
        role = line.role
        instrument = str(line.options.get("instrument") or "")
        if not instrument:
            if role == ROLE_MELODY:
                instrument = self.options.melody_instrument
            elif role == ROLE_CHORDS:
                instrument = self.options.chords_instrument
            else:
                instrument = gm.instrument_for_name(line.name, fallback_index)
        velocity = int(line.options.get("velocity") or DEFAULT_VELOCITY.get(role, 76))
        octave = int(line.options.get("octave") or DEFAULT_OCTAVE.get(role, 3))
        if "bass" in instrument.lower():
            octave = min(octave, 2)
        return instrument, velocity, octave

    def _line_beats(self, line: Line, bar_beats: float, unit: float) -> float:
        """How long a row lasts, in beats.

        Barred rows are one bar per cell. Unbarred rows -- notation written
        without pipes -- run at the fixed subdivision unit and are rounded up
        to a whole bar so sections stay aligned with each other.
        """
        if line.barred:
            return line.bar_count * bar_beats
        weight = sum(token_weight(token)[1] for cell in line.cells for token in cell.tokens)
        beats = weight * unit
        bars = max(1, int(beats / bar_beats) + (1 if beats % bar_beats > 1e-9 else 0))
        return bars * bar_beats

    def _place_lyrics(self, line: Line, origin: float, bar_beats: float, out: list[LyricEvent]) -> None:
        for bar_index, cell in enumerate(line.cells):
            if not cell.tokens:
                continue
            bar_start = origin + bar_index * bar_beats
            step = bar_beats / len(cell.tokens)
            for token_index, token in enumerate(cell.tokens):
                out.append(LyricEvent(start=bar_start + token_index * step, text=token))

    def _place_row(
        self,
        line: Line,
        track: Track,
        origin: float,
        bar_beats: float,
        velocity: int,
        octave: int,
        swing: float,
        unit: float,
        chords_out: list[ChordEvent] | None,
    ) -> None:
        pending: list[tuple[list[int], float, float]] = []  # pitches, start, end

        def flush() -> None:
            for pitches, start, end in pending:
                duration = max(end - start, 1e-3)
                for pitch in pitches:
                    track.add(
                        Note(
                            start=start + self._swing_offset(start, swing),
                            duration=duration,
                            pitch=pitch,
                            velocity=self._velocity(velocity),
                        )
                    )
            pending.clear()

        if line.barred:
            groups = [
                (origin + index * bar_beats, cell.tokens) for index, cell in enumerate(line.cells)
            ]
        else:
            groups = [(origin, [token for cell in line.cells for token in cell.tokens])]

        for group_start, tokens in groups:
            self._unreadable.clear()
            slots = [self._resolve_token(token, line.role, octave) for token in tokens]
            if self._unreadable:
                shown = ", ".join(sorted(self._unreadable)[:4])
                more = len(self._unreadable) - 4
                self.diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        message=f"{line.role} row: nothing understood "
                        f"{shown}{f' and {more} more' if more > 0 else ''}; "
                        "silence there instead",
                        line=line.line_number,
                        hint="chords look like Am, F#m7, Bb; pitches carry an octave, "
                        "as in A4 or c3 -- a bare A is not a pitch",
                        source=line.raw,
                    )
                )
            if line.barred:
                placed = self._slot_positions(slots, group_start, bar_beats, line)
            else:
                placed = []
                running = 0.0
                for slot in slots:
                    start = group_start + running * unit
                    running += slot.weight
                    placed.append((slot, start, group_start + running * unit - start))

            for slot, start, length in placed:
                if slot.kind == "sustain":
                    if pending:
                        pitches, note_start, _ = pending[-1]
                        pending[-1] = (pitches, note_start, start + length)
                    continue
                if slot.kind == "rest":
                    flush()
                    continue

                flush()
                if slot.kind == "chord" and slot.chord is not None:
                    from .voicing import voice

                    notes = list(
                        voice(
                            slot.chord,
                            octave=self.options.chord_voicing_octave,
                            limit=self.options.max_chord_notes,
                            strategy=self.options.voicing,
                        )
                    )
                    pending.append((list(notes), start, start + length))
                    if chords_out is not None:
                        chords_out.append(ChordEvent(start=start, duration=length, chord=slot.chord))
                elif slot.kind == "note":
                    pending.append((list(slot.pitches), start, start + length))
        flush()


def arrange(score: Score, options: ArrangeOptions | None = None) -> Arrangement:
    """Resolve a parsed score into timed notes."""
    return Arranger(score, options).arrange()
