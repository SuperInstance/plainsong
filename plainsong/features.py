"""Sixteen numbers per bar.

A model that has to react to music needs a fixed-width view of it. This turns
an :class:`~plainsong.notation.ir.Arrangement` into one vector per bar, in the
order :data:`FEATURE_NAMES`, each value in roughly ``[0, 1]`` (``contour``
alone is signed). The layout is the one the fleet-jepa bandleader consumes, so
a written score and a recorded performance can be described the same way, and
the notation in this repository becomes a corpus a model can be trained on.

Analysis only: no rendering, no dependencies, and no state. Raw quantities --
onsets per beat, semitones, MIDI velocities -- are divided by the references in
:data:`REFERENCES` and clipped, so a value of 1.0 means "at or past the
reference" rather than "the largest seen in this piece". Normalising against
the piece itself would make a bar's numbers depend on the bars around it, and
two agents analysing different excerpts would disagree about the same bar.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

FEATURE_NAMES = (
    "note_density",
    "avg_pitch",
    "rhythmic_complexity",
    "harmonic_tension",
    "register_spread",
    "velocity_mean",
    "velocity_std",
    "syncopation",
    "contour_direction",
    "interval_size",
    "rest_ratio",
    "chord_density",
    "bass_register",
    "treble_activity",
    "dynamic_range",
    "sustain_ratio",
)

# The raw value that normalises to 1.0. Chosen from what the notation in this
# repository actually contains rather than from theoretical extremes: sixteenth
# notes are dense, an octave is a large melodic leap, four sounding voices is a
# full texture.
REFERENCES = {
    "note_density": 4.0,  # onsets per beat
    "rhythmic_complexity": 1.0,  # stdev of inter-onset intervals, in beats
    "velocity_std": 32.0,  # MIDI velocity
    "contour_direction": 12.0,  # semitones, signed
    "interval_size": 12.0,  # semitones
    "chord_density": 6.0,  # simultaneous notes
}

MIDI_MAX = 127.0
BASS_CEILING = 48  # below this is bass register
TREBLE_FLOOR = 84  # above this is treble activity
BEAT = 1.0  # a beat, in the units the arranger works in
ON_BEAT_TOLERANCE = 1e-3
PITCH_CLASSES = 12


@dataclass(frozen=True)
class BarFeatures:
    """One bar, described."""

    bar: int
    start: float
    onsets: int
    values: dict[str, float] = field(default_factory=dict)

    @property
    def vector(self) -> list[float]:
        """The values in :data:`FEATURE_NAMES` order."""
        return [self.values[name] for name in FEATURE_NAMES]

    def as_dict(self) -> dict[str, Any]:
        return {
            "bar": self.bar,
            "start": round(self.start, 6),
            "onsets": self.onsets,
            "features": dict(self.values),
            "vector": self.vector,
        }


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _round(value: float) -> float:
    # Six places is far more than the analysis means and still gives byte-equal
    # JSON for the same input on every platform.
    return round(value + 0.0, 6)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: Sequence[float]) -> float:
    """Population standard deviation; zero for fewer than two values."""
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _entropy(counts: Iterable[int]) -> float:
    """Shannon entropy of a histogram, normalised by the entropy of a flat one."""
    counts = [count for count in counts if count > 0]
    total = sum(counts)
    if total <= 0 or len(counts) < 2:
        return 0.0
    entropy = -sum((count / total) * math.log(count / total) for count in counts)
    return entropy / math.log(PITCH_CLASSES)


def _empty(bar: int, start: float) -> BarFeatures:
    """A bar with nothing in it: silent, and every other reading undefined."""
    values = dict.fromkeys(FEATURE_NAMES, 0.0)
    values["rest_ratio"] = 1.0
    return BarFeatures(bar=bar, start=start, onsets=0, values=values)


def bar_length(arrangement: Any) -> float:
    """Bar length in beats, from the arrangement's metre."""
    beats = float(arrangement.meta.meter.beats_per_bar)
    return beats if beats > 0 else 4.0


def bar_count(arrangement: Any) -> int:
    """How many whole bars the arrangement occupies."""
    beats = float(arrangement.total_beats)
    if beats <= 0:
        return 0
    return int(math.ceil(beats / bar_length(arrangement) - 1e-9))


def extract(arrangement: Any, voice: str = "") -> list[BarFeatures]:
    """Describe every bar of *arrangement*, optionally one voice of it.

    *voice* matches a track name; empty means the whole texture, which is what
    a conductor hears and what the bandleader is given.
    """
    beats_per_bar = bar_length(arrangement)
    tracks = [
        track
        for track in arrangement.tracks
        if not voice or track.name.lstrip("@").lower() == voice.lstrip("@").lower()
    ]
    lines = [list(track.notes) for track in tracks if track.notes]
    notes = [note for line in lines for note in line]
    total = bar_count(arrangement) if not voice else _bars_for(notes, beats_per_bar)

    features: list[BarFeatures] = []
    for index in range(total):
        start = index * beats_per_bar
        features.append(_describe_bar(notes, index + 1, start, beats_per_bar, lines))
    return features


def _bars_for(notes: Sequence[Any], beats_per_bar: float) -> int:
    end = max((note.end for note in notes), default=0.0)
    return int(math.ceil(end / beats_per_bar - 1e-9)) if end > 0 else 0


