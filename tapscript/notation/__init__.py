"""Notation: parsing, theory, arrangement and text emission."""

from .arrange import ArrangeOptions, arrange
from .ir import Arrangement, Diagnostic, Meter, Metadata, Note, Score, Section, Track
from .parser import parse, parse_file
from .theory import Chord, Key, TheoryError, parse_chord, parse_key, parse_pitch, pitch_name

__all__ = [
    "ArrangeOptions",
    "Arrangement",
    "Chord",
    "Diagnostic",
    "Key",
    "Meter",
    "Metadata",
    "Note",
    "Score",
    "Section",
    "TheoryError",
    "Track",
    "arrange",
    "parse",
    "parse_chord",
    "parse_file",
    "parse_key",
    "parse_pitch",
    "pitch_name",
]
