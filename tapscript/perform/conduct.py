"""Bandleader directives, applied to the whole ensemble at once.

A conductor does not learn a separate correction for each player. One
instruction goes out and everybody reacts to the same thing, immediately. So a
directive is defined on the *arrival* timeline -- on what the room is meant to
hear -- and each player's emission falls out of it. Because the voices sit at
different distances, their emissions move by different amounts while the
arrivals stay together.

The vocabulary is not ours. It comes from ``SuperInstance/fleet-jepa-midi``,
where an LLM bandleader emits directives as JSON every one to four bars, and
this module reads that JSON unchanged so the two systems mean the same thing by
the same word. Nothing here opens a socket: it is a pure function from
(arrangement, directives) to a new arrangement, and somebody else wires the
transport.

    {
      "directives": [
        {"action": "lay_back", "intensity": 0.7, "duration_beats": 8,
         "offset_beats": 0, "target": ["rhythm"], "priority": "blend"}
      ],
      "energy":  {"target": 0.8, "mode": "absolute"},
      "tension": {"delta": 0.15, "mode": "relative"},
      "narrative_note": "arriving at climax"
    }

This is the timing layer, so it implements the time and feel family in full and
accepts the rest of the vocabulary without complaint -- unhandled actions are
reported, never an error, because a bandleader talking to several systems at
once should not have to know which of them cares about what.

The distinction that matters
----------------------------
``push_forward`` moves the arrival. The whole band leans ahead, hands and sound
together, and that is an expressive choice the audience hears.

``anticipate`` moves the emission and leaves the arrival exactly where it was.
The player starts the motion earlier and the note still lands on the beat --
the drummer's raised stick, the organist's head start. That is a correction,
not an effect, and nobody hears it as early.

If those two came out the same, the model would be wrong.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .solve import Shaping

# Beats per integration step when warping the timeline. Fixed rather than
# adaptive so the same score always warps to the same numbers.
STEP = 1.0 / 48.0

LAYERS = ("melody", "harmony", "rhythm", "texture", "dynamics", "ensemble")
PRIORITIES = ("blend", "override")

# The time and feel family: everything an arrival-centric model is for.
TIMING_ACTIONS = frozenset(
    {
        "lay_back",
        "push_forward",
        "anticipate",
        "drag",
        "straighten",
        "deepen_swing",
        "float",
        "lock_in",
        "double_time",
        "half_time",
    }
)


@dataclass(frozen=True)
class Feel:
    """What each action means at intensity 1.0. Numbers, not magic.

    The defaults are the middle of what players actually do, from the
    literature on expressive timing and from what a section leader will ask for
    in words:

    ``lay_back`` 25ms -- a jazz drummer sitting behind the ride sits 10 to 30ms
    back, and it reads as a mood rather than a mistake at that size.

    ``push_forward`` 18ms -- pushing is habitually subtler than laying back;
    much past 20ms and it stops sounding eager and starts sounding nervous.

    ``anticipate`` 40ms of extra preparation -- a bigger gesture into the note.
    It never moves the arrival, so it can be larger than the others safely.

    ``drag`` 60ms by the end of the window, arrived at gradually. This is the
    one that is meant to sound like a problem.

    ``deep_swing`` 0.67 on the same 0-to-1 scale the notation uses, where 1 is
    a full triplet. ``float_relax`` 0.75 leaves a quarter of the correction in
    place, which is roughly an ensemble that has stopped watching.
    """

    lay_back: float = 0.025
    push_forward: float = 0.018
    anticipate: float = 0.040
    drag: float = 0.060
    deep_swing: float = 0.67
    float_relax: float = 0.75
    double_time: float = 2.0
    half_time: float = 0.5


DEFAULT_FEEL = Feel()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class Directive:
    """One instruction, covering a window of the piece measured in beats."""

    action: str
    intensity: float = 1.0
    duration_beats: float = 0.0
    """Length of the window. Zero means "until further notice"."""

    offset_beats: float = 0.0
    """Where the window starts. Bandleader cues rarely land on a downbeat --
    "drop out on beat 3" is an offset of 2, not a bar line."""

    target: tuple[str, ...] = ()
    """Layers this applies to. Empty, or ``ensemble``, means everyone."""

    priority: str = "blend"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Directive:
        target = data.get("target") or ()
        if isinstance(target, str):
            target = (target,)
        priority = str(data.get("priority", "blend")).strip().lower()
        return cls(
            action=str(data.get("action", "")).strip().lower(),
            intensity=_clamp(float(data.get("intensity", 1.0) or 0.0), 0.0, 1.0),
            duration_beats=max(float(data.get("duration_beats", 0.0) or 0.0), 0.0),
            offset_beats=float(data.get("offset_beats", 0.0) or 0.0),
            target=tuple(str(item).strip().lower() for item in target),
            priority=priority if priority in PRIORITIES else "blend",
        )

    @property
    def handled(self) -> bool:
        return self.action in TIMING_ACTIONS

    def covers(self, beat: float) -> bool:
        if beat < self.offset_beats - 1e-9:
            return False
        if self.duration_beats <= 0.0:
            return True
        return beat < self.offset_beats + self.duration_beats - 1e-9

    def progress(self, beat: float) -> float:
        """How far through the window *beat* is, 0 to 1. Used by ``drag``."""
        if self.duration_beats <= 0.0:
            return 1.0
        return _clamp((beat - self.offset_beats) / self.duration_beats, 0.0, 1.0)

    def applies_to(self, layers: Iterable[str]) -> bool:
        if not self.target or "ensemble" in self.target:
            return True
        return bool(set(self.target) & set(layers))

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "intensity": self.intensity,
            "duration_beats": self.duration_beats,
            "offset_beats": self.offset_beats,
            "target": list(self.target),
            "priority": self.priority,
        }


@dataclass(frozen=True)
class Scalar:
    """One of the ``energy`` / ``density`` / ``tension`` knobs.

    ``absolute`` sets the value, ``relative`` nudges it. Half is the neutral
    point for an absolute target, because a score that nobody has said anything
    about is already being played at some middling energy.
    """

    target: float | None = None
    delta: float | None = None
    mode: str = "absolute"

    @classmethod
    def from_dict(cls, data: Any) -> Scalar | None:
        if not isinstance(data, dict):
            return None
        mode = str(data.get("mode", "absolute")).strip().lower()
        target = data.get("target")
        delta = data.get("delta")
        return cls(
            target=_clamp(float(target), 0.0, 1.0) if target is not None else None,
            delta=_clamp(float(delta), -1.0, 1.0) if delta is not None else None,
            mode="relative" if mode == "relative" else "absolute",
        )

    @property
    def offset(self) -> float:
        """How far from neutral this asks for, -0.5 to +0.5-ish."""
        if self.mode == "relative" or self.target is None:
            return self.delta or 0.0
        return self.target - 0.5

    def as_dict(self) -> dict[str, Any]:
        return {"target": self.target, "delta": self.delta, "mode": self.mode}


@dataclass
class DirectiveSet:
    """One message from the bandleader."""

    directives: tuple[Directive, ...] = ()
    energy: Scalar | None = None
    density: Scalar | None = None
    tension: Scalar | None = None
    narrative_note: str = ""
    revise_macro_plan: bool = False
    problems: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DirectiveSet:
        raw = data.get("directives") or []
        directives = tuple(
            Directive.from_dict(item) for item in raw if isinstance(item, dict)
        )
        problems = [
            f"directive {index}: not an object" for index, item in enumerate(raw)
            if not isinstance(item, dict)
        ]
        return cls(
            directives=tuple(item for item in directives if item.action),
            energy=Scalar.from_dict(data.get("energy")),
            density=Scalar.from_dict(data.get("density")),
            tension=Scalar.from_dict(data.get("tension")),
            narrative_note=str(data.get("narrative_note", "") or ""),
            revise_macro_plan=bool(data.get("revise_macro_plan", False)),
            problems=problems,
        )

    @classmethod
    def from_json(cls, payload: str) -> DirectiveSet:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError) as exc:
            return cls(problems=[f"could not read the directive JSON: {exc}"])
        if not isinstance(data, dict):
            return cls(problems=["the directive payload is not an object"])
        return cls.from_dict(data)

    def unhandled(self) -> list[str]:
        """Actions this layer knows about but does nothing with, in order."""
        seen: list[str] = []
        for directive in self.directives:
            if not directive.handled and directive.action not in seen:
                seen.append(directive.action)
        return seen

    def active(self, beat: float, layers: Iterable[str]) -> list[Directive]:
        layers = set(layers)
        return [
            directive
            for directive in self.directives
            if directive.handled and directive.covers(beat) and directive.applies_to(layers)
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "directives": [directive.as_dict() for directive in self.directives],
            "energy": self.energy.as_dict() if self.energy else None,
            "density": self.density.as_dict() if self.density else None,
            "tension": self.tension.as_dict() if self.tension else None,
            "narrative_note": self.narrative_note,
            "revise_macro_plan": self.revise_macro_plan,
            "unhandled": self.unhandled(),
            "problems": list(self.problems),
        }


def read(payload: Any) -> DirectiveSet:
    """Accept whatever the caller has: JSON text, a dict, or a built set."""
    if isinstance(payload, DirectiveSet):
        return payload
    if isinstance(payload, str):
        return DirectiveSet.from_json(payload)
    if isinstance(payload, dict):
        return DirectiveSet.from_dict(payload)
    if isinstance(payload, Sequence):
        items = list(payload)
        if all(isinstance(item, Directive) for item in items):
            return DirectiveSet(directives=tuple(items))
        return DirectiveSet.from_dict({"directives": items})
    return DirectiveSet(problems=[f"cannot read directives from {type(payload).__name__}"])


# --------------------------------------------------------------------------
# layers
# --------------------------------------------------------------------------

INSTRUMENT_LAYERS: tuple[tuple[str, str], ...] = (
    ("drum", "rhythm"),
    ("perc", "rhythm"),
    ("timpani", "rhythm"),
    ("bass", "rhythm"),
    ("pad", "texture"),
    ("string", "texture"),
    ("choir", "texture"),
    ("organ", "harmony"),
    ("piano", "harmony"),
    ("guitar", "harmony"),
    ("lead", "melody"),
    ("voice", "melody"),
    ("flute", "melody"),
)


def layers_for(track: Any) -> set[str]:
    """Which layers a voice belongs to, for directive targeting.

    A rough mapping and deliberately so: a bandleader saying "rhythm" means the
    section that keeps time, and on any given stage that is a judgement call.
    Every voice is also in ``ensemble``, so an untargeted directive reaches all
    of them.
    """
    found = {"ensemble"}
    role = getattr(track, "role", "")
    if role == "melody":
        found.add("melody")
    elif role == "chords":
        found.add("harmony")
    if getattr(track, "is_drum", False):
        found.add("rhythm")
    text = f"{getattr(track, 'name', '')} {getattr(track, 'instrument', '')}".lower()
    for hint, layer in INSTRUMENT_LAYERS:
        if hint in text:
            found.add(layer)
    if found == {"ensemble"}:
        found.add("texture")
    return found


# --------------------------------------------------------------------------
# blending
# --------------------------------------------------------------------------


def _blend(contributions: list[tuple[float, float, str]], baseline: float) -> float:
    """Interpolate several directives' opinions of one number.

    ``blend`` is the intensity-weighted mean, so two directives pulling opposite
    ways meet somewhere sensible. An ``override`` directive removes the blenders
    from the conversation entirely rather than out-shouting them.
    """
    if not contributions:
        return baseline
    overriding = [item for item in contributions if item[2] == "override"]
    active = overriding or contributions
    weight = sum(item[1] for item in active)
    if weight <= 0.0:
        return baseline
    return sum(value * share for value, share, _priority in active) / weight


def _shaping(active: list[Directive], beat: float, feel: Feel) -> Shaping:
    """Turn the directives in force at one moment into a solver shaping."""
    shift: list[tuple[float, float, str]] = []
    preparation: list[tuple[float, float, str]] = []
    alignment: list[tuple[float, float, str]] = []
    own_feel: list[tuple[float, float, str]] = []

    for directive in active:
        share, priority = directive.intensity, directive.priority
        if directive.action == "lay_back":
            shift.append((feel.lay_back * directive.intensity, share, priority))
        elif directive.action == "push_forward":
            shift.append((-feel.push_forward * directive.intensity, share, priority))
        elif directive.action == "drag":
            # Lateness that accumulates rather than arriving all at once.
            depth = feel.drag * directive.intensity * directive.progress(beat)
            shift.append((depth, share, priority))
        elif directive.action == "anticipate":
            preparation.append((feel.anticipate * directive.intensity, share, priority))
        elif directive.action == "float":
            alignment.append((1.0 - feel.float_relax * directive.intensity, share, priority))
        elif directive.action == "lock_in":
            alignment.append((1.0, share, priority))
            own_feel.append((1.0 - directive.intensity, share, priority))

    return Shaping(
        feel=_blend(shift, 0.0),
        preparation=_blend(preparation, 0.0),
        alignment=_clamp(_blend(alignment, 1.0), 0.0, 1.0),
        feel_scale=_clamp(_blend(own_feel, 1.0), 0.0, 1.0),
    )


def _swing_target(active: list[Directive], written: float, feel: Feel) -> float:
    """Where the swing should be, given who is asking. ``written`` is the file's."""
    wanted: list[tuple[float, float, str]] = []
    for directive in active:
        if directive.action == "straighten":
            wanted.append((written * (1.0 - directive.intensity), directive.intensity, directive.priority))
        elif directive.action == "deepen_swing":
            deeper = written + (feel.deep_swing - written) * directive.intensity
            wanted.append((deeper, directive.intensity, directive.priority))
    return _clamp(_blend(wanted, written), 0.0, 1.0)


