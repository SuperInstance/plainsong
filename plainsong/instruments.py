"""General MIDI instrument mapping.

One table, used by the arranger, both renderers, the web interface and the
agent's tool surface. Earlier versions of this project kept four copies of this
data that had already drifted apart; keep it here and import it.
"""

from __future__ import annotations

# Canonical name -> General MIDI program number (0-based).
GM_PROGRAMS: dict[str, int] = {
    "piano": 0,
    "acoustic piano": 0,
    "grand piano": 0,
    "bright piano": 1,
    "electric piano": 4,
    "rhodes": 4,
    "harpsichord": 6,
    "clavinet": 7,
    "celesta": 8,
    "glockenspiel": 9,
    "music box": 10,
    "vibraphone": 11,
    "vibes": 11,
    "marimba": 12,
    "xylophone": 13,
    "organ": 16,
    "hammond": 16,
    "church organ": 19,
    "reed organ": 20,
    "accordion": 21,
    "harmonica": 22,
    "guitar": 24,
    "nylon guitar": 24,
    "acoustic guitar": 25,
    "steel guitar": 25,
    "jazz guitar": 26,
    "electric guitar": 27,
    "clean guitar": 27,
    "muted guitar": 28,
    "overdrive guitar": 29,
    "distortion guitar": 30,
    "bass": 33,
    "acoustic bass": 32,
    "upright bass": 32,
    "electric bass": 33,
    "fingered bass": 33,
    "picked bass": 34,
    "fretless bass": 35,
    "slap bass": 36,
    "synth bass": 38,
    "violin": 40,
    "viola": 41,
    "cello": 42,
    "contrabass": 43,
    "tremolo strings": 44,
    "pizzicato": 45,
    "harp": 46,
    "timpani": 47,
    "strings": 48,
    "string section": 48,
    "slow strings": 51,
    "synth strings": 50,
    "choir": 52,
    "voice": 53,
    "vocals": 53,
    "voice oohs": 53,
    "synth voice": 54,
    "trumpet": 56,
    "trombone": 57,
    "tuba": 58,
    "muted trumpet": 59,
    "french horn": 60,
    "brass": 61,
    "brass section": 61,
    "synth brass": 62,
    "soprano sax": 64,
    "alto sax": 65,
    "saxophone": 65,
    "sax": 65,
    "tenor sax": 66,
    "baritone sax": 67,
    "oboe": 68,
    "english horn": 69,
    "bassoon": 70,
    "clarinet": 71,
    "piccolo": 72,
    "flute": 73,
    "recorder": 74,
    "pan flute": 75,
    "whistle": 78,
    "ocarina": 79,
    "lead": 80,
    "square lead": 80,
    "saw lead": 81,
    "synth": 81,
    "lead synth": 81,
    "calliope": 82,
    "charang": 84,
    "pad": 88,
    "new age pad": 88,
    "warm pad": 89,
    "polysynth": 90,
    "choir pad": 91,
    "bowed pad": 92,
    "halo pad": 94,
    "sweep pad": 95,
    "sitar": 104,
    "banjo": 105,
    "shamisen": 106,
    "koto": 107,
    "kalimba": 108,
    "bagpipe": 109,
    "fiddle": 110,
    "shanai": 111,
    "steel drums": 114,
    "woodblock": 115,
    "taiko": 116,
    "melodic tom": 117,
    "synth drum": 118,
    "drums": 0,
    "drum kit": 0,
    "percussion": 0,
}

# Substrings checked against a player's name, longest first.
NAME_HINTS: tuple[tuple[str, str], ...] = tuple(
    sorted(
        (
            ("piano", "piano"),
            ("keys", "electric piano"),
            ("rhodes", "rhodes"),
            ("organ", "organ"),
            ("synth", "synth"),
            ("pad", "pad"),
            ("lead", "lead"),
            ("guitar", "guitar"),
            ("gtr", "guitar"),
            ("acoustic", "acoustic guitar"),
            ("banjo", "banjo"),
            ("uke", "nylon guitar"),
            ("bass", "bass"),
            ("sub", "synth bass"),
            ("drum", "drums"),
            ("perc", "percussion"),
            ("kit", "drums"),
            ("string", "strings"),
            ("violin", "violin"),
            ("cello", "cello"),
            ("viola", "viola"),
            ("harp", "harp"),
            ("horn", "french horn"),
            ("brass", "brass"),
            ("trumpet", "trumpet"),
            ("trombone", "trombone"),
            ("sax", "saxophone"),
            ("flute", "flute"),
            ("clarinet", "clarinet"),
            ("oboe", "oboe"),
            ("voice", "voice"),
            ("vocal", "vocals"),
            ("choir", "choir"),
            ("sing", "vocals"),
            ("melody", "piano"),
            ("chord", "piano"),
        ),
        key=lambda pair: -len(pair[0]),
    )
)

DRUM_WORDS = ("drum", "perc", "kit", "taiko", "cajon")

# Fallback instruments assigned to unnamed players, in order.
ROTATION = ("piano", "guitar", "bass", "strings", "electric piano", "flute")


def program_for(instrument: str) -> int:
    """GM program number for an instrument name. Unknown names become piano."""
    key = instrument.strip().lower()
    if key in GM_PROGRAMS:
        return GM_PROGRAMS[key]
    for name, program in GM_PROGRAMS.items():
        if name in key:
            return program
    return 0


def instrument_for_name(name: str, fallback_index: int = 0) -> str:
    """Guess an instrument from a player's name (``@bass``, ``@lead_gtr``)."""
    key = name.strip().lower().replace("_", " ").replace("-", " ")
    if key in GM_PROGRAMS:
        return key
    for hint, instrument in NAME_HINTS:
        if hint in key:
            return instrument
    return ROTATION[fallback_index % len(ROTATION)]


def is_drum_name(name: str) -> bool:
    key = name.strip().lower()
    return any(word in key for word in DRUM_WORDS)


def instrument_names() -> list[str]:
    return sorted(GM_PROGRAMS)
