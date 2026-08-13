"""Checks that specs point at.

Each function returns ``(ok, detail)`` and must run without network access,
without optional dependencies, and without writing outside a temporary
directory. They are the executable half of ``specs/``.
"""

from __future__ import annotations

import struct
import tempfile
import wave
from pathlib import Path

SAMPLE = """**TRACK: Spec Sample**
[MetaData]
key: Am | tempo: 96 | swing: 0% | subdivision: 8th
time: 4/4

[V1] (Verse - 2 Bars)
Chords: | Am . . . | F . . . |
Melody: | A4 . C5 E5 | F4 . A4 C5 |
Lyrics: | one two | three four |
@bass | a1 . e2 . | f1 . c2 . | vel: 70
"""


def check_parse() -> tuple[bool, str]:
    """Notation parses into the expected structure."""
    from .notation import parse

    score = parse(SAMPLE)
    if score.has_errors:
        return False, "; ".join(diag.message for diag in score.errors())
    if len(score.sections) != 1:
        return False, f"expected 1 section, got {len(score.sections)}"
    if score.meta.tempo != 96:
        return False, f"tempo read as {score.meta.tempo}"
    if score.meta.key.name() != "Am":
        return False, f"key read as {score.meta.key.name()}"
    if score.player_names() != ["bass"]:
        return False, f"players read as {score.player_names()}"
    return True, "sections, metadata and players all read correctly"


def check_arrange() -> tuple[bool, str]:
    """Bars divide evenly and voices land where they should."""
    from .notation import arrange, parse

    arrangement = arrange(parse(SAMPLE))
    if arrangement.total_beats != 8.0:
        return False, f"expected 8 beats, got {arrangement.total_beats}"
    roles = {track.role for track in arrangement.tracks}
    if not {"chords", "melody", "player"} <= roles:
        return False, f"missing voices: {roles}"
    if arrangement.note_count == 0:
        return False, "no notes were produced"
    if len(arrangement.lyrics) != 4:
        return False, f"expected 4 lyric events, got {len(arrangement.lyrics)}"
    return True, f"{arrangement.note_count} notes over {arrangement.total_beats:g} beats"


def check_bar_fill() -> tuple[bool, str]:
    """An unusual token count divides its bar instead of spilling over."""
    from .notation import arrange, parse

    text = (
        "[A]\nMelody: | C4 D4 E4 F4 G4 A4 B4 C5 C4 D4 E4 F4 G4 A4 B4 C5 D5 |\n"
    )
    arrangement = arrange(parse(text))
    if arrangement.total_beats != 4.0:
        return False, f"17 tokens should still fill one bar, got {arrangement.total_beats} beats"
    notes = arrangement.tracks[0].notes
    if len(notes) != 17:
        return False, f"expected all 17 notes, got {len(notes)}"
    last = notes[-1]
    if last.end > 4.0 + 1e-6:
        return False, f"last note runs past the bar to {last.end}"
    return True, "17 tokens divided one bar with nothing lost"


def check_midi_bytes() -> tuple[bool, str]:
    """The MIDI writer emits a structurally valid format-1 file."""
    from .notation import arrange, parse
    from .render.midi import midi_bytes

    data = midi_bytes(arrange(parse(SAMPLE)))
    if data[:4] != b"MThd":
        return False, "missing MThd header"
    length, fmt, tracks, division = struct.unpack(">IHHH", data[4:14])
    if length != 6 or fmt != 1:
        return False, f"unexpected header: length={length} format={fmt}"
    if tracks < 2:
        return False, f"expected a conductor track plus voices, got {tracks}"

    position = 14
    seen = 0
    while position < len(data):
        if data[position : position + 4] != b"MTrk":
            return False, f"expected MTrk at byte {position}"
        size = struct.unpack(">I", data[position + 4 : position + 8])[0]
        position += 8 + size
        seen += 1
    if position != len(data):
        return False, "trailing bytes after the last track"
    if seen != tracks:
        return False, f"header claims {tracks} tracks, found {seen}"
    return True, f"{len(data)} bytes, {tracks} tracks at {division} ticks per beat"