class TimeMap:
    """The written timeline mapped onto the conducted one.

    ``double_time`` and ``half_time`` scale the subdivision inside their window.
    A stretch of music running at factor ``f`` takes ``1/f`` as long, so the map
    is the running integral of ``1/f``. It is built once over a fixed grid and
    interpolated, which keeps it monotone and keeps repeated runs identical.
    """

    def __init__(self, windows: Sequence[tuple[float, float, float]], total: float) -> None:
        self.windows = list(windows)
        self.total = max(total, 0.0)
        self._grid: list[float] = [0.0]
        self._mapped: list[float] = [0.0]
        # Nothing bends the timeline: stay the exact identity rather than
        # accumulating rounding error across a few thousand steps of 1.0.
        steps = int(math.ceil(self.total / STEP)) if self.windows and self.total > 0 else 0
        running = 0.0
        previous = 1.0 / self.factor(0.0)
        for index in range(1, steps + 1):
            beat = index * STEP
            current = 1.0 / self.factor(beat)
            running += 0.5 * (previous + current) * STEP
            previous = current
            self._grid.append(beat)
            self._mapped.append(running)

    def factor(self, beat: float) -> float:
        """Multiplier on the written tempo at a written beat."""
        value = 1.0
        for start, span, factor in self.windows:
            if beat < start - 1e-9:
                continue
            if span > 0.0 and beat >= start + span - 1e-9:
                continue
            value *= factor
        return max(value, 0.05)

    def __call__(self, beat: float) -> float:
        if not self._grid or beat <= 0.0:
            return beat
        if beat >= self._grid[-1]:
            # Past the last window the timeline runs at the written tempo again.
            return self._mapped[-1] + (beat - self._grid[-1])
        index = min(int(beat / STEP), len(self._grid) - 2)
        low, high = self._grid[index], self._grid[index + 1]
        fraction = 0.0 if high <= low else (beat - low) / (high - low)
        return self._mapped[index] + fraction * (self._mapped[index + 1] - self._mapped[index])

    def inverse(self, beat: float) -> float:
        """Conducted beat back to written beat, by bisection over a monotone map."""
        if not self.windows:
            return beat
        low, high = 0.0, max(self.total, beat) + 1.0
        for _ in range(40):
            middle = 0.5 * (low + high)
            if self(middle) < beat:
                low = middle
            else:
                high = middle
        return 0.5 * (low + high)