def _describe_bar(
    notes: Sequence[Any],
    bar: int,
    start: float,
    length: float,
    lines: Sequence[Sequence[Any]] = (),
) -> BarFeatures:
    """The sixteen features of one bar.

    Onsets are notes that begin in the bar; a note held over the bar line still
    counts towards how full the bar sounds, which is why texture and rests are
    measured over everything that overlaps it.

    *lines* is the same notes split by voice. Melodic motion is measured inside
    a voice and then averaged: taken over the merged stream, "the interval
    between consecutive notes" is mostly the gap between the bass and the tune,
    which saturates on any piece with more than one part in it.
    """
    end = start + length
    overlapping = [note for note in notes if note.start < end - 1e-9 and note.end > start + 1e-9]
    onsets = sorted(
        (note for note in notes if start - 1e-9 <= note.start < end - 1e-9),
        key=lambda note: (note.start, note.pitch),
    )
    if not onsets and not overlapping:
        return _empty(bar, start)

    pitches = [float(note.pitch) for note in onsets]
    velocities = [float(note.velocity) for note in onsets]
    times = sorted({round(note.start, 9) for note in onsets})
    gaps = [times[i + 1] - times[i] for i in range(len(times) - 1)]
    intervals = _melodic_intervals(lines or [notes], start, end)

    sounding = sum(min(note.end, end) - max(note.start, start) for note in overlapping)
    covered = _union_length(overlapping, start, end)

    histogram = [0] * PITCH_CLASSES
    for note in onsets:
        histogram[int(note.pitch) % PITCH_CLASSES] += 1

    off_beat = sum(
        1
        for note in onsets
        if abs((note.start - start) / BEAT - round((note.start - start) / BEAT)) > ON_BEAT_TOLERANCE
    )

    values = {
        "note_density": _clip((len(onsets) / length) / REFERENCES["note_density"]),
        "avg_pitch": _clip(_mean(pitches) / MIDI_MAX),
        "rhythmic_complexity": _clip(_stdev(gaps) / REFERENCES["rhythmic_complexity"]),
        "harmonic_tension": _clip(_entropy(histogram)),
        "register_spread": _clip((max(pitches) - min(pitches)) / MIDI_MAX) if pitches else 0.0,
        "velocity_mean": _clip(_mean(velocities) / MIDI_MAX),
        "velocity_std": _clip(_stdev(velocities) / REFERENCES["velocity_std"]),
        "syncopation": (off_beat / len(onsets)) if onsets else 0.0,
        "contour_direction": _clip(_mean(intervals) / REFERENCES["contour_direction"], -1.0, 1.0),
        "interval_size": _clip(
            _mean([abs(interval) for interval in intervals]) / REFERENCES["interval_size"]
        ),
        "rest_ratio": _clip(1.0 - covered / length),
        "chord_density": _clip((sounding / length) / REFERENCES["chord_density"]),
        "bass_register": (
            sum(1 for pitch in pitches if pitch < BASS_CEILING) / len(pitches) if pitches else 0.0
        ),
        "treble_activity": (
            sum(1 for pitch in pitches if pitch > TREBLE_FLOOR) / len(pitches) if pitches else 0.0
        ),
        "dynamic_range": _clip((max(velocities) - min(velocities)) / MIDI_MAX) if velocities else 0.0,
        "sustain_ratio": (
            sum(1 for note in onsets if note.duration > BEAT) / len(onsets) if onsets else 0.0
        ),
    }
    return BarFeatures(
        bar=bar,
        start=start,
        onsets=len(onsets),
        values={name: _round(values[name]) for name in FEATURE_NAMES},
    )


def _melodic_intervals(lines: Sequence[Sequence[Any]], start: float, end: float) -> list[float]:
    """Signed steps between successive notes, taken one voice at a time."""
    intervals: list[float] = []
    for line in lines:
        within = sorted(
            (note for note in line if start - 1e-9 <= note.start < end - 1e-9),
            key=lambda note: (note.start, note.pitch),
        )
        intervals.extend(
            float(within[index + 1].pitch - within[index].pitch) for index in range(len(within) - 1)
        )
    return intervals


def _union_length(notes: Sequence[Any], start: float, end: float) -> float:
    """Total time in [start, end) with at least one note sounding."""
    spans = sorted(
        (max(note.start, start), min(note.end, end))
        for note in notes
        if note.end > start and note.start < end
    )
    covered = 0.0
    cursor = start
    for span_start, span_end in spans:
        if span_end <= cursor:
            continue
        covered += span_end - max(span_start, cursor)
        cursor = max(cursor, span_end)
    return covered


def summarise(bars: Sequence[BarFeatures]) -> dict[str, float]:
    """The mean of each feature over a run of bars."""
    if not bars:
        return dict.fromkeys(FEATURE_NAMES, 0.0)
    return {name: _round(_mean([bar.values[name] for bar in bars])) for name in FEATURE_NAMES}


def format_table(bars: Sequence[BarFeatures], width: int = 6) -> str:
    """A fixed-width table, for reading in a terminal or by a model."""
    short = [name[:width].rjust(width) for name in FEATURE_NAMES]
    lines = ["bar " + " ".join(short)]
    for bar in bars:
        cells = " ".join(f"{value:>{width}.2f}" for value in bar.vector)
        lines.append(f"{bar.bar:>3} {cells}")
    return "\n".join(lines)