def check_audio() -> tuple[bool, str]:
    """The built-in synthesiser produces real audio with no dependencies."""
    from .notation import arrange, parse
    from .render.audio import AudioOptions, Synthesiser

    arrangement = arrange(parse(SAMPLE))
    synth = Synthesiser(AudioOptions(sample_rate=8000, tail=0.2))
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "check.wav"
        synth.write(arrangement, target)
        with wave.open(str(target), "rb") as handle:
            frames = handle.getnframes()
            raw = handle.readframes(min(frames, 40000))
    if frames < 8000:
        return False, f"only {frames} frames of audio"
    peak = 0
    for index in range(0, len(raw) - 1, 2):
        value = int.from_bytes(raw[index : index + 2], "little", signed=True)
        peak = max(peak, abs(value))
    if peak < 1000:
        return False, f"audio is effectively silent (peak {peak})"
    return True, f"{frames} frames, peak {peak}, backend {synth.backend}"


def check_round_trip() -> tuple[bool, str]:
    """Notation survives being written back out and read in again."""
    from .notation import arrange, parse
    from .transform import to_text

    original = parse(SAMPLE)
    reparsed = parse(to_text(original))
    if reparsed.has_errors:
        return False, "; ".join(diag.message for diag in reparsed.errors())
    first, second = arrange(original), arrange(reparsed)
    if first.note_count != second.note_count:
        return False, f"note count changed: {first.note_count} -> {second.note_count}"
    if abs(first.total_beats - second.total_beats) > 1e-6:
        return False, f"length changed: {first.total_beats} -> {second.total_beats}"
    return True, f"{first.note_count} notes preserved"


def check_transpose() -> tuple[bool, str]:
    """Transposing moves every voice, including the chord row."""
    from .notation import arrange, parse
    from .transform import transpose

    original = arrange(parse(SAMPLE))
    moved = arrange(parse(transpose(SAMPLE, "C")))
    if original.note_count != moved.note_count:
        return False, f"note count changed: {original.note_count} -> {moved.note_count}"

    def pitches(arrangement, role):
        return [
            note.pitch
            for track in arrangement.tracks
            if track.role == role
            for note in track.notes
        ]

    melody_before, melody_after = pitches(original, "melody"), pitches(moved, "melody")
    shifts = {later - earlier for earlier, later in zip(melody_before, melody_after)}
    if shifts != {3}:
        return False, f"melody shifted by {sorted(shifts)}, expected 3 semitones"

    # Chord voicings are re-derived from the new root and stay in their
    # register, so compare pitch classes rather than absolute pitches.
    chord_before = [pitch % 12 for pitch in pitches(original, "chords")]
    chord_after = [pitch % 12 for pitch in pitches(moved, "chords")]
    if not chord_before:
        return False, "the chord row produced no notes"
    wrong = [
        (before, after)
        for before, after in zip(chord_before, chord_after)
        if (before + 3) % 12 != after
    ]
    if wrong:
        return False, f"{len(wrong)} chord tone(s) did not move by 3 semitones"
    return True, "melody and chord row both moved Am -> C"


def check_providers() -> tuple[bool, str]:
    """The provider catalogue loads and every entry has an adapter."""
    from .llm.catalog import load_catalog
    from .llm.providers import ADAPTERS

    catalog = load_catalog()
    if len(catalog) < 5:
        return False, f"only {len(catalog)} providers in the catalogue"
    missing = sorted({info.api for info in catalog.values()} - set(ADAPTERS))
    if missing:
        return False, f"no adapter for API shapes: {', '.join(missing)}"
    return True, f"{len(catalog)} providers across {len(ADAPTERS)} API shapes"


def check_offline_provider() -> tuple[bool, str]:
    """There is always a usable provider, even with no key and no network."""
    from .llm import build_provider

    provider = build_provider("echo")
    ok, detail = provider.check()
    return ok, detail


def check_tools() -> tuple[bool, str]:
    """Agent tools are registered and describe themselves properly."""
    from .agent.tools import ToolRegistry

    registry = ToolRegistry()
    specs = registry.specs()
    if len(specs) < 6:
        return False, f"only {len(specs)} tools registered"
    for spec in specs:
        if not spec.description:
            return False, f"tool {spec.name} has no description"
        if spec.parameters.get("type") != "object":
            return False, f"tool {spec.name} has a malformed schema"
    return True, f"{len(specs)} tools: {', '.join(sorted(spec.name for spec in specs))}"


def check_corpus() -> tuple[bool, str]:
    """The bundled library still parses with the current engine."""
    from .library import Library

    library = Library()
    entries = library.entries(limit=120)
    if not entries:
        return True, "skipped: no library on this install"
    failures: list[str] = []
    for entry in entries:
        score = library.parse(entry)
        if score.has_errors:
            failures.append(entry.name)
    if failures:
        return False, f"{len(failures)} of {len(entries)} failed: {', '.join(failures[:5])}"
    return True, f"{len(entries)} library files parsed"