def _windows(directives: DirectiveSet, feel: Feel) -> list[tuple[float, float, float]]:
    out: list[tuple[float, float, float]] = []
    for directive in directives.directives:
        if directive.action == "double_time":
            factor = 1.0 + (feel.double_time - 1.0) * directive.intensity
        elif directive.action == "half_time":
            factor = 1.0 + (feel.half_time - 1.0) * directive.intensity
        else:
            continue
        out.append((directive.offset_beats, directive.duration_beats, factor))
    return out


def apply(
    arrangement: Any,
    directives: Any,
    frame: str = "",
    feel: Feel = DEFAULT_FEEL,
) -> Any:
    """Apply a bandleader's directives and re-solve everybody's emissions.

    *directives* is the JSON above, as text, as a dict, as a
    :class:`DirectiveSet` or as a list of :class:`Directive`. The arrangement is
    copied, so the written one is left alone.

    Arrival times move together because the directives are applied to them
    directly. Emission times move by different amounts per voice, because each
    voice's correction is a fixed number of seconds and the number of beats that
    buys changes with the tempo. Actions outside the time and feel family are
    recorded as diagnostics and otherwise ignored.

    Of the three scalars, ``energy`` scales velocities and ``tension`` shortens
    notes. ``density`` is read and reported but does nothing here: it asks for
    more or fewer notes, and moving notes around is all this layer can do.
    """
    from copy import deepcopy

    from ..notation.ir import Diagnostic
    from . import solve as solver

    reading = read(directives)
    conducted = deepcopy(arrangement)

    for problem in reading.problems:
        conducted.diagnostics.append(Diagnostic(severity="warning", message=f"conduct: {problem}"))
    for action in reading.unhandled():
        conducted.diagnostics.append(
            Diagnostic(
                severity="info",
                message=f"conduct: nothing in the timing layer acts on {action!r}",
                hint="the time and feel family is: " + ", ".join(sorted(TIMING_ACTIONS)),
            )
        )

    written_swing = float(getattr(conducted.meta, "swing", 0.0) or 0.0)
    time_map = TimeMap(_windows(reading, feel), conducted.total_beats)
    energy = reading.energy.offset if reading.energy else 0.0
    tension = reading.tension.offset if reading.tension else 0.0

    for track in conducted.tracks:
        layers = layers_for(track)
        for note in track.notes:
            written = note.start
            active = reading.active(written, layers)
            # Swing sits on the written grid, so it is applied before the
            # timeline is stretched rather than after.
            target = _swing_target(active, written_swing, feel)
            swung = written + _swing_shift(written, written_swing, target)
            start = time_map(swung)
            end = time_map(swung + note.duration)
            note.start = start
            note.duration = max((end - start) * max(1.0 - 0.4 * tension, 0.1), 1e-3)
            note.velocity = max(1, min(127, int(round(note.velocity * (1.0 + energy)))))
        track.sort()

    for lyric in conducted.lyrics:
        lyric.start = time_map(lyric.start)
    for chord in conducted.chords:
        end = time_map(chord.start + chord.duration)
        chord.start = time_map(chord.start)
        chord.duration = max(end - chord.start, 1e-3)
    conducted.section_starts = [(name, time_map(beat)) for name, beat in conducted.section_starts]

    layers_by_voice = {track.name.strip().lower(): layers_for(track) for track in conducted.tracks}
    written_tempo = float(conducted.meta.tempo or 100.0)

    def tempo_at(beat: float) -> float:
        # The solver converts each voice's correction from seconds to beats, so
        # it needs the tempo where the note now lands, not the written one.
        return written_tempo * time_map.factor(time_map.inverse(beat))

    def shaping_at(voice: str, beat: float) -> Shaping:
        written = time_map.inverse(beat)
        return _shaping(reading.active(written, layers_by_voice.get(voice, {"ensemble"})), written, feel)

    solver.apply_to(conducted, frame=frame, tempo_at=tempo_at, shaping_at=shaping_at)
    return conducted


