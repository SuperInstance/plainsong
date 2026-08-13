"""Solving backwards from what the listener should hear.

A written time is an *arrival* time: the moment the composer wants the sound to
reach the reference listener. Three things sit between a player acting and that
moment, so the solver subtracts all three to find when the player must act:

    arrival  = emission + speech + propagation + p_center
    emission = arrival  - speech - propagation - p_center + feel

``speech`` is the instrument taking time to sound (:mod:`.profiles`),
``propagation`` is distance over the speed of sound (:mod:`.stage`), and
``p_center`` is the ear placing the note slightly into the attack rather than at
its physical onset.

``feel`` is not part of the correction. It is a deliberate musical deviation --
negative pushes ahead of the beat, positive lays back -- and it is meant to be
heard, so it survives into the arrival time instead of cancelling out. Keeping
the two apart is the whole point: the correction makes an ensemble sound
together, and the feel makes it sound like somebody.

Everything here is in seconds until the last step, where offsets become beats at
the local tempo. That conversion is where conducting gets interesting: a fixed
74ms lead is a quarter of a beat at 200bpm and a fourteenth of one at 60, so
changing tempo moves each player's hands by a different amount while their
arrivals stay together.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from .stage import FRAME_SCORE, PLAYER_FRAME_PREFIX, Stage


@dataclass(frozen=True)
class Shaping:
    """What a conductor's directives do to one voice's solve at one moment.

    Everything a directive can change about *timing* comes through here, which
    keeps the solver the only place the equation is written down.

    ``feel``
        Seconds added to the arrival, and so to the emission as well. The whole
        ensemble leaning ahead or sitting back: ``push_forward``, ``lay_back``,
        ``drag``. The gaps between the players do not change.

    ``preparation``
        Seconds of extra speech time -- the player starting the motion earlier
        for a bigger gesture. The emission moves earlier by exactly this and the
        arrival does not move at all, because the solver compensates for it.
        This is ``anticipate``.

    ``alignment``
        How much of the correction the players are actually applying, 0 to 1.
        One is an ensemble that has it right; ``float`` relaxes it and the
        arrivals spread apart, ``lock_in`` pulls it back to one.

    ``feel_scale``
        Scales each voice's own written feel, so ``lock_in`` can pull individual
        desks onto the same instant.
    """

    feel: float = 0.0
    preparation: float = 0.0
    alignment: float = 1.0
    feel_scale: float = 1.0


NEUTRAL = Shaping()


@dataclass(frozen=True)
class VoiceTiming:
    """What one voice has to do, and what one listener gets, in seconds."""

    name: str
    position: tuple[float, float]
    profile: str
    speech: float
    p_center: float
    feel: float
    reference_distance: float
    reference_propagation: float
    observed_distance: float
    observed_propagation: float
    emission_offset: float
    """Seconds to add to the written time to get the moment the player acts.
    Normally negative: everyone acts early."""

    arrival_offset: float
    """Seconds to add to the written time to get the moment the sound reaches
    the observing listener. Zero means it lands exactly where it was written."""

    def offsets(self, shaping: Shaping = NEUTRAL, compensate: bool = True) -> tuple[float, float]:
        """(emission, arrival) offsets in seconds under a given shaping.

        The one place the equation lives:

            emission = feel - alignment * (speech + preparation + travel + p-centre)
            arrival  = emission + speech + preparation + p-centre + travel to here

        With ``alignment`` at one and the listener at the reference, the second
        line cancels the first and the arrival lands exactly where it was
        written -- give or take the feel, which is meant to be heard.
        """
        alignment = shaping.alignment if compensate else 0.0
        correction = self.speech + shaping.preparation + self.reference_propagation + self.p_center
        emission = self.feel * shaping.feel_scale + shaping.feel - alignment * correction
        arrival = (
            emission + self.speech + shaping.preparation + self.p_center + self.observed_propagation
        )
        return emission, arrival

    def as_dict(self) -> dict[str, Any]:
        return {
            "voice": self.name,
            "position": list(self.position),
            "profile": self.profile,
            "distance_m": round(self.reference_distance, 2),
            "speech_ms": round(self.speech * 1000.0, 1),
            "propagation_ms": round(self.reference_propagation * 1000.0, 1),
            "p_center_ms": round(self.p_center * 1000.0, 1),
            "feel_ms": round(self.feel * 1000.0, 1),
            "emission_ms": round(self.emission_offset * 1000.0, 1),
            "arrival_ms": round(self.arrival_offset * 1000.0, 1),
            "observed_distance_m": round(self.observed_distance, 2),
        }


@dataclass
class Solution:
    """Every voice's timing for one observation frame."""

    stage: Stage
    frame: str
    reference: str
    speed: float
    voices: dict[str, VoiceTiming] = field(default_factory=dict)
    requested: str = ""
    """What the caller asked for, when that was not a listener this stage has.
    Empty otherwise; ``frame`` always says where the listening actually
    happened."""

    lead_in: float = 0.0
    """Beats the whole piece was pushed later so that nothing has to be played
    before the file starts. Applied to emissions and arrivals alike, so it moves
    the music without changing anything inside it."""

    @property
    def unknown_frame(self) -> bool:
        return bool(self.requested)

    @property
    def spread(self) -> float:
        """Seconds between the earliest and latest arrival of a written beat."""
        if not self.voices:
            return 0.0
        offsets = [timing.arrival_offset for timing in self.voices.values()]
        return max(offsets) - min(offsets)

    def as_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame,
            "reference": self.reference,
            "speed_of_sound": round(self.speed, 2),
            "compensate": self.stage.compensate,
            "requested": self.requested,
            "spread_ms": round(self.spread * 1000.0, 1),
            "lead_in_beats": round(self.lead_in, 4),
            "voices": [timing.as_dict() for timing in self.voices.values()],
        }


