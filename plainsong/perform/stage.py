"""Where everyone is standing, and how long sound takes to get from them to you.

The stage is a plan view in metres. The origin is the podium, ``+y`` points out
towards the audience and ``+x`` is to the conductor's right, so a first-violin
desk at the front left of the platform is around ``-3,1`` and a timpanist at the
back right is around ``4,-6``. The numbers only ever matter relative to each
other, so pacing the room out roughly is enough.

Sound covers 343 metres a second at 20 degrees, which is 2.9 milliseconds a
metre. Twenty metres across a large platform is 58ms -- longer than a
thirty-second note at 120bpm, and far longer than an ensemble's own tolerance
for being out of time.

This module holds only geometry and the ``[Stage]`` block's data. The solver
that turns it into note timings is :mod:`plainsong.perform.solve`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .profiles import SpeechProfile, profile_for_name, profile_for_program

# The frame that means "do not compensate at all": what the compiler did before
# this feature existed, and what a file without a [Stage] block still does.
FRAME_SCORE = "score"

# Listeners every stage has unless it says otherwise. The conductor stands on
# the podium; the audience reference point is twelve metres out in front of it.
DEFAULT_LISTENERS: dict[str, tuple[float, float]] = {
    "conductor": (0.0, 0.0),
    "audience": (0.0, 12.0),
}

PLAYER_FRAME_PREFIX = "player:"

_NUMBER = r"[-+]?\d+(?:\.\d+)?"
POSITION_RE = re.compile(rf"^\s*({_NUMBER})\s*[, ]\s*({_NUMBER})\s*$")
DURATION_RE = re.compile(rf"^\s*({_NUMBER})\s*(ms|msec|s|sec|seconds?)?\s*$", re.IGNORECASE)
FIELD_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_-]*)\s*(?:[:=]\s*|\s+)(.*)$")

TRUE_WORDS = {"on", "yes", "true", "1", "compensate", "solve"}
FALSE_WORDS = {"off", "no", "false", "0", "none", "raw"}


def speed_of_sound(temperature_c: float = 20.0) -> float:
    """Speed of sound in dry air, metres per second.

    The usual approximation, ``331.3 * sqrt(1 + T/273.15)``: 343.2 m/s at 20
    degrees. Humidity and altitude move it by well under a percent, which is
    smaller than the error in knowing where anybody is standing.
    """
    return 331.3 * math.sqrt(1.0 + max(temperature_c, -273.0) / 273.15)


def parse_position(text: str) -> tuple[float, float] | None:
    """Read ``4,-6`` or ``4 -6`` as a position in metres."""
    match = POSITION_RE.match(text)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def parse_duration(text: str) -> float | None:
    """Read ``-6ms``, ``0.045s`` or a bare number of milliseconds, in seconds."""
    match = DURATION_RE.match(text)
    if not match:
        return None
    value = float(match.group(1))
    unit = (match.group(2) or "ms").lower()
    return value if unit.startswith("s") else value / 1000.0


@dataclass(frozen=True)
class Placement:
    """One voice's position on the stage and how it speaks."""

    name: str
    position: tuple[float, float] = (0.0, 0.0)
    speech_name: str = ""
    speech_override: float | None = None
    p_center_override: float | None = None
    feel: float = 0.0
    """Deliberate musical deviation, in seconds. Negative pushes ahead of the
    beat, positive lays back. It is expressive, not corrective: the solver adds
    it after the correction and it is meant to be heard."""

    def profile(self, program: int = 0, is_drum: bool = False) -> SpeechProfile:
        """The profile for this voice: what it declared, else its GM program."""

        named = profile_for_name(self.speech_name) if self.speech_name else None
        base = named or profile_for_program(program, is_drum)
        if self.speech_override is None and self.p_center_override is None:
            return base
        return SpeechProfile(
            name=base.name,
            speech=base.speech if self.speech_override is None else self.speech_override,
            p_center=base.p_center if self.p_center_override is None else self.p_center_override,
            note=base.note,
        )


@dataclass
class Stage:
    """A ``[Stage]`` block: who is where, and who the music is written for."""

    listener: str = "conductor"
    """The reference frame the composer wrote in. Written times are the times
    sound is meant to *arrive* here."""

    temperature: float = 20.0
    compensate: bool = True
    listeners: dict[str, tuple[float, float]] = field(
        default_factory=lambda: dict(DEFAULT_LISTENERS)
    )
    placements: dict[str, Placement] = field(default_factory=dict)
    problems: list[tuple[int, str]] = field(default_factory=list)
    """(line number, message) for anything in the block that could not be read."""

    @property
    def speed(self) -> float:
        return speed_of_sound(self.temperature)

    def placement(self, name: str) -> Placement | None:
        return self.placements.get(name.strip().lower())

    def position(self, name: str) -> tuple[float, float]:
        """Where a voice stands. Unplaced voices are treated as at the podium."""
        found = self.placement(name)
        return found.position if found else (0.0, 0.0)

    def listener_position(self, frame: str = "") -> tuple[float, float] | None:
        """Resolve a frame name to a point, or ``None`` for the score frame.

        Accepts a named listener (``conductor``, ``audience``), ``player:<name>``
        for what one player hears, and ``score`` for no compensation at all.
        An unknown name falls back to the stage's own listener.
        """
        key = (frame or self.listener or "conductor").strip().lower()
        if key == FRAME_SCORE:
            return None
        if key.startswith(PLAYER_FRAME_PREFIX):
            player = key[len(PLAYER_FRAME_PREFIX) :].strip()
            found = self.placement(player)
            return found.position if found else None
        if key in self.listeners:
            return self.listeners[key]
        found = self.placement(key)
        if found is not None:
            return found.position
        return self.listeners.get(self.listener.strip().lower(), (0.0, 0.0))

    def knows_frame(self, frame: str) -> bool:
        """Whether a ``--frame`` name means anything on this stage.

        Worth asking separately, because a typo in a player's name would
        otherwise fall back to the stage's own listener and quietly report the
        wrong desk's numbers.
        """
        key = (frame or "").strip().lower()
        if not key or key == FRAME_SCORE:
            return True
        if key.startswith(PLAYER_FRAME_PREFIX):
            return key[len(PLAYER_FRAME_PREFIX) :].strip() in self.placements
        return key in self.listeners or key in self.placements

    def distance(self, voice: str, frame: str = "") -> float:
        """Metres from a voice to a listener. Zero if the frame is the score."""
        target = self.listener_position(frame)
        if target is None:
            return 0.0
        x, y = self.position(voice)
        return math.hypot(x - target[0], y - target[1])

    def propagation(self, voice: str, frame: str = "") -> float:
        """Seconds for sound to travel from a voice to a listener."""
        return self.distance(voice, frame) / self.speed

    def frames(self) -> list[str]:
        """Every frame worth reporting on: the named listeners, then each desk."""
        names = list(self.listeners)
        names.extend(f"{PLAYER_FRAME_PREFIX}{name}" for name in sorted(self.placements))
        return names

    def as_dict(self) -> dict[str, object]:
        return {
            "listener": self.listener,
            "temperature": self.temperature,
            "compensate": self.compensate,
            "speed_of_sound": round(self.speed, 2),
            "listeners": {name: list(point) for name, point in self.listeners.items()},
            "voices": {
                name: {
                    "position": list(placement.position),
                    "speech": placement.speech_name,
                    "feel_ms": round(placement.feel * 1000.0, 1),
                }
                for name, placement in self.placements.items()
            },
        }