def _swing_shift(beat: float, written: float, target: float) -> float:
    """Move an off-beat between two swing settings.

    The arranger delays an off-beat by ``swing / 6`` of a beat, so undoing that
    much finds where the note was written and tells us whether it is one of the
    notes a swing setting is about.
    """
    if abs(target - written) < 1e-9:
        return 0.0
    position = (beat - written / 6.0) % 1.0
    if abs(position - 0.5) < 0.05:
        return (target - written) / 6.0
    return 0.0


def describe(directives: Any) -> str:
    """A one-paragraph reading of a directive message, for a person."""
    reading = read(directives)
    lines: list[str] = []
    for directive in reading.directives:
        window = (
            f"from beat {directive.offset_beats:g}"
            + (f" for {directive.duration_beats:g}" if directive.duration_beats else " onwards")
        )
        target = ", ".join(directive.target) or "everyone"
        mark = "" if directive.handled else "  (not a timing action; ignored here)"
        lines.append(
            f"  {directive.action} at {directive.intensity:.2f} on {target}, {window}, "
            f"{directive.priority}{mark}"
        )
    for name in ("energy", "density", "tension"):
        scalar = getattr(reading, name)
        if scalar is not None:
            value = scalar.target if scalar.target is not None else scalar.delta
            lines.append(f"  {name}: {scalar.mode} {value}")
    if reading.narrative_note:
        lines.append(f"  note: {reading.narrative_note}")
    for problem in reading.problems:
        lines.append(f"  problem: {problem}")
    return "\n".join(lines) or "  (nothing to do)"


__all__ = [
    "DEFAULT_FEEL",
    "Directive",
    "DirectiveSet",
    "Feel",
    "LAYERS",
    "Scalar",
    "TIMING_ACTIONS",
    "TimeMap",
    "apply",
    "describe",
    "layers_for",
    "read",
]
