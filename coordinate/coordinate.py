"""Scheduling backwards from when an effect should land.

Copyright (c) 2026 SuperInstance. MIT licensed -- see LICENSE beside this file.

Most scheduling says when to *act*. This says when the effect should *arrive*,
and solves backwards for when each participant has to move. That inversion is
the whole idea, and it is worth stating plainly because everything else here
follows from it:

    A written time is an arrival time.

Say four players must sound a chord together at the podium. They sit at
different distances, their instruments speak at different speeds, and some
drag by habit. If each acts on the beat, the chord arrives smeared. If each
acts early by exactly their own lag, it arrives together. The second is what
this computes.

Nothing here is about music. The same three quantities describe a boat --
a steering pump has valve lag (`actuation`), linkage backlash (`bias`), and
was tuned in conditions you are no longer in (`reference_delay` versus
`observed_delay`) -- or a camera rig, or a fleet of agents whose messages take
different times to land.

The two delay terms are the part that must not be collapsed
------------------------------------------------------------
`reference_delay` is the transport delay the plan was **compensated for**.
`observed_delay` is the delay **actually experienced** by whoever is watching
now. When they are equal the correction cancels exactly and the effect lands
where it was written. When they differ it does not, and the residue is real:
it is why a spread of zero at the tuning point becomes non-zero everywhere
else, and why a coordinated group needs a conductor rather than mutual
listening.

Collapse those two into one variable and the model becomes symmetric,
self-consistent, and a description of nothing.

`intent` survives compensation on purpose
-----------------------------------------
Swing is meant to be heard; a deliberate lead into a turn is meant to happen.
So `intent` moves the effect and is not solved away, while `lead` moves only
the action and *is* compensated. They are not the same knob and must not be
merged -- a correction and an intention look alike in the arithmetic and are
opposites in meaning.

Stdlib only, one file, no configuration. Copy it next to whatever needs it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

__all__ = [
    "Latency",
    "Participant",
    "Shaping",
    "NEUTRAL",
    "Timing",
    "Schedule",
    "schedule",
    "delay_for",
    "divide",
    "SPEED_OF_SOUND",
    "speed_of_sound",
]


# -- what a participant costs -------------------------------------------------


@dataclass(frozen=True)
class Latency:
    """How long one participant takes to turn an action into an effect.

    ``actuation``
        Seconds from beginning to act to the effect beginning. A bowed string
        speaking, a hydraulic valve opening, a model starting to emit.

    ``bias``
        Seconds of systematic offset this participant carries regardless --
        backlash in a linkage, a habitual drag, a fixed pipeline stage. Split
        from ``actuation`` because one is the cost of moving and the other is
        an error you may be able to measure away.
    """

    name: str = ""
    actuation: float = 0.0
    bias: float = 0.0
    note: str = ""


@dataclass(frozen=True)
class Participant:
    """One actor, and the two transport delays that matter to it."""

    name: str
    latency: Latency = field(default_factory=Latency)

    intent: float = 0.0
    """Seconds this participant is *meant* to be off the written time. Survives
    compensation, because it is an intention rather than an error."""

    reference_delay: float = 0.0
    """Transport delay the plan was compensated for."""

    observed_delay: float = 0.0
    """Transport delay actually experienced by the current observer. Equal to
    ``reference_delay`` means observing from the point the plan was built for."""


@dataclass(frozen=True)
class Shaping:
    """A directive applied to every participant at one moment.

    ``intent_shift``
        Seconds added to the effect, and so to the action too. The whole group
        leaning early or late together; the gaps between them do not change.

    ``lead``
        Extra seconds of preparation. The action moves earlier by exactly this
        and the effect does not move at all, because it is compensated.

    ``alignment``
        How much of the correction is actually applied, 0 to 1. One is a group
        that has it right; lower values let the effects spread apart, which is
        what a degraded or distrusted calibration looks like.

    ``intent_scale``
        Scales each participant's own ``intent``, so a directive can pull
        individuals onto one instant without discarding the group shift.
    """

    intent_shift: float = 0.0
    lead: float = 0.0
    alignment: float = 1.0
    intent_scale: float = 1.0


NEUTRAL = Shaping()


# -- the answer ---------------------------------------------------------------


@dataclass(frozen=True)
class Timing:
    """When one participant must act, and when its effect reaches the observer.

    Both are offsets in seconds from the written time. ``act_at`` is normally
    negative: everyone moves early. ``effect_at`` of zero means the effect
    lands exactly where it was written.
    """

    participant: Participant
    act_at: float
    effect_at: float

    @property
    def name(self) -> str:
        return self.participant.name

    def as_dict(self) -> dict[str, object]:
        return {
            "participant": self.name,
            "profile": self.participant.latency.name,
            "actuation_ms": round(self.participant.latency.actuation * 1000.0, 1),
            "bias_ms": round(self.participant.latency.bias * 1000.0, 1),
            "intent_ms": round(self.participant.intent * 1000.0, 1),
            "reference_delay_ms": round(self.participant.reference_delay * 1000.0, 1),
            "observed_delay_ms": round(self.participant.observed_delay * 1000.0, 1),
            "act_at_ms": round(self.act_at * 1000.0, 1),
            "effect_at_ms": round(self.effect_at * 1000.0, 1),
        }


@dataclass(frozen=True)
class Schedule:
    """Every participant's timing, as seen from one observation point."""

    timings: dict[str, Timing] = field(default_factory=dict)
    compensated: bool = True

    @property
    def spread(self) -> float:
        """Seconds between the earliest and latest effect of one written time.

        Zero when every observed delay matches its reference -- which is the
        observation point the plan was built for, and nowhere else. Reading
        this live tells you how far you are from the conditions you tuned in.
        """
        if not self.timings:
            return 0.0
        landings = [timing.effect_at for timing in self.timings.values()]
        return max(landings) - min(landings)

    def __iter__(self) -> Iterable[Timing]:
        return iter(self.timings.values())

    def __len__(self) -> int:
        return len(self.timings)

    def as_dict(self) -> dict[str, object]:
        return {
            "compensated": self.compensated,
            "spread_ms": round(self.spread * 1000.0, 1),
            "participants": [timing.as_dict() for timing in self.timings.values()],
        }


