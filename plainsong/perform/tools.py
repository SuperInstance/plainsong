"""Arrival-centric timing, exposed to the agent.

One entry point, :func:`register`, adds the tools to a
:class:`~plainsong.agent.tools.ToolRegistry`. Keeping them here rather than in
``agent/tools.py`` means the feature owns its own tool surface, and an install
that deletes ``perform/`` loses these tools and nothing else.

The tools return text, like every other tool, because the model has to read the
answer rather than parse it.
"""

from __future__ import annotations

from typing import Any

STAGE_HELP = """A [Stage] block says where the players are standing and who the music is
written for. Written times are then arrival times -- when the sound should reach
that listener -- and the compiler solves backwards for when each player has to act.

    [Stage]
    listener: conductor          # conductor, audience, or player:<name>
    temperature: 20              # degrees C; sets the speed of sound
    compensate: on               # off renders the errors instead of correcting them
    audience: 0,14               # move a listener, in metres
    @timpani: pos 4,-6 | speech: percussion
    @violin1: pos -3,1 | speech: bowed | feel: -6ms
    @organ:   pos 0,-12 | speech: organ-large

Positions are metres from the podium: +y towards the audience, +x to the
conductor's right. `speech` names an instrument family or gives a time such as
`40ms`; leaving it out picks one from the voice's General MIDI program. `feel`
is expressive, not corrective -- negative pushes ahead of the beat, positive
lays back -- and it survives into what the listener hears.

MIDI export carries emission times, audio renders arrival times. A file with no
[Stage] block behaves exactly as it always did.
"""

DIRECTIVE_HELP = """A conductor's directive is applied to what the room hears, and every player's
own timing is solved from it. The vocabulary is the one fleet-jepa-midi's
bandleader emits, and this is the JSON it sends:

    {
      "directives": [
        {"action": "lay_back", "intensity": 0.7, "duration_beats": 8,
         "offset_beats": 0, "target": ["rhythm"], "priority": "blend"}
      ],
      "energy":  {"target": 0.8, "mode": "absolute"},
      "tension": {"delta": 0.15, "mode": "relative"},
      "narrative_note": "arriving at climax"
    }

Windows are in beats, not bars, and `offset_beats` need not be a downbeat --
"drop out on beat 3" is an offset of 2. `priority` is `blend` (interpolate with
whatever else is running) or `override` (take the others out of it). `target`
picks layers: melody, harmony, rhythm, texture, dynamics, ensemble.

The timing layer acts on the time and feel family:

    lay_back      arrivals sit behind the grid
    push_forward  arrivals sit ahead of it
    anticipate    the hands move earlier and the sound does not move at all
    drag          lateness accumulating across the window
    straighten    swing towards zero
    deepen_swing  swing towards a triplet
    float         the ensemble stops correcting and spreads apart
    lock_in       the ensemble tightens to a single instant
    double_time   the subdivision halves inside the window
    half_time     the subdivision doubles

Anything else in the vocabulary is accepted and reported rather than refused,
because a bandleader talking to several systems should not have to know which
of them cares about what.
"""


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


