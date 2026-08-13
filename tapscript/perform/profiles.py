"""How long an instrument takes to speak, and where the ear places its attack.

A profile is data, the way a synthesiser voice is data in
:mod:`tapscript.render.voices`. Two numbers matter:

``speech``
    The delay between the player acting and sound leaving the instrument. A
    stick on a woodblock is instant; a large organ pipe has to fill before it
    sounds at all.

``p_center``
    The perceptual attack time -- how far into the attack the ear places the
    note. A soft bowed swell is heard later than its physical onset; a snare is
    heard essentially at it. This is a measured phenomenon in music
    psychology, and it is why two instruments whose onsets align can still
    sound out of time with each other.

These numbers are a model, not measurements of any particular instrument. They
are the right order of magnitude and they rank instruments correctly against
each other, which is what the timing solver needs. A specific Steinway in a
specific hall will differ, and a player can change their own speech time by a
factor of two with a different articulation. Override the model per voice with
``speech: 40ms`` in the ``[Stage]`` block when you know better.

Sources for the ranges, loosely: organ pipe speech is the best documented
(tens to a couple of hundred milliseconds, longest for large flue pipes);
bowed-string onset varies most with articulation; percussion is the reference
point that everything else is late against.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpeechProfile:
    """One instrument family's onset behaviour, in seconds."""

    name: str
    speech: float = 0.010
    p_center: float = 0.008
    note: str = ""

    @property
    def total(self) -> float:
        """Everything between the player acting and the ear hearing the note."""
        return self.speech + self.p_center


PERCUSSION = SpeechProfile(
    "percussion", 0.000, 0.001, "stick meets head: the reference for everything else"
)
MALLET = SpeechProfile("mallet", 0.002, 0.004, "vibraphone, marimba, glockenspiel")
PLUCKED = SpeechProfile("plucked", 0.003, 0.004, "guitar, harp, harpsichord, pizzicato")
PLUCKED_BASS = SpeechProfile(
    "plucked-bass", 0.006, 0.009, "low strings need a cycle or two before the pitch is there"
)
PIANO = SpeechProfile("piano", 0.008, 0.006, "hammer travel after the key goes down")
ELECTRIC = SpeechProfile("electric", 0.004, 0.005, "electronic sources speak when told to")
BOWED = SpeechProfile("bowed", 0.045, 0.025, "an ordinary detache bow; a swell is slower")
BOWED_SHORT = SpeechProfile("bowed-short", 0.012, 0.008, "spiccato, martele, a hard attack")
BOWED_SECTION = SpeechProfile(
    "bowed-section", 0.060, 0.032, "a section is slower than a soloist: desks do not start together"
)
BRASS = SpeechProfile("brass", 0.025, 0.015, "tongued attack; soft entries run to 40ms")
BRASS_SOFT = SpeechProfile("brass-soft", 0.045, 0.022, "a quiet horn entry, no tongue")
WOODWIND = SpeechProfile("woodwind", 0.018, 0.012, "reeds: oboe, clarinet, bassoon, saxophone")
WOODWIND_FLUE = SpeechProfile("woodwind-flue", 0.014, 0.010, "flute and recorder: air, no reed")
VOICE = SpeechProfile("voice", 0.045, 0.030, "consonant to vowel; a sung 'm' is later still")
REED_ORGAN = SpeechProfile("reed-organ", 0.035, 0.020, "harmonium, accordion, harmonica")
ORGAN_SMALL = SpeechProfile("organ-small", 0.045, 0.025, "a chamber organ, small flue pipes")
ORGAN = SpeechProfile("organ", 0.090, 0.040, "a church organ on ordinary stops")
ORGAN_LARGE = SpeechProfile(
    "organ-large", 0.140, 0.060, "large flue pipes: the pipe has to fill before it speaks"
)
PAD = SpeechProfile("pad", 0.080, 0.045, "a synthesiser pad is as slow as its patch")
GENERIC = SpeechProfile("generic", 0.010, 0.008, "used when nothing better is known")

# General MIDI program ranges, in order. First match wins, the same way
# render/voices.py maps programs to timbres, so any program lands somewhere
# sensible without a table entry per instrument.
PROGRAM_RANGES: tuple[tuple[int, int, SpeechProfile], ...] = (
    (0, 7, PIANO),
    (8, 15, MALLET),
    (16, 18, ELECTRIC),          # drawbar, percussive and rock organ are electronic
    (19, 19, ORGAN_LARGE),       # church organ
    (20, 20, REED_ORGAN),
    (21, 23, REED_ORGAN),        # accordion, harmonica, tango accordion
    (24, 31, PLUCKED),
    (32, 39, PLUCKED_BASS),
    (40, 44, BOWED),             # solo violin through tremolo strings
    (45, 46, PLUCKED),           # pizzicato strings, harp
    (47, 47, PERCUSSION),        # timpani
    (48, 51, BOWED_SECTION),
    (52, 54, VOICE),
    (55, 55, PERCUSSION),        # orchestra hit
    (56, 63, BRASS),
    (64, 71, WOODWIND),
    (72, 79, WOODWIND_FLUE),
    (80, 87, ELECTRIC),
    (88, 95, PAD),
    (96, 103, PAD),
    (104, 109, PLUCKED),         # sitar, banjo, shamisen, koto, kalimba, bagpipe
    (110, 110, BOWED),           # fiddle
    (111, 111, WOODWIND),        # shanai
    (112, 119, PERCUSSION),
    (120, 127, ELECTRIC),
)

BY_NAME: dict[str, SpeechProfile] = {
    profile.name: profile
    for profile in (
        PERCUSSION, MALLET, PLUCKED, PLUCKED_BASS, PIANO, ELECTRIC, BOWED, BOWED_SHORT,
        BOWED_SECTION, BRASS, BRASS_SOFT, WOODWIND, WOODWIND_FLUE, VOICE, REED_ORGAN,
        ORGAN_SMALL, ORGAN, ORGAN_LARGE, PAD, GENERIC,
    )
}

# Spellings a musician is likely to write, mapped onto the profiles above.
ALIASES: dict[str, str] = {
    "drum": "percussion",
    "drums": "percussion",
    "timpani": "percussion",
    "woodblock": "percussion",
    "instant": "percussion",
    "pluck": "plucked",
    "guitar": "plucked",
    "harp": "plucked",
    "pizz": "plucked",
    "pizzicato": "plucked",
    "keys": "piano",
    "hammer": "piano",
    "string": "bowed",
    "strings": "bowed-section",
    "arco": "bowed",
    "spiccato": "bowed-short",
    "detache": "bowed",
    "horn": "brass",
    "trumpet": "brass",
    "trombone": "brass",
    "reed": "woodwind",
    "flute": "woodwind-flue",
    "sung": "voice",
    "choir": "voice",
    "vocals": "voice",
    "organ-church": "organ-large",
    "synth": "electric",
    "electronic": "electric",
}


def profile_for_name(name: str) -> SpeechProfile | None:
    """Look a profile up by name or by one of the spellings in :data:`ALIASES`."""
    key = name.strip().lower().replace("_", "-").replace(" ", "-")
    if not key:
        return None
    if key in BY_NAME:
        return BY_NAME[key]
    alias = ALIASES.get(key)
    return BY_NAME.get(alias) if alias else None


def profile_for_program(program: int, is_drum: bool = False) -> SpeechProfile:
    """Pick a profile for a General MIDI program number."""
    if is_drum:
        return PERCUSSION
    for low, high, profile in PROGRAM_RANGES:
        if low <= program <= high:
            return profile
    return GENERIC


def profile_names() -> list[str]:
    return sorted(BY_NAME)