def solve(
    stage: Stage,
    voices: Sequence[tuple[str, int, bool]],
    frame: str = "",
) -> Solution:
    """Work out every voice's emission and arrival offsets.

    *voices* is a sequence of ``(name, gm_program, is_drum)``. The program is
    only used to choose a speech profile when the stage did not name one.
    *frame* is where the listening happens; empty means the stage's own
    listener, and ``score`` means no compensation at all.
    """
    reference = stage.listener or "conductor"
    known = stage.knows_frame(frame)
    observation = (frame if known else reference).strip().lower() or reference.strip().lower()
    solution = Solution(
        stage=stage,
        frame=observation,
        reference=reference,
        speed=stage.speed,
        requested="" if known else frame,
    )
    if observation == FRAME_SCORE:
        return solution

    for name, program, is_drum in voices:
        placement = stage.placement(name)
        profile = (
            placement.profile(program, is_drum)
            if placement is not None
            else _unplaced_profile(program, is_drum)
        )
        feel = placement.feel if placement is not None else 0.0
        reference_distance = stage.distance(name, reference)
        reference_propagation = reference_distance / stage.speed
        observed_distance = stage.distance(name, observation)
        observed_propagation = observed_distance / stage.speed

        timing = VoiceTiming(
            name=name,
            position=stage.position(name),
            profile=profile.name,
            speech=profile.speech,
            p_center=profile.p_center,
            feel=feel,
            reference_distance=reference_distance,
            reference_propagation=reference_propagation,
            observed_distance=observed_distance,
            observed_propagation=observed_propagation,
            emission_offset=0.0,
            arrival_offset=0.0,
        )
        # Nothing shapes the plain solve: with compensation off, alignment is
        # zero and the players act on the written beat instead.
        emission_offset, arrival_offset = timing.offsets(NEUTRAL, stage.compensate)
        solution.voices[name] = replace(
            timing, emission_offset=emission_offset, arrival_offset=arrival_offset
        )
    return solution


def _unplaced_profile(program: int, is_drum: bool):
    from .profiles import profile_for_program

    return profile_for_program(program, is_drum)