def _split_fields(text: str) -> list[str]:
    return [part.strip() for part in text.split("|") if part.strip()]


def placement_from_fields(name: str, fields: list[str]) -> tuple[Placement, list[str]]:
    """Build a placement from ``pos 4,-6``-style fields. Returns it and any problems."""
    position = (0.0, 0.0)
    speech_name = ""
    speech_override: float | None = None
    p_center_override: float | None = None
    feel = 0.0
    problems: list[str] = []

    for chunk in fields:
        match = FIELD_RE.match(chunk)
        if not match:
            problems.append(f"could not read {chunk!r}")
            continue
        key = match.group(1).strip().lower().replace(" ", "-")
        value = match.group(2).strip()
        if key in {"pos", "position", "at"}:
            point = parse_position(value)
            if point is None:
                problems.append(f"position {value!r} is not 'x,y' in metres")
            else:
                position = point
        elif key in {"speech", "onset", "attack"}:
            seconds = parse_duration(value)
            if profile_for_name(value) is not None:
                speech_name = value.strip().lower()
            elif seconds is not None:
                speech_override = seconds
            else:
                problems.append(f"unknown speech profile {value!r}")
        elif key in {"p-center", "p-centre", "pcenter", "pcentre"}:
            seconds = parse_duration(value)
            if seconds is None:
                problems.append(f"p-center {value!r} is not a duration")
            else:
                p_center_override = seconds
        elif key == "feel":
            seconds = parse_duration(value)
            if seconds is None:
                problems.append(f"feel {value!r} is not a duration such as -6ms")
            else:
                feel = seconds
        else:
            problems.append(f"unknown stage field {key!r}")

    placement = Placement(
        name=name,
        position=position,
        speech_name=speech_name,
        speech_override=speech_override,
        p_center_override=p_center_override,
        feel=feel,
    )
    return placement, problems


def read_stage_line(stage: Stage, text: str, line_number: int = 0) -> None:
    """Apply one line of a ``[Stage]`` block. Problems are recorded, never raised.

    A line is either a setting (``listener: audience``, ``temperature: 18``), a
    listener position (``audience: 0,20``) or a voice
    (``@organ: pos 0,-12 | speech: organ-large``).
    """
    line = text.strip()
    if not line or line.startswith("//") or line.startswith("#"):
        return

    if line.startswith("@"):
        # The name runs to the first colon or pipe, whichever comes first, so
        # both `@organ: pos 0,-12` and `@organ | pos 0,-12` read the same way.
        body = line[1:]
        colon, pipe = body.find(":"), body.find("|")
        cut = min(index for index in (colon, pipe, len(body)) if index >= 0)
        name = body[:cut].strip().lower()
        rest = body[cut + 1 :] if cut < len(body) else ""
        if not name:
            stage.problems.append((line_number, "stage row has no player name"))
            return
        placement, problems = placement_from_fields(name, _split_fields(rest))
        stage.placements[name] = placement
        for problem in problems:
            stage.problems.append((line_number, f"@{name}: {problem}"))
        return

    key, separator, value = line.partition(":")
    if not separator:
        stage.problems.append((line_number, f"could not read stage line {line!r}"))
        return
    key = key.strip().lower()
    value = value.strip()

    if key == "listener":
        stage.listener = value.lower() or "conductor"
    elif key in {"temperature", "temp"}:
        number = re.search(_NUMBER, value)
        if number is None:
            stage.problems.append((line_number, f"temperature {value!r} is not a number"))
        else:
            stage.temperature = float(number.group(0))
    elif key in {"compensate", "compensation", "solve"}:
        word = value.lower()
        if word in TRUE_WORDS:
            stage.compensate = True
        elif word in FALSE_WORDS:
            stage.compensate = False
        else:
            stage.problems.append((line_number, f"compensate {value!r} is not on or off"))
    else:
        point = parse_position(value)
        if point is None:
            stage.problems.append((line_number, f"unknown stage setting {key!r}"))
        else:
            stage.listeners[key] = point
