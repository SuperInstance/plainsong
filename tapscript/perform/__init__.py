"""Arrival-centric timing: writing what the listener hears.

A written time is a moment at somebody's ear, not a moment at somebody's hands.
Between the two sit the instrument taking time to speak, the sound taking time
to cross the room, and the ear placing the note a little way into its attack.
This package models all three, solves backwards for when each player has to
act, and reports what the result sounds like from wherever you choose to stand.

    :mod:`.stage`     geometry, listeners, the speed of sound
    :mod:`.profiles`  how long each instrument family takes to speak
    :mod:`.solve`     the emission/arrival solver and the ensemble report
    :mod:`.conduct`   bandleader directives, applied coherently to every voice
    :mod:`.tools`     the same operations, exposed to the agent

None of it does anything unless a piece declares a ``[Stage]`` block. See
``docs/performance.md``.
"""

from __future__ import annotations

from . import conduct, profiles, solve, stage
from .conduct import Directive, DirectiveSet, Feel
from .profiles import SpeechProfile, profile_for_name, profile_for_program, profile_names
from .solve import Shaping, Solution, VoiceTiming, analyse, apply_to, format_report
from .stage import (
    FRAME_SCORE,
    Placement,
    Stage,
    parse_duration,
    parse_position,
    read_stage_line,
    speed_of_sound,
)

# The verbs keep their module names: `perform.solve.solve(...)` and
# `perform.conduct.apply(...)`. Re-exporting them here would shadow the modules
# they live in, which is worse than the extra word.
__all__ = [
    "FRAME_SCORE",
    "Directive",
    "DirectiveSet",
    "Feel",
    "Placement",
    "Shaping",
    "Solution",
    "SpeechProfile",
    "Stage",
    "VoiceTiming",
    "analyse",
    "apply_to",
    "conduct",
    "format_report",
    "parse_duration",
    "parse_position",
    "profile_for_name",
    "profile_for_program",
    "profile_names",
    "profiles",
    "read_stage_line",
    "solve",
    "speed_of_sound",
    "stage",
]