def apply_to(
    arrangement: Any,
    frame: str = "",
    tempo_at: Callable[[float], float] | None = None,
    stage: Stage | None = None,
    shaping_at: Callable[[str, float], Shaping] | None = None,
) -> Solution | None:
    """Stamp emission and arrival times onto every note in an arrangement.

    Returns the :class:`Solution` used, or ``None`` when the arrangement has no
    stage and nothing should change. Notes keep their written ``start``; the two
    solved times are additional, so anything that ignores them behaves exactly
    as it did before stages existed. Pass *stage* to render against a variation
    of the written one without altering it, and *shaping_at* -- a function of
    (voice, beat) -- to let a conductor's directives bend the solve note by note.
    """
    stage = stage or getattr(arrangement.meta, "stage", None)
    if stage is None:
        return None

    solution = solve(
        stage,
        [(track.name.strip().lower(), track.program, track.is_drum) for track in arrangement.tracks],
        frame=frame,
    )
    if solution.unknown_frame:
        from ..notation.ir import Diagnostic

        arrangement.diagnostics.append(
            Diagnostic(
                severity="warning",
                message=f"nobody called {frame!r} is on this stage; listening at "
                f"{solution.frame} instead",
                hint="frames are: " + ", ".join(frames_for(stage)),
            )
        )
    if not solution.voices:
        arrangement.stage = stage
        arrangement.frame = solution.frame
        return solution

    tempo = float(getattr(arrangement.meta, "tempo", 100.0) or 100.0)

    def offsets(timing: VoiceTiming, at: float) -> tuple[float, float]:
        if shaping_at is None:
            return timing.emission_offset, timing.arrival_offset
        return timing.offsets(shaping_at(timing.name, at), stage.compensate)

    def beats(seconds: float, at: float) -> float:
        local = tempo_at(at) if tempo_at is not None else tempo
        return seconds * max(local, 1e-6) / 60.0

    # Two passes: the first finds how far before the start of the piece the
    # earliest player has to act, the second writes the times with that lead-in
    # added to everything so the file still begins at zero.
    earliest = 0.0
    for track in arrangement.tracks:
        timing = solution.voices.get(track.name.strip().lower())
        if timing is None:
            continue
        track.placement = stage.placement(track.name)
        for note in track.notes:
            emission, _arrival = offsets(timing, note.start)
            earliest = min(earliest, note.start + beats(emission, note.start))
    solution.lead_in = -earliest if earliest < 0 else 0.0

    for track in arrangement.tracks:
        timing = solution.voices.get(track.name.strip().lower())
        if timing is None:
            continue
        for note in track.notes:
            emission, arrival = offsets(timing, note.start)
            note.emission = note.start + beats(emission, note.start) + solution.lead_in
            note.arrival = note.start + beats(arrival, note.start) + solution.lead_in

    arrangement.stage = stage
    arrangement.frame = solution.frame
    arrangement.lead_in = solution.lead_in
    return solution


def analyse(arrangement: Any, frame: str = "") -> dict[str, Any]:
    """The ensemble report: who is where, what they hear, and how far apart."""
    stage = getattr(arrangement, "stage", None) or getattr(arrangement.meta, "stage", None)
    if stage is None:
        return {"stage": False, "reason": "this piece has no [Stage] block"}

    voices = [
        (track.name.strip().lower(), track.program, track.is_drum)
        for track in arrangement.tracks
    ]
    chosen = solve(stage, voices, frame=frame)

    # Standing at a desk, the reference you actually judge by is your own
    # sound, which reaches you first. This is the number a player would
    # describe as "the timpani are late".
    relative: list[dict[str, Any]] = []
    own = chosen.frame[len(PLAYER_FRAME_PREFIX) :] if chosen.frame.startswith(
        PLAYER_FRAME_PREFIX
    ) else ""
    if own and own in chosen.voices:
        anchor = chosen.voices[own].arrival_offset
        relative = [
            {"voice": timing.name, "ms": round((timing.arrival_offset - anchor) * 1000.0, 1)}
            for timing in chosen.voices.values()
            if timing.name != own
        ]
        relative.sort(key=lambda item: -item["ms"])

    elsewhere = []
    for candidate in stage.frames():
        if candidate == chosen.frame:
            continue
        other = solve(stage, voices, frame=candidate)
        latest = max(other.voices.values(), key=lambda t: t.arrival_offset, default=None)
        elsewhere.append(
            {
                "frame": candidate,
                "spread_ms": round(other.spread * 1000.0, 1),
                "latest": latest.name if latest else "",
                "latest_ms": round(latest.arrival_offset * 1000.0, 1) if latest else 0.0,
            }
        )

    return {
        "stage": True,
        "title": getattr(arrangement.meta, "title", "") or "(untitled)",
        "tempo": getattr(arrangement.meta, "tempo", 0.0),
        "voices": len(voices),
        "geometry": stage.as_dict(),
        "solution": chosen.as_dict(),
        "relative_to_own_sound": relative,
        "elsewhere": elsewhere,
        "problems": [f"line {line}: {message}" for line, message in stage.problems],
    }


