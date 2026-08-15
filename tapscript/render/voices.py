"""Synthesiser voices.

A voice is data: a handful of harmonic amplitudes, an envelope, and a little
noise or vibrato. Instruments are matched by General MIDI program range, so any
program number lands on something reasonable without a lookup table per
instrument.

This is a preview synthesiser. It exists so that a fresh clone with nothing
installed can still play you the tune. When quality matters, render through a
soundfont -- see :mod:`tapscript.render.backends`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Voice:
    """One timbre."""

    name: str
    harmonics: tuple[float, ...] = (1.0, 0.4, 0.2, 0.1)
    attack: float = 0.01          # seconds
    decay: float = 0.20           # seconds
    sustain: float = 0.6          # fraction of peak
    release: float = 0.18         # seconds
    noise: float = 0.0            # blend of white noise, 0..1
    vibrato_hz: float = 0.0
    vibrato_depth: float = 0.0    # fraction of a semitone
    gain: float = 1.0
    percussive: bool = False      # ignore sustain, decay straight to silence

    def envelope_points(self, duration: float) -> tuple[float, float, float, float]:
        """Attack, decay, sustain level and release scaled to fit *duration*."""
        attack = min(self.attack, duration * 0.4)
        decay = min(self.decay, max(duration - attack, 0.0) * 0.6)
        release = min(self.release, max(duration - attack - decay, 0.0) * 0.9)
        return attack, decay, self.sustain, release


PIANO = Voice(
    name="piano",
    harmonics=(1.0, 0.42, 0.22, 0.11, 0.06, 0.03),
    attack=0.004, decay=0.45, sustain=0.28, release=0.25, percussive=True,
)
ELECTRIC_PIANO = Voice(
    name="electric piano",
    harmonics=(1.0, 0.28, 0.14, 0.35, 0.05),
    attack=0.006, decay=0.5, sustain=0.32, release=0.3, percussive=True,
)
BELL = Voice(
    name="bell",
    harmonics=(1.0, 0.0, 0.6, 0.0, 0.35, 0.0, 0.2),
    attack=0.002, decay=0.9, sustain=0.05, release=0.6, percussive=True,
)
ORGAN = Voice(
    name="organ",
    harmonics=(1.0, 0.7, 0.5, 0.35, 0.25, 0.18, 0.12),
    attack=0.02, decay=0.05, sustain=0.9, release=0.08,
)
GUITAR = Voice(
    name="guitar",
    harmonics=(1.0, 0.55, 0.32, 0.18, 0.1, 0.05),
    attack=0.005, decay=0.6, sustain=0.2, release=0.3, percussive=True,
)
BASS = Voice(
    name="bass",
    harmonics=(1.0, 0.5, 0.18, 0.06),
    attack=0.008, decay=0.4, sustain=0.45, release=0.2, gain=1.15,
)
STRINGS = Voice(
    name="strings",
    harmonics=(1.0, 0.6, 0.4, 0.28, 0.2, 0.14, 0.1),
    attack=0.12, decay=0.15, sustain=0.85, release=0.35,
    vibrato_hz=5.2, vibrato_depth=0.035,
)
CHOIR = Voice(
    name="choir",
    harmonics=(1.0, 0.5, 0.3, 0.12, 0.28, 0.08),
    attack=0.09, decay=0.2, sustain=0.8, release=0.4,
    vibrato_hz=4.6, vibrato_depth=0.03, noise=0.015,
)
BRASS = Voice(
    name="brass",
    harmonics=(1.0, 0.8, 0.62, 0.45, 0.3, 0.2, 0.12),
    attack=0.05, decay=0.12, sustain=0.78, release=0.18, gain=0.95,
)
REED = Voice(
    name="reed",
    harmonics=(1.0, 0.15, 0.5, 0.1, 0.28, 0.05),
    attack=0.04, decay=0.1, sustain=0.82, release=0.15,
    vibrato_hz=5.0, vibrato_depth=0.02,
)
FLUTE = Voice(
    name="flute",
    harmonics=(1.0, 0.12, 0.05),
    attack=0.06, decay=0.1, sustain=0.85, release=0.18,
    noise=0.035, vibrato_hz=5.5, vibrato_depth=0.025,
)
LEAD = Voice(
    name="lead",
    harmonics=(1.0, 0.5, 0.33, 0.25, 0.2, 0.16, 0.14, 0.12),
    attack=0.01, decay=0.15, sustain=0.7, release=0.12,
)
PAD = Voice(
    name="pad",
    harmonics=(1.0, 0.45, 0.3, 0.22, 0.15, 0.1),
    attack=0.35, decay=0.3, sustain=0.75, release=0.6,
    vibrato_hz=3.1, vibrato_depth=0.02, gain=0.85,
)
PLUCK = Voice(
    name="pluck",
    harmonics=(1.0, 0.4, 0.25, 0.15, 0.08),
    attack=0.003, decay=0.35, sustain=0.1, release=0.2, percussive=True,
)
DRUM = Voice(
    name="drum",
    harmonics=(1.0, 0.3),
    attack=0.001, decay=0.18, sustain=0.0, release=0.08,
    noise=0.85, percussive=True, gain=1.1,
)

# General MIDI program ranges, in order. First match wins.
PROGRAM_RANGES: tuple[tuple[int, int, Voice], ...] = (
    (0, 3, PIANO),
    (4, 7, ELECTRIC_PIANO),
    (8, 15, BELL),
    (16, 23, ORGAN),
    (24, 31, GUITAR),
    (32, 39, BASS),
    (40, 51, STRINGS),
    (52, 55, CHOIR),
    (56, 63, BRASS),
    (64, 71, REED),
    (72, 79, FLUTE),
    (80, 87, LEAD),
    (88, 95, PAD),
    (96, 103, PAD),
    (104, 111, PLUCK),
    (112, 119, PLUCK),
    (120, 127, DRUM),
)

BY_NAME: dict[str, Voice] = {
    voice.name: voice
    for voice in (
        PIANO, ELECTRIC_PIANO, BELL, ORGAN, GUITAR, BASS, STRINGS,
        CHOIR, BRASS, REED, FLUTE, LEAD, PAD, PLUCK, DRUM,
    )
}


def voice_for_program(program: int, is_drum: bool = False) -> Voice:
    """Pick a voice for a General MIDI program number."""
    if is_drum:
        return DRUM
    for low, high, voice in PROGRAM_RANGES:
        if low <= program <= high:
            return voice
    return PIANO


def voice_for_name(name: str) -> Voice | None:
    return BY_NAME.get(name.strip().lower())


def voice_names() -> list[str]:
    return sorted(BY_NAME)
