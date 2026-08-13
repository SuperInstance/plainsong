"""A gesture, applied to the whole ensemble at once.

A conductor does not learn a separate correction for each player. One gesture
goes out and everybody reacts to the same thing, immediately. The gesture is
therefore defined on the *arrival* timeline -- on what the room is meant to hear
-- and the emission times fall out of it per voice.

The interesting part is what that does to the players. A tempo change does not
move everyone's hands by the same amount, because each player's lead is a fixed
number of milliseconds and a beat is not. Shorten the beats and that lead
becomes a bigger slice of one -- much bigger for the organ at the back than for
the timpanist, whose lead is small to begin with. The arrivals stay together
through all of it. That is not a rule anyone wrote into this module; it comes
out of solving in seconds and writing in beats.

Three gestures are modelled, which between them cover what a stick can say:

``rubato``
    a tempo curve -- the timeline itself stretches or compresses

``swell``
    a dynamic curve -- velocities rise and fall

``lean``
    an articulation curve -- notes are held longer or shorter without moving
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Sequence

# Beats per integration step when warping the timeline. Fixed rather than
# adaptive so the same score always warps to the same numbers.
STEP = 1.0 / 48.0

SHAPES = ("arch", "ramp", "fall", "step")
KINDS = ("rubato", "swell", "lean")


@dataclass(frozen=True)
class Gesture:
    """One shaped instruction, covering a span of the piece in beats."""

    kind: str = "rubato"
    start: float = 0.0
    span: float = 0.0
    """Length in beats. Zero means "to the end of the piece"."""

    amount: float = 0.0
    """Depth at the peak of the shape, as a fraction. For ``rubato`` it is the
    tempo change (-0.2 is twenty percent slower), for ``swell`` the velocity
    change, for ``lean`` the note-length change."""

    shape: str = "arch"

    def weight(self, beat: float, total: float) -> float:
        """How much of the gesture applies at *beat*, between 0 and 1."""
        span = self.span if self.span > 0 else max(total - self.start, 0.0)
        if span <= 0 or beat < self.start:
            return 0.0
        position = min((beat - self.start) / span, 1.0)
        if beat > self.start + span:
            return 0.0
        if self.shape == "ramp":
            return position
        if self.shape == "fall":
            return 1.0 - position
        if self.shape == "step":
            return 1.0
        return math.sin(math.pi * position)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "start": self.start,
            "span": self.span,
            "amount": self.amount,
            "shape": self.shape,
        }


def tempo_factor(gestures: Sequence[Gesture], beat: float, total: float) -> float:
    """Multiplier on the written tempo at a written beat. 1.0 is no change."""
    factor = 1.0
    for gesture in gestures:
        if gesture.kind == "rubato":
            factor *= 1.0 + gesture.amount * gesture.weight(beat, total)
    return max(factor, 0.05)


def velocity_factor(gestures: Sequence[Gesture], beat: float, total: float) -> float:
    factor = 1.0
    for gesture in gestures:
        if gesture.kind == "swell":
            factor *= 1.0 + gesture.amount * gesture.weight(beat, total)
    return max(factor, 0.0)


def length_factor(gestures: Sequence[Gesture], beat: float, total: float) -> float:
    factor = 1.0
    for gesture in gestures:
        if gesture.kind == "lean":
            factor *= 1.0 + gesture.amount * gesture.weight(beat, total)
    return max(factor, 0.05)


class TimeMap:
    """The written timeline mapped onto the conducted one.

    A beat whose tempo is multiplied by ``f`` takes ``1/f`` as long, so the map
    is the running integral of ``1/f``. It is built once over a fixed grid and
    interpolated, which keeps it monotone and keeps repeated runs identical.
    """

    def __init__(self, gestures: Sequence[Gesture], total: float) -> None:
        self.gestures = [gesture for gesture in gestures if gesture.kind == "rubato"]
        self.total = max(total, 0.0)
        self._grid: list[float] = [0.0]
        self._mapped: list[float] = [0.0]
        # Nothing bends the timeline: stay the exact identity rather than
        # accumulating rounding error across a few thousand steps of 1.0.
        steps = int(math.ceil(self.total / STEP)) if self.gestures and self.total > 0 else 0
        running = 0.0
        previous = 1.0 / tempo_factor(self.gestures, 0.0, self.total)
        for index in range(1, steps + 1):
            beat = index * STEP
            current = 1.0 / tempo_factor(self.gestures, beat, self.total)
            running += 0.5 * (previous + current) * STEP
            previous = current
            self._grid.append(beat)
            self._mapped.append(running)

    def __call__(self, beat: float) -> float:
        if not self._grid or beat <= 0.0:
            return beat
        if beat >= self._grid[-1]:
            # Past the last gesture the timeline runs at the written tempo again.
            return self._mapped[-1] + (beat - self._grid[-1])
        index = int(beat / STEP)
        index = min(index, len(self._grid) - 2)
        low, high = self._grid[index], self._grid[index + 1]
        fraction = 0.0 if high <= low else (beat - low) / (high - low)
        return self._mapped[index] + fraction * (self._mapped[index + 1] - self._mapped[index])


def conduct(arrangement: Any, gestures: Sequence[Gesture], frame: str = "") -> Any:
    """Apply *gestures* to an arrangement and re-solve everybody's emissions.

    The arrangement is copied, so the written one is left alone. Arrival times
    move together because the gesture is applied to them directly; emission
    times move by different amounts per voice, because each voice's correction
    is a fixed number of seconds and the number of beats that buys changes with
    the tempo.
    """
    from copy import deepcopy

    from . import solve as solver

    conducted = deepcopy(arrangement)
    gestures = [gesture for gesture in gestures if gesture.amount]
    if not gestures:
        solver.apply_to(conducted, frame=frame)
        return conducted

    total = conducted.total_beats
    time_map = TimeMap(gestures, total)

    for track in conducted.tracks:
        for note in track.notes:
            written_start, written_end = note.start, note.end
            start = time_map(written_start)
            end = time_map(written_end)
            note.start = start
            note.duration = max(
                (end - start) * length_factor(gestures, written_start, total), 1e-3
            )
            note.velocity = max(
                1, min(127, int(round(note.velocity * velocity_factor(gestures, written_start, total))))
            )
        track.sort()

    for lyric in conducted.lyrics:
        lyric.start = time_map(lyric.start)
    for chord in conducted.chords:
        end = time_map(chord.start + chord.duration)
        chord.start = time_map(chord.start)
        chord.duration = max(end - chord.start, 1e-3)
    conducted.section_starts = [(name, time_map(beat)) for name, beat in conducted.section_starts]

    # The solver converts each voice's correction from seconds to beats, so it
    # needs the tempo where the note now lands rather than the written tempo.
    written_tempo = float(conducted.meta.tempo or 100.0)
    inverse = _Inverse(time_map, total)

    def tempo_at(beat: float) -> float:
        return written_tempo * tempo_factor(gestures, inverse(beat), total)

    solver.apply_to(conducted, frame=frame, tempo_at=tempo_at)
    return conducted


class _Inverse:
    """Conducted beat back to written beat, by bisection over a monotone map."""

    def __init__(self, time_map: TimeMap, total: float) -> None:
        self.time_map = time_map
        self.total = total

    def __call__(self, beat: float) -> float:
        low, high = 0.0, max(self.total, beat) + 1.0
        for _ in range(40):
            middle = 0.5 * (low + high)
            if self.time_map(middle) < beat:
                low = middle
            else:
                high = middle
        return 0.5 * (low + high)


def parse_gesture(text: str) -> Gesture | None:
    """Read ``rubato -0.2 arch 8 16`` -- kind, amount, shape, start, span."""
    parts = text.replace(",", " ").split()
    if not parts or parts[0].lower() not in KINDS:
        return None
    gesture = Gesture(kind=parts[0].lower())
    numbers: list[float] = []
    for part in parts[1:]:
        if part.lower() in SHAPES:
            gesture = replace(gesture, shape=part.lower())
            continue
        try:
            numbers.append(float(part.rstrip("%")) / (100.0 if part.endswith("%") else 1.0))
        except ValueError:
            return None
    if numbers:
        gesture = replace(gesture, amount=numbers[0])
    if len(numbers) > 1:
        gesture = replace(gesture, start=numbers[1])
    if len(numbers) > 2:
        gesture = replace(gesture, span=numbers[2])
    return gesture