def format_report(report: dict[str, Any]) -> str:
    """The report as text, for the terminal."""
    if not report.get("stage"):
        return str(report.get("reason", "no stage"))

    geometry = report["geometry"]
    solution = report["solution"]
    lines = [
        f"{report['title']}  --  {report['voices']} voices at {report['tempo']:g} bpm",
        f"written for {solution['reference']}, listening at {solution['frame']}, "
        f"{geometry['temperature']:g} C, sound at {geometry['speed_of_sound']:g} m/s",
    ]
    if solution["requested"]:
        lines.append(
            f"nobody called {solution['requested']!r} is on this stage; "
            f"listening at {solution['frame']} instead"
        )
    if not solution["compensate"]:
        lines.append("compensation is off: nobody is correcting for any of this")

    if solution["frame"] == FRAME_SCORE:
        lines.append("")
        lines.append("the score frame ignores the stage: every voice is heard where it is written")
        return "\n".join(lines)

    lines.append("")
    lines.append(f"what each player has to do, solved against {solution['reference']}")
    header = ("voice", "pos", "speech", "distance", "onset", "travel", "p-centre", "act")
    rows: list[tuple[str, ...]] = [header]
    order = sorted(solution["voices"], key=lambda item: -item["emission_ms"])
    for voice in order:
        rows.append(
            (
                voice["voice"],
                f"{voice['position'][0]:g},{voice['position'][1]:g}",
                voice["profile"],
                f"{voice['distance_m']:.1f} m",
                f"{voice['speech_ms']:.0f} ms",
                f"{voice['propagation_ms']:.0f} ms",
                f"{voice['p_center_ms']:.0f} ms",
                f"{voice['emission_ms']:+.0f} ms",
            )
        )
    widths = [max(len(row[index]) for row in rows) for index in range(len(header))]
    for row in rows:
        lines.append(
            "  " + "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)).rstrip()
        )
    if solution["lead_in_beats"]:
        lines.append(
            f"  the piece begins {solution['lead_in_beats']:.3f} beats later than written, so the "
            "earliest of them can act on time"
        )

    lines.append("")
    lines.append(f"what {solution['frame']} hears, against the written beat")
    lines.append(f"  spread {solution['spread_ms']:.0f} ms")
    for voice in sorted(order, key=lambda item: -abs(item["arrival_ms"]))[:8]:
        if abs(voice["arrival_ms"]) < 0.5:
            continue
        word = "late" if voice["arrival_ms"] > 0 else "early"
        lines.append(f"  {voice['voice']:<10} {abs(voice['arrival_ms']):.0f} ms {word}")

    if report["relative_to_own_sound"]:
        own = solution["frame"].split(":", 1)[-1]
        lines.append("")
        lines.append(f"and against {own}'s own sound, which is what that player judges by")
        for entry in report["relative_to_own_sound"]:
            word = "late" if entry["ms"] > 0 else "early"
            lines.append(f"  {entry['voice']:<10} {abs(entry['ms']):.0f} ms {word}")

    if report["elsewhere"]:
        lines.append("")
        lines.append("the same performance heard elsewhere")
        for entry in report["elsewhere"]:
            detail = ""
            if entry["latest"] and abs(entry["latest_ms"]) >= 0.5:
                word = "late" if entry["latest_ms"] > 0 else "early"
                detail = f"  (latest: {entry['latest']} {abs(entry['latest_ms']):.0f} ms {word})"
            lines.append(f"  {entry['frame']:<24} spread {entry['spread_ms']:.0f} ms{detail}")

    for problem in report["problems"]:
        lines.append(f"  stage: {problem}")
    return "\n".join(lines)


