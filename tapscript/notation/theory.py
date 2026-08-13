"""Pitch, scale and chord arithmetic.

Pure functions over integers. No I/O, no state, no dependencies. Both notation
dialects resolve down to the MIDI note numbers this module produces.
"""

from __future__ import annotations

import re

NOTE_NAMES_SHARP = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
NOTE_NAMES_FLAT = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")

LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Keys conventionally written with flats.
FLAT_KEYS = {"F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb", "Dm", "Gm", "Cm", "Fm", "Bbm", "Ebm"}

SCALES: dict[str, tuple[int, ...]] = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "ionian": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "aeolian": (0, 2, 3, 5, 7, 8, 10),
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11),
    "melodic_minor": (0, 2, 3, 5, 7, 9, 11),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
    "blues": (0, 3, 5, 6, 7, 10),
    "pentatonic_major": (0, 2, 4, 7, 9),
    "pentatonic_minor": (0, 3, 5, 7, 10),
    "chromatic": tuple(range(12)),
}

DIATONIC_TRIADS: dict[str, tuple[str, ...]] = {
    "major": ("maj", "min", "min", "maj", "maj", "min", "dim"),
    "minor": ("min", "dim", "maj", "min", "min", "maj", "maj"),
    "dorian": ("min", "min", "maj", "maj", "min", "dim", "maj"),
    "phrygian": ("min", "maj", "maj", "min", "dim", "maj", "min"),
    "lydian": ("maj", "maj", "min", "dim", "maj", "min", "min"),
    "mixolydian": ("maj", "min", "dim", "maj", "min", "min", "maj"),
    "locrian": ("dim", "maj", "min", "min", "dim", "maj", "maj"),
    "harmonic_minor": ("min", "dim", "aug", "min", "maj", "maj", "dim"),
    "melodic_minor": ("min", "min", "aug", "maj", "maj", "dim", "dim"),
}

CHORD_INTERVALS: dict[str, tuple[int, ...]] = {
    "maj": (0, 4, 7),
    "min": (0, 3, 7),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
    "5": (0, 7),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "6": (0, 4, 7, 9),
    "min6": (0, 3, 7, 9),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
    "minmaj7": (0, 3, 7, 11),
    "dim7": (0, 3, 6, 9),
    "min7b5": (0, 3, 6, 10),
    "aug7": (0, 4, 8, 10),
    "7sus4": (0, 5, 7, 10),
    "add9": (0, 4, 7, 14),
    "madd9": (0, 3, 7, 14),
    "9": (0, 4, 7, 10, 14),
    "maj9": (0, 4, 7, 11, 14),
    "min9": (0, 3, 7, 10, 14),
    "11": (0, 4, 7, 10, 14, 17),
    "min11": (0, 3, 7, 10, 14, 17),
    "13": (0, 4, 7, 10, 14, 21),
    "maj13": (0, 4, 7, 11, 14, 21),
    "min13": (0, 3, 7, 10, 14, 21),
    "7b9": (0, 4, 7, 10, 13),
    "7sharp9": (0, 4, 7, 10, 15),
    "7b5": (0, 4, 6, 10),
    "7sharp5": (0, 4, 8, 10),
}