def solve_one(
    participant: Participant,
    shaping: Shaping = NEUTRAL,
    compensate: bool = True,
) -> Timing:
    """The equation, and the only place it is written down.

        act    = intent·scale + shift − alignment·(actuation + lead + reference + bias)
        effect = act + actuation + lead + bias + observed

    With ``alignment`` at one and the observer at the reference point, the
    second line cancels the first and the effect lands exactly where it was
    written -- give or take the intent, which is meant to be seen.

    ``compensate=False`` drops the correction entirely: participants act on the
    written time and the effects land wherever the physics puts them. That is
    the honest default for a plan that never declared any latencies.
    """
    alignment = shaping.alignment if compensate else 0.0
    latency = participant.latency

    correction = latency.actuation + shaping.lead + participant.reference_delay + latency.bias
    act = participant.intent * shaping.intent_scale + shaping.intent_shift - alignment * correction
    effect = act + latency.actuation + shaping.lead + latency.bias + participant.observed_delay

    return Timing(participant=participant, act_at=act, effect_at=effect)


def schedule(
    participants: Sequence[Participant],
    shaping: Shaping = NEUTRAL,
    compensate: bool = True,
) -> Schedule:
    """Solve every participant against one observation point."""
    return Schedule(
        timings={p.name: solve_one(p, shaping, compensate) for p in participants},
        compensated=compensate,
    )


# -- turning a distance into a delay ------------------------------------------

SPEED_OF_SOUND = 343.2
"""Metres per second in air at 20 degrees. A default, not an assumption."""


def speed_of_sound(temperature_c: float = 20.0) -> float:
    """``331.3 · sqrt(1 + T/273.15)`` -- 343.2 m/s at 20 degrees."""
    return 331.3 * (1.0 + temperature_c / 273.15) ** 0.5


def delay_for(distance: float, speed: float = SPEED_OF_SOUND) -> float:
    """Seconds for something to cross ``distance`` at ``speed``.

    The medium is a parameter because it is the only physical assumption in
    this file. Sound in air is the default; a signal on a wire, a hydraulic
    line, or a network hop is the same arithmetic with a different constant --
    and where there is no distance at all, set the delays directly and never
    call this.
    """
    if speed <= 0.0:
        raise ValueError("speed must be positive")
    return distance / speed


# -- dividing an interval -----------------------------------------------------

_EPSILON = 1e-9


def divide(count: int, span: float = 1.0, start: float = 0.0) -> list[float]:
    """Where ``count`` items fall when they divide ``span`` between them.

    The rule is that the interval is one interval long and its contents divide
    it: three items are thirds, twelve are twelfths, and a thirteenth cannot
    spill into the next one. Positions are computed from ``start`` rather than
    accumulated, because accumulation drifts and the drift is invisible until
    something far away lands on the wrong side of a boundary.
    """
    if count <= 0:
        return []
    width = span / count
    return [start + index * width for index in range(count)]


def index_at(position: float, count: int, span: float = 1.0, start: float = 0.0) -> int:
    """Which of ``count`` slots ``position`` falls in.

    Nudged before flooring. Positions are produced by division, so a boundary
    arrives as ``0.29999999999999993`` about as often as ``0.3``, and a bare
    floor puts it in the slot below.
    """
    if count <= 0:
        raise ValueError("count must be positive")
    if span <= 0.0:
        raise ValueError("span must be positive")
    offset = (position - start) / span * count
    return max(0, min(count - 1, int(offset + _EPSILON)))