def movement(before: Any, after: Any) -> dict[str, Any]:
    """What a conductor's directives did, voice by voice.

    Notes are paired in written order, which holds because every transform here
    is monotone in time. Shifts are reported in milliseconds at the written
    tempo; where a directive changed the tempo itself, that is a reading of the
    beat positions rather than of any one moment.
    """
    tempo = float(getattr(before.meta, "tempo", 100.0) or 100.0)
    to_ms = 60_000.0 / max(tempo, 1e-6)
    later = {track.name: track for track in after.tracks}
    voices: list[dict[str, Any]] = []

    for track in before.tracks:
        partner = later.get(track.name)
        if partner is None or not track.notes:
            continue
        pairs = list(
            zip(
                sorted(track.notes, key=lambda note: (note.start, note.pitch)),
                sorted(partner.notes, key=lambda note: (note.start, note.pitch)),
                strict=False,  # voices differ in length; compare the overlap
            )
        )
        if not pairs:
            continue
        arrival = [
            (second.arrival_time - after.lead_in) - (first.arrival_time - before.lead_in)
            for first, second in pairs
        ]
        emission = [
            (second.emission_time - after.lead_in) - (first.emission_time - before.lead_in)
            for first, second in pairs
        ]
        voices.append(
            {
                "voice": track.name,
                "arrival_ms": round(sum(arrival) / len(arrival) * to_ms, 1),
                "arrival_last_ms": round(arrival[-1] * to_ms, 1),
                "emission_ms": round(sum(emission) / len(emission) * to_ms, 1),
            }
        )

    def spread(arrangement: Any) -> float:
        firsts = [
            min(note.arrival_time for note in track.notes)
            for track in arrangement.tracks
            if track.notes
        ]
        return (max(firsts) - min(firsts)) * to_ms if firsts else 0.0

    return {
        "voices": voices,
        "spread_before_ms": round(spread(before), 1),
        "spread_after_ms": round(spread(after), 1),
        "beats_before": round(before.total_beats, 3),
        "beats_after": round(after.total_beats, 3),
        "lead_in_beats": round(after.lead_in, 4),
    }


def format_movement(report: dict[str, Any]) -> str:
    """The movement report as text."""
    header = ("voice", "sound moved", "hands moved", "by the end")
    rows: list[tuple[str, ...]] = [header]
    for voice in report["voices"]:
        rows.append(
            (
                voice["voice"],
                f"{voice['arrival_ms']:+.0f} ms",
                f"{voice['emission_ms']:+.0f} ms",
                f"{voice['arrival_last_ms']:+.0f} ms",
            )
        )
    widths = [max(len(row[index]) for row in rows) for index in range(len(header))]
    lines = ["what the directives did"]
    for row in rows:
        lines.append(
            "  " + "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)).rstrip()
        )
    lines.append(
        f"  spread at the listener {report['spread_before_ms']:.0f} ms -> "
        f"{report['spread_after_ms']:.0f} ms, "
        f"length {report['beats_before']:g} -> {report['beats_after']:g} beats"
    )
    return "\n".join(lines)


def frames_for(stage: Stage) -> Iterable[str]:
    """Every frame name a user may pass to ``--frame`` for this stage."""
    return [FRAME_SCORE, *stage.frames(), f"{PLAYER_FRAME_PREFIX}<name>"]