# Suffix spellings people actually type, longest first so `maj7` wins over `maj`.
QUALITY_ALIASES: tuple[tuple[str, str], ...] = tuple(
    sorted(
        (
            ("", "maj"),
            ("M", "maj"),
            ("maj", "maj"),
            ("major", "maj"),
            ("m", "min"),
            ("-", "min"),
            ("min", "min"),
            ("minor", "min"),
            ("dim", "dim"),
            ("o", "dim"),
            ("°", "dim"),
            ("aug", "aug"),
            ("+", "aug"),
            ("5", "5"),
            ("no3", "5"),
            ("sus", "sus4"),
            ("sus2", "sus2"),
            ("sus4", "sus4"),
            ("6", "6"),
            ("m6", "min6"),
            ("min6", "min6"),
            ("-6", "min6"),
            ("7", "7"),
            ("dom7", "7"),
            ("maj7", "maj7"),
            ("M7", "maj7"),
            ("Δ", "maj7"),
            ("Δ7", "maj7"),
            ("m7", "min7"),
            ("-7", "min7"),
            ("min7", "min7"),
            ("mM7", "minmaj7"),
            ("mmaj7", "minmaj7"),
            ("dim7", "dim7"),
            ("o7", "dim7"),
            ("°7", "dim7"),
            ("m7b5", "min7b5"),
            ("min7b5", "min7b5"),
            ("ø", "min7b5"),
            ("ø7", "min7b5"),
            ("half-dim", "min7b5"),
            ("+7", "aug7"),
            ("aug7", "aug7"),
            ("7aug5", "aug7"),
            ("7sus4", "7sus4"),
            ("7sus", "7sus4"),
            ("add9", "add9"),
            ("madd9", "madd9"),
            ("2", "add9"),
            ("9", "9"),
            ("maj9", "maj9"),
            ("M9", "maj9"),
            ("m9", "min9"),
            ("min9", "min9"),
            ("11", "11"),
            ("m11", "min11"),
            ("min11", "min11"),
            ("13", "13"),
            ("maj13", "maj13"),
            ("m13", "min13"),
            ("min13", "min13"),
            ("7b9", "7b9"),
            ("7#9", "7sharp9"),
            ("7b5", "7b5"),
            ("7#5", "7sharp5"),
        ),
        key=lambda pair: -len(pair[0]),
    )
)

ROMAN_DEGREES = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
}

_PITCH_RE = re.compile(r"^([A-Ga-g])([#b♯♭]*)(-?\d+)?$")
_CHORD_RE = re.compile(r"^([A-Ga-g])([#b♯♭]*)(.*)$")
_ROMAN_RE = re.compile(
    r"^([#b♯♭]?)([ivIV]+)(.*)$",
)


class TheoryError(ValueError):
    """Raised when a token cannot be interpreted as pitch or harmony."""


def _accidental_shift(accidentals: str) -> int:
    shift = 0
    for char in accidentals:
        if char in "#♯":
            shift += 1
        elif char in "b♭":
            shift -= 1
    return shift


def parse_pitch(token: str, default_octave: int = 4) -> int:
    """Scientific pitch notation to MIDI note number. ``C4`` is 60.

    Case-insensitive: the corpus uses lowercase for accompaniment voicings
    (``a2-e3-a3``) and uppercase for melody, and both mean the same pitch.
    """
    match = _PITCH_RE.match(token.strip())
    if not match:
        raise TheoryError(f"not a pitch: {token!r}")
    letter, accidentals, octave = match.groups()
    pc = LETTER_PC[letter.upper()] + _accidental_shift(accidentals)
    octave_number = int(octave) if octave is not None else default_octave
    midi = (octave_number + 1) * 12 + pc
    if not 0 <= midi <= 127:
        raise TheoryError(f"pitch out of MIDI range: {token!r}")
    return midi


def is_pitch(token: str) -> bool:
    return bool(_PITCH_RE.match(token.strip()))


def pitch_name(midi: int, prefer_flats: bool = False) -> str:
    names = NOTE_NAMES_FLAT if prefer_flats else NOTE_NAMES_SHARP
    return f"{names[midi % 12]}{midi // 12 - 1}"


def normalise_quality(suffix: str) -> str | None:
    """Map a written chord suffix onto a key of :data:`CHORD_INTERVALS`."""
    cleaned = suffix.strip()
    if cleaned in CHORD_INTERVALS:
        return cleaned
    for alias, quality in QUALITY_ALIASES:
        if cleaned == alias:
            return quality
    # Tolerate trailing decoration such as `C7(b9)` or `Am(add9)`.
    stripped = cleaned.replace("(", "").replace(")", "").replace(" ", "")
    if stripped in CHORD_INTERVALS:
        return stripped
    for alias, quality in QUALITY_ALIASES:
        if stripped == alias:
            return quality
    return None