def _string(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def register(registry: Any) -> None:
    """Add the performance tools to *registry*."""

    def stage_reference() -> str:
        return STAGE_HELP

    def ensemble_report(path: str = "", content: str = "", frame: str = "") -> str:
        from ..notation import arrange, parse
        from ..notation.arrange import ArrangeOptions
        from .solve import analyse, format_report

        text, problem = _load(registry, path, content)
        if problem:
            return problem
        score = parse(text, path=path)
        if score.has_errors:
            return "the notation has errors:\n" + "\n".join(
                f"  {diag.format()}" for diag in score.errors()
            )
        if score.meta.stage is None:
            return (
                "this piece has no [Stage] block, so every voice is heard where it is written. "
                "Call stage_reference to see how to add one."
            )
        arrangement = arrange(score, ArrangeOptions(frame=frame))
        return format_report(analyse(arrangement, frame=frame))

    def speech_profiles() -> str:
        from .profiles import BY_NAME

        rows = [
            f"{profile.name:<14} speech {profile.speech * 1000:>5.0f} ms   "
            f"p-centre {profile.p_center * 1000:>4.0f} ms   {profile.note}"
            for profile in sorted(BY_NAME.values(), key=lambda item: item.speech)
        ]
        return (
            "Speech profiles, in order of how quickly they sound. These are a model, "
            "not measurements of any particular instrument.\n\n" + "\n".join(rows)
        )

    def directive_reference() -> str:
        return DIRECTIVE_HELP

    def conduct_score(
        directives: str, path: str = "", content: str = "", frame: str = ""
    ) -> str:
        from ..notation import arrange, parse
        from ..notation.arrange import ArrangeOptions
        from . import conduct
        from .solve import format_movement, movement

        text, problem = _load(registry, path, content)
        if problem:
            return problem
        score = parse(text, path=path)
        if score.has_errors:
            return "the notation has errors:\n" + "\n".join(
                f"  {diag.format()}" for diag in score.errors()
            )
        reading = conduct.read(directives)
        written = arrange(score, ArrangeOptions(frame=frame))
        conducted = conduct.apply(written, reading, frame=frame)

        lines = ["directives read:", conduct.describe(reading), ""]
        lines.append(format_movement(movement(written, conducted)))
        if score.meta.stage is None:
            lines.append("")
            lines.append(
                "this piece declares no [Stage] block, so the directives moved the written "
                "times but there was nobody's position to solve against. Call stage_reference."
            )
        return "\n".join(lines)

    registry.add(
        "stage_reference",
        "Read how to write a [Stage] block: positions, listeners, speech profiles and feel. "
        "Call this before writing arrival-centric timing for the first time in a session.",
        _schema({}),
        stage_reference,
    )
    registry.add(
        "ensemble_report",
        "Report what a listener on the stage actually hears: each voice's distance, speech "
        "time, propagation delay and the moment its player has to act, plus the spread at "
        "the chosen listener and at every other one.",
        _schema(
            {
                "path": _string("A .song file to analyse."),
                "content": _string("Notation to analyse instead of a path."),
                "frame": _string("Whose ears: conductor, audience, player:<name>, or score."),
            }
        ),
        ensemble_report,
    )
    registry.add(
        "speech_profiles",
        "List the instrument speech profiles a [Stage] block can name, with how long each "
        "takes to sound and how far into the attack the ear places it.",
        _schema({}),
        speech_profiles,
    )
    registry.add(
        "directive_reference",
        "Read the conductor's directive vocabulary -- the JSON a bandleader sends, which "
        "actions the timing layer acts on, and what the windows and targets mean. Call this "
        "before writing directives for the first time in a session.",
        _schema({}),
        directive_reference,
    )
    registry.add(
        "conduct_score",
        "Apply a bandleader's directive JSON to a piece and report what it did to the "
        "ensemble's timing: how the arrivals moved together and how far each player's hands "
        "moved to keep them there.",
        _schema(
            {
                "directives": _string("The directive JSON. See directive_reference."),
                "path": _string("A .song file to conduct."),
                "content": _string("Notation to conduct instead of a path."),
                "frame": _string("Whose ears: conductor, audience, player:<name>, or score."),
            },
            ["directives"],
        ),
        conduct_score,
    )


def _load(registry: Any, path: str, content: str) -> tuple[str, str]:
    """Read notation from the sandbox or take it inline. Returns (text, problem)."""
    if content:
        return content, ""
    if not path:
        return "", "error: pass either a path or inline content"
    source = registry.sandbox.resolve(path)
    if not source.is_file():
        return "", f"error: {path} does not exist"
    return source.read_text(encoding="utf-8", errors="replace"), ""
