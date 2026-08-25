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
    ROLE_VELOCITY,
    Arrangement,
    ChordEvent,
    Diagnostic,
    Line,
    LyricEvent,
    Note,
    Score,
    Track,
)
from .parser import (
    REST_TOKENS,
    SUSTAIN_TOKENS,
    Slot,
    parse_velocity_mark,
    split_dynamics,
    token_weight,
)
from .timegrid import TimeGrid

DEGREE_RE = re.compile(r"^([b#♭♯]?)([1-7])([\^_']*)$")
SUBDIVISION_UNITS = {
    "4th": 1.0,
    "quarter": 1.0,
    "8th": 0.5,
    "eighth": 0.5,
    "16th": 0.25,
    "sixteenth": 0.25,
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

# -- swing -----------------------------------------------------------------
#
# ``swing: NN%`` names the share of a beat the *long* note of each
# eighth-note pair occupies. 50% is straight (the pair splits the beat in
# half), 66% is approximately a triplet, 75% is dotted. Anything at or below
# 50% reads as straight; anything above 90% is held at 90%, because past that
# the short eighth of the pair is so brief the pair stops being a pair.

SWING_STRAIGHT = 0.5
SWING_CEILING = 0.9
# Onsets are produced by division, so "on the half-beat" arrives as 0.4999…
# and has to be recognised within a tolerance.
SWING_TOLERANCE = 0.05


def swing_amount(swing: float) -> float:
    """The share of a beat the long eighth of a swung pair occupies."""
    if swing <= 0.0:
        return SWING_STRAIGHT
    return min(SWING_CEILING, max(SWING_STRAIGHT, float(swing)))


@dataclass
class ArrangeOptions:
    """Knobs the caller may turn. Defaults match the documented behaviour."""

    bar_fill: str = "rescale"  # rescale | grid
    humanize: bool = True
    humanize_seed: int = 42
    humanize_velocity: int = 6
    swing: float | None = None  # None means take it from the score
    melody_instrument: str = "piano"
    chords_instrument: str = "nylon guitar"
    chord_voicing_octave: int = 3
    max_chord_notes: int = 4
    voicing: str = "guide"
    lyrics: str = "independent"  # independent | bound
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
        self.grid = TimeGrid(bar_beats=score.meta.meter.beats_per_bar)

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

        # A dynamics mark written on the token (`C4!`, `Am@64`) travels with
        # it and is resolved here rather than left to the renderer, so the
        # arrangement carries one velocity per note no matter who reads it.
        core, absolute, delta = split_dynamics(bare)

        if role == ROLE_CHORDS:
            chord = self._resolve_chord(core)
            if chord is not None:
                return Slot(
                    kind="chord", weight=weight, chord=chord, text=bare,
                    velocity=absolute, velocity_delta=delta,
                )
            self._unreadable.add(bare)
            return Slot(kind="rest", weight=weight, text=bare)

        pitches = self._resolve_pitches(core, octave)
        if pitches:
            return Slot(
                kind="note", weight=weight, pitches=pitches, text=bare,
                velocity=absolute, velocity_delta=delta,
            )

        # A melody row may legitimately carry a chord symbol.
        chord = self._resolve_chord(core)
        if chord is not None:
            return Slot(
                kind="chord", weight=weight, chord=chord, text=bare,
                velocity=absolute, velocity_delta=delta,
            )
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
                pitches.append(self.score.meta.key.degree_pitch(int(number), octave + octave_shift, shift))
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
                        hint='use the default bar_fill = "rescale" to fit the tokens to the bar instead',
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

    def _swing_time(self, time: float, swing: float) -> float:
        """Remap one written time onto the swung timeline.

        Only the half-beat moves: a time sitting on the eighth-note off-beat
        slides from 0.5 of its beat to the swing amount, and every other time
        -- downbeats, sixteenths, triplet thirds, bar lines -- stays exactly
        where it was written. Notes stretch to meet the moved off-beat, which
        is what makes a pair long-short rather than merely late.
        """
        amount = swing_amount(swing)
        if amount <= SWING_STRAIGHT + 1e-9:
            return time
        position = time % 1.0
        if abs(position - SWING_STRAIGHT) < SWING_TOLERANCE:
            return time - position + amount
        return time

    def _velocity(self, base: int) -> int:
        if not self.options.humanize or self.options.humanize_velocity <= 0:
            return max(1, min(127, base))
        jitter = self._rng.randint(-self.options.humanize_velocity, self.options.humanize_velocity)
        return max(1, min(127, base + jitter))

    # -- dynamics ------------------------------------------------------------

    def _is_attack(self, token: str) -> bool:
        """Whether a written token starts a sound, by the cheap test.

        The full answer lives in ``_resolve_token``, but working out which
        tokens a ``Vel:`` row marks must not re-implement pitch and chord
        parsing. Sustains, rests and parenthesised directions are the tokens
        that never attack; an unreadable token counts here and becomes a rest
        later, which can skew the marks of a row that is already warning about
        the tokens it cannot read.
        """
        bare, _weight = token_weight(token)
        lowered = bare.lower()
        if lowered in SUSTAIN_TOKENS or lowered.startswith("(hold"):
            return False
        if lowered in REST_TOKENS or lowered.startswith("(rest") or lowered.startswith("(sil"):
            return False
        if bare.startswith("(") and bare.endswith(")"):
            return False
        return True

    def _velocity_plans(self, section) -> dict[int, list[int | None]]:
        """Resolve the ``Vel:`` rows of one section into per-attack velocities.

        A ``Vel:`` row marks the nearest playable row above it and owns no time
        of its own, the way a bound lyric row owns none. The result is keyed by
        the target row's ``id`` and holds one value per attack -- ``None`` where
        the mark said nothing and the row's own velocity stands.
        """
        plans: dict[int, list[int | None]] = {}
        claimed: set[int] = set()
        target: Line | None = None
        for line in section.lines:
            if line.role == ROLE_VELOCITY:
                if not line.cells:
                    continue
                if target is None or not target.cells:
                    # The parser already said this at parse time, with a line
                    # number -- saying it again here would double the warning.
                    continue
                if id(target) in claimed:
                    self.diagnostics.append(
                        Diagnostic(
                            severity="warning",
                            message=f"a second Vel: row marks the {target.role} row above it; the first stands",
                            line=line.line_number,
                            source=line.raw,
                        )
                    )
                    continue
                claimed.add(id(target))
                plans[id(target)] = self._velocity_plan(target, line)
                continue
            if line.cells and line.role in {ROLE_CHORDS, ROLE_MELODY, ROLE_PLAYER}:
                target = line
        return plans

    def _velocity_plan(self, target: Line, vel_line: Line) -> list[int | None]:
        """One target row and its ``Vel:`` row, resolved to attack velocities.

        The k-th token of a ``Vel:`` cell marks the k-th token of the bar
        above it. That is a *positional* reading, deliberately: a writer lays
        the marks under the notes they are for, and a ``.`` in the marking row
        holds that column the way it holds a note. Marks standing over a
        sustain or a rest do nothing, and the cheap attack test decides which
        tokens those are -- the same cheap test ``_is_attack`` documents.
        """
        base = int(target.options.get("velocity") or DEFAULT_VELOCITY.get(target.role, 76))
        target_bars = (
            [cell.tokens for cell in target.cells]
            if target.barred
            else [[token for cell in target.cells for token in cell.tokens]]
        )
        vel_bars = (
            [cell.tokens for cell in vel_line.cells]
            if vel_line.barred
            else [[token for cell in vel_line.cells for token in cell.tokens]]
        )

        marks: list[tuple[str, object] | None] = []
        width = max(len(target_bars), len(vel_bars))
        for bar in range(width):
            tokens = target_bars[bar] if bar < len(target_bars) else []
            written = vel_bars[bar] if bar < len(vel_bars) else []
            if len(written) > len(tokens):
                self.diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        message=f"Vel: bar {bar + 1} writes {len(written)} mark(s) over "
                        f"{len(tokens)} token(s); the extra marks do nothing",
                        line=vel_line.line_number,
                        hint="a Vel: cell holds one mark per token of the row above",
                        source=vel_line.raw,
                    )
                )
            junk: list[str] = []
            for position, token in enumerate(tokens):
                if not self._is_attack(token):
                    continue
                mark = None
                if position < len(written):
                    mark = parse_velocity_mark(written[position])
                    if mark is None and not self._is_velocity_spacer(written[position]):
                        junk.append(written[position])
                        mark = None
                marks.append(mark)
            if junk:
                shown = ", ".join(sorted(set(junk))[:4])
                self.diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        message=f"Vel: row: nothing understood {shown}; skipped",
                        line=vel_line.line_number,
                        hint="a Vel: cell holds numbers (72), changes (+10, -8), names "
                        "(mf, f), cresc/dim, or . to leave a note alone",
                        source=vel_line.raw,
                    )
                )

        return self._resolve_marks(marks, base)

    @staticmethod
    def _is_velocity_spacer(token: str) -> bool:
        bare, _weight = token_weight(token)
        lowered = bare.lower()
        return lowered in SUSTAIN_TOKENS or lowered in REST_TOKENS

    @staticmethod
    def _resolve_marks(marks: list[tuple[str, object] | None], base: int) -> list[int | None]:
        """Turn a per-attack sequence of marks into per-attack velocities.

        Dynamics hold until the next one -- ``| p . . f |`` plays piano
        through the first three notes and forte on the fourth, the way a
        marking does on paper. ``.`` is the same rule spelt as a token. Numbers
        and names stand for themselves; ``+10``/``-8`` ride on whatever came
        before. ``cresc``/``dim`` ramp from the note they sit on to the next
        explicit value later in the row -- or, when the row never names one, to
        24 louder or softer, reached on the row's last note.
        """

        def clamp(value: int) -> int:
            return max(1, min(127, value))

        values: list[int | None] = [None] * len(marks)
        current = clamp(base)
        index = 0
        while index < len(marks):
            mark = marks[index]
            if mark is None:
                values[index] = current
                index += 1
                continue
            kind, value = mark
            if kind == "absolute":
                current = clamp(int(value))
                values[index] = current
                index += 1
                continue
            if kind == "delta":
                current = clamp(current + int(value))
                values[index] = current
                index += 1
                continue
            # A ramp: interpolate from the note it sits on to an anchor note.
            direction = 1 if kind == "cresc" else -1
            start = current
            end = index + 1
            while end < len(marks) and marks[end] is None:
                end += 1
            anchored = (
                end < len(marks)
                and marks[end] is not None
                and marks[end][0] in ("absolute", "delta")
            )
            if anchored:
                kind_end, value_end = marks[end]
                target = (
                    clamp(int(value_end)) if kind_end == "absolute" else clamp(current + int(value_end))
                )
                anchor = end
                resume = end + 1
            elif end < len(marks):
                # A second ramp takes over: this one climbs to it and stops.
                target = clamp(start + direction * 24)
                anchor = end
                resume = end
            else:
                target = clamp(start + direction * 24)
                anchor = len(marks) - 1
                resume = len(marks)
            if anchor <= index:
                # No room to ramp: the marking sits on the row's last note and
                # there is nothing after it to swell towards.
                values[index] = start
                index += 1
                continue
            span = anchor - index
            for step in range(span + 1):
                fraction = step / span
                values[index + step] = clamp(round(start + (target - start) * fraction))
            current = values[anchor]
            index = resume
        return values

    # -- main walk -----------------------------------------------------------

    def _check_voicing(self) -> None:
        """A misspelled strategy would otherwise fall back to the default in
        silence, which looks exactly like the setting having been honoured."""
        from .voicing import DEFAULT_STRATEGY, STRATEGIES

        name = self.options.voicing
        if name in STRATEGIES:
            return
        known = ", ".join(sorted(STRATEGIES))
        self.diagnostics.append(
            Diagnostic(
                severity="warning",
                message=f"unknown voicing {name!r}; using {DEFAULT_STRATEGY!r}",
                hint=f"voicing is one of: {known}",
            )
        )

    def _check_lyrics(self) -> None:
        from .lyrics import DEFAULT_MODE, MODES

        if self.options.lyrics in MODES:
            return
        self.diagnostics.append(
            Diagnostic(
                severity="warning",
                message=f"unknown lyrics mode {self.options.lyrics!r}; using {DEFAULT_MODE!r}",
                hint=f"lyrics is one of: {', '.join(sorted(MODES))}",
            )
        )

    def arrange(self) -> Arrangement:
        meta = self.score.meta
        bar_beats = meta.meter.beats_per_bar
        self._check_voicing()
        self._check_lyrics()
        swing = self.options.swing if self.options.swing is not None else meta.swing
        lyrics: list[LyricEvent] = []
        chords: list[ChordEvent] = []
        section_starts: list[tuple[str, float]] = []

        cursor = 0.0
        fallback_index = 0
        unit = SUBDIVISION_UNITS.get(str(meta.subdivision).lower(), 0.5)

        for section in self.score.sections:
            playable = [
                line
                for line in section.lines
                if line.cells and line.role in {ROLE_CHORDS, ROLE_MELODY, ROLE_PLAYER, ROLE_LYRICS}
            ]
            if not playable:
                continue
            section_starts.append((section.name, cursor))
            vel_plans = self._velocity_plans(section)

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
                            grid_row=key,
                            vel_plan=vel_plans.get(id(line)),
                        )
                    offset += length
                section_beats = max(section_beats, offset - cursor)

            cursor += section_beats

        if self.options.lyrics == "bound" and lyrics:
            # Runs after the walk, because binding reads the finished grid: it
            # needs every melody onset and every lyric token already placed.
            from .lyrics import bind

            bound, diagnostics = bind(self.grid)
            lyrics = bound
            self.diagnostics.extend(diagnostics)

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
            grid=self.grid,
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
                start = bar_start + token_index * step
                out.append(LyricEvent(start=start, text=token))
                self.grid.add(token=token, row=ROLE_LYRICS, kind="text", onset=start, width=step)

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
        grid_row: str,
        vel_plan: list[int | None] | None = None,
    ) -> None:
        # pitches, start, end, slot, attack index -- the attack index is the
        # Vel: row's coordinate: the k-th attack of the row takes the k-th
        # mark, rests and sustains never consume one.
        pending: list[tuple[list[int], float, float, Slot, int]] = []

        def flush() -> None:
            for pitches, start, end, slot, attack_index in pending:
                # Swing is a playback decision, not a notation one: starts and
                # ends both remap, so a pair comes out long-short rather than
                # merely late, and nothing downstream sees a half-moved note.
                swung_start = self._swing_time(start, swing)
                swung_end = self._swing_time(end, swing)
                duration = max(swung_end - swung_start, 1e-3)
                value = velocity
                if vel_plan is not None and attack_index < len(vel_plan):
                    marked = vel_plan[attack_index]
                    if marked is not None:
                        value = marked
                if slot.velocity is not None:
                    value = slot.velocity
                if slot.velocity_delta:
                    value += slot.velocity_delta
                for pitch in pitches:
                    track.add(
                        Note(
                            start=swung_start,
                            duration=duration,
                            pitch=pitch,
                            velocity=self._velocity(value),
                        )
                    )
            pending.clear()

        if line.barred:
            groups = [(origin + index * bar_beats, cell.tokens) for index, cell in enumerate(line.cells)]
        else:
            groups = [(origin, [token for cell in line.cells for token in cell.tokens])]

        attack_index = 0
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
                # Recorded before the dispatch below, so that a rest and a
                # sustain -- which produce no note and would otherwise leave no
                # trace -- still occupy their column.
                self.grid.add(token=slot.text, row=grid_row, kind=slot.kind, onset=start, width=length)
                if slot.kind == "sustain":
                    if pending:
                        pitches, note_start, _end, slot_held, attack = pending[-1]
                        pending[-1] = (pitches, note_start, start + length, slot_held, attack)
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
                    pending.append((list(notes), start, start + length, slot, attack_index))
                    attack_index += 1
                    if chords_out is not None:
                        chords_out.append(ChordEvent(start=start, duration=length, chord=slot.chord))
                elif slot.kind == "note":
                    pending.append((list(slot.pitches), start, start + length, slot, attack_index))
                    attack_index += 1
        flush()


def arrange(score: Score, options: ArrangeOptions | None = None) -> Arrangement:
    """Resolve a parsed score into timed notes."""
    return Arranger(score, options).arrange()