class Chord:
    """A resolved chord: a root pitch class, a quality, an optional bass."""

    __slots__ = ("root_pc", "quality", "bass_pc", "text")

    def __init__(self, root_pc: int, quality: str, bass_pc: int | None = None, text: str = "") -> None:
        self.root_pc = root_pc % 12
        self.quality = quality
        self.bass_pc = bass_pc % 12 if bass_pc is not None else None
        self.text = text

    def notes(self, octave: int = 3, spread: bool = True) -> list[int]:
        """MIDI notes for this chord, root position, bass note first if given."""
        intervals = CHORD_INTERVALS.get(self.quality, CHORD_INTERVALS["maj"])
        root = (octave + 1) * 12 + self.root_pc
        notes = [root + interval for interval in intervals]
        if self.bass_pc is not None and self.bass_pc != self.root_pc:
            bass = (octave + 1) * 12 + self.bass_pc
            while bass >= notes[0]:
                bass -= 12
            notes.insert(0, bass)
        if not spread and len(notes) > 4:
            notes = notes[:4]
        return [note for note in notes if 0 <= note <= 127]

    def transpose(self, semitones: int) -> Chord:
        return Chord(
            self.root_pc + semitones,
            self.quality,
            None if self.bass_pc is None else self.bass_pc + semitones,
            self.text,
        )

    def name(self, prefer_flats: bool = False) -> str:
        names = NOTE_NAMES_FLAT if prefer_flats else NOTE_NAMES_SHARP
        suffix = {"maj": "", "min": "m", "dim": "dim", "aug": "aug"}.get(self.quality, self.quality)
        label = f"{names[self.root_pc]}{suffix}"
        if self.bass_pc is not None and self.bass_pc != self.root_pc:
            label += f"/{names[self.bass_pc]}"
        return label

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Chord({self.name()!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Chord):
            return NotImplemented
        return (self.root_pc, self.quality, self.bass_pc) == (other.root_pc, other.quality, other.bass_pc)


def parse_chord(token: str) -> Chord:
    """Parse an absolute chord symbol such as ``Am``, ``Cmaj7`` or ``D/F#``."""
    text = token.strip()
    if not text:
        raise TheoryError("empty chord")
    bass_pc: int | None = None
    if "/" in text:
        text, _, bass_text = text.partition("/")
        bass_match = _CHORD_RE.match(bass_text.strip())
        if bass_match:
            bass_pc = LETTER_PC[bass_match.group(1).upper()] + _accidental_shift(bass_match.group(2))
    match = _CHORD_RE.match(text)
    if not match:
        raise TheoryError(f"not a chord: {token!r}")
    letter, accidentals, suffix = match.groups()
    # A bare uppercase letter with an octave digit is a pitch, not a chord.
    quality = normalise_quality(suffix)
    if quality is None:
        raise TheoryError(f"unknown chord quality: {suffix!r} in {token!r}")
    root_pc = LETTER_PC[letter.upper()] + _accidental_shift(accidentals)
    # Lowercase root with a minor-ish suffix is still that root; lowercase alone
    # is treated as major because the corpus writes voicings in lowercase.
    return Chord(root_pc, quality, bass_pc, text=token.strip())


def is_chord(token: str) -> bool:
    try:
        parse_chord(token)
        return True
    except TheoryError:
        return False


class Key:
    """A tonal centre plus a mode."""

    __slots__ = ("tonic_pc", "mode", "text")

    def __init__(self, tonic_pc: int, mode: str = "major", text: str = "") -> None:
        self.tonic_pc = tonic_pc % 12
        self.mode = mode if mode in SCALES else "major"
        self.text = text

    @property
    def intervals(self) -> tuple[int, ...]:
        return SCALES[self.mode]

    @property
    def prefer_flats(self) -> bool:
        return self.name() in FLAT_KEYS

    def name(self) -> str:
        names = NOTE_NAMES_SHARP
        suffix = "m" if self.mode in {"minor", "aeolian"} else ""
        return f"{names[self.tonic_pc]}{suffix}"

    def degree_pc(self, degree: int, alteration: int = 0) -> int:
        """Pitch class of a scale degree (1-based), wrapping past the octave."""
        intervals = self.intervals
        index = (degree - 1) % len(intervals)
        octaves = (degree - 1) // len(intervals)
        return (self.tonic_pc + intervals[index] + 12 * octaves + alteration) % 12

    def degree_pitch(self, degree: int, octave: int = 4, alteration: int = 0) -> int:
        intervals = self.intervals
        index = (degree - 1) % len(intervals)
        octave_shift = (degree - 1) // len(intervals)
        semitone = self.tonic_pc + intervals[index] + alteration
        return (octave + 1) * 12 + semitone + 12 * octave_shift

    def triad_quality(self, degree: int) -> str:
        table = DIATONIC_TRIADS.get(self.mode, DIATONIC_TRIADS["major"])
        return table[(degree - 1) % len(table)]

    def transpose(self, semitones: int) -> Key:
        return Key(self.tonic_pc + semitones, self.mode)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Key({self.name()!r}, {self.mode!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Key):
            return NotImplemented
        return (self.tonic_pc, self.mode) == (other.tonic_pc, other.mode)


MODE_WORDS = {
    "major": "major", "maj": "major", "": "major", "ionian": "ionian",
    "minor": "minor", "min": "minor", "m": "minor", "aeolian": "aeolian",
    "dorian": "dorian", "phrygian": "phrygian", "lydian": "lydian",
    "mixolydian": "mixolydian", "locrian": "locrian",
    "harmonic minor": "harmonic_minor", "harmonic_minor": "harmonic_minor",
    "melodic minor": "melodic_minor", "melodic_minor": "melodic_minor",
    "blues": "blues",
}


def parse_key(text: str) -> Key:
    """Parse ``Am``, ``A minor``, ``F# dorian`` or ``Bb`` into a :class:`Key`."""
    cleaned = text.strip()
    if not cleaned:
        return Key(0, "major")
    match = re.match(r"^([A-Ga-g])([#b♯♭]*)\s*(.*)$", cleaned)
    if not match:
        return Key(0, "major", text=cleaned)
    letter, accidentals, remainder = match.groups()
    tonic = LETTER_PC[letter.upper()] + _accidental_shift(accidentals)
    remainder = remainder.strip().lower()
    mode = MODE_WORDS.get(remainder)
    if mode is None:
        # `Am`, `Amin`, `Am7` -> minor; anything else falls back to major.
        mode = "minor" if remainder.startswith("m") and not remainder.startswith("maj") else "major"
    return Key(tonic, mode, text=cleaned)


def parse_roman(token: str, key: Key) -> Chord:
    """Resolve a roman-numeral chord such as ``iv``, ``bVII`` or ``V7``."""
    text = token.strip()
    match = _ROMAN_RE.match(text)
    if not match:
        raise TheoryError(f"not a roman numeral: {token!r}")
    accidental, numeral, suffix = match.groups()
    upper = numeral.upper()
    if upper not in ROMAN_DEGREES:
        raise TheoryError(f"not a roman numeral: {token!r}")
    degree = ROMAN_DEGREES[upper]
    alteration = _accidental_shift(accidental)
    root_pc = key.degree_pc(degree, alteration)

    quality = key.triad_quality(degree)
    if numeral.islower():
        quality = "dim" if suffix.startswith(("o", "°", "dim")) else "min"
    elif numeral.isupper():
        quality = "aug" if suffix.startswith(("+", "aug")) else "maj"

    seventh = suffix.lstrip("o°+")
    if seventh.startswith("7"):
        quality = {"maj": "7", "min": "min7", "dim": "dim7", "aug": "aug7"}.get(quality, "7")
    elif seventh.startswith("maj7"):
        quality = "maj7"
    return Chord(root_pc, quality, text=text)


def is_roman(token: str) -> bool:
    text = token.strip().lstrip("#b♯♭")
    if not text:
        return False
    head = re.match(r"^[ivIV]+", text)
    if not head:
        return False
    return head.group(0).upper() in ROMAN_DEGREES


def transpose_interval(from_key: Key, to_key: Key) -> int:
    """Smallest signed semitone distance between two tonics."""
    raw = (to_key.tonic_pc - from_key.tonic_pc) % 12
    return raw - 12 if raw > 6 else raw
