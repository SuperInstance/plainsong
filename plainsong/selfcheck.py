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


def check_chord_vocabulary() -> tuple[bool, str]:
    """Chord symbols are read by rule, so compound spellings work unenumerated.

    Each case here fails under a lookup table. `C7b9#11` and `F13#11` are not
    in any table because nobody types every combination; `C7M` is how Brazil
    writes a major seventh and was the largest group of unreadable chords in
    the bundled songbook; `G7alt` names a scale rather than a note set.
    """
    from .notation.theory import TheoryError, parse_chord

    expected = {
        # symbol      -> semitones above the root
        "C7b9#11": (0, 4, 7, 10, 13, 18),
        "F13#11": (0, 4, 7, 10, 14, 18, 21),
        "C7M": (0, 4, 7, 11),        # sétima maior
        "EbMaj7": (0, 4, 7, 11),     # capitalised, which used to refuse
        "C13": (0, 4, 7, 10, 14, 21),  # no eleventh: it fights the major third
        "Cm13": (0, 3, 7, 10, 14, 17, 21),  # minor third, so the eleventh stays
        "C9sus4": (0, 5, 7, 10, 14),   # no third, so nothing to avoid
        "Bb-7": (0, 3, 7, 10),       # a minus before a seven is minor
    }
    for symbol, intervals in expected.items():
        try:
            got = parse_chord(symbol).intervals()
        except TheoryError as error:
            return False, f"{symbol} was refused: {error}"
        if got != intervals:
            return False, f"{symbol} gave {got}, expected {intervals}"

    # `alt` subtracts. The altered scale has no natural fifth and no natural
    # ninth, and a chord that grew them would be the wrong chord entirely.
    alt = parse_chord("C7alt")
    if 7 in alt.intervals():
        return False, "C7alt kept its natural fifth"
    if 14 in alt.intervals():
        return False, "C7alt kept its natural ninth"

    # Reading more spellings must not change one already understood.
    if parse_chord("Cmaj7").intervals() != (0, 4, 7, 11):
        return False, "the common vocabulary moved"

    return True, f"{len(expected)} compound spellings derived, none enumerated"


def check_chord_transposition() -> tuple[bool, str]:
    """A chord the quality names cannot express still survives a transpose.

    No quality string can carry `b9#11`, so reconstructing the symbol from one
    would drop the alterations silently. The suffix is carried verbatim and
    only the root is respelled, which this checks by going round the circle.
    """
    from .notation.theory import parse_chord

    for symbol in ("C7b9#11", "G7alt", "C7M", "C6/9", "Cø", "Bb-7", "Cm/Bb"):
        start = parse_chord(symbol)
        here = start
        for _ in range(12):
            here = parse_chord(here.transpose(1).name())
        if {(start.root_pc + i) % 12 for i in start.intervals()} != {
            (here.root_pc + i) % 12 for i in here.intervals()
        }:
            return False, f"{symbol} did not survive twelve transpositions"
    return True, "seven symbols round the circle unchanged"


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
    shifts = {later - earlier for earlier, later in zip(melody_before, melody_after, strict=True)}
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
        for before, after in zip(chord_before, chord_after, strict=True)
        if (before + 3) % 12 != after
    ]
    if wrong:
        return False, f"{len(wrong)} chord tone(s) did not move by 3 semitones"

    # A target we cannot read is refused rather than guessed at. `parse_key` is
    # forgiving so a hand-typed header cannot stop a file loading, and it reads
    # "banana" as B major -- which as a transpose target would quietly move the
    # whole score by a semitone.
    from .notation.theory import TheoryError

    for bad in ("banana", "Z", "hello world"):
        try:
            transpose(SAMPLE, bad)
        except TheoryError:
            continue
        return False, f"{bad!r} was accepted as a key"

    return True, "melody and chord row both moved Am -> C; an unreadable key is refused"


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


# -- arrival-centric timing --------------------------------------------------

STAGE_MUSIC = """**TRACK: Stage Sample**
[MetaData]
key: Dm | tempo: 96 | time: 4/4

[A] (2 Bars)
@timpani | d2 . . . | d2 . . . |
@organ   | d3 . . . | a2 . . . |
"""

STAGE_BLOCK = """[Stage]
listener: conductor
temperature: 20
@timpani: pos 4,-6 | speech: percussion
@organ:   pos 0,-12 | speech: organ-large

"""

# The same music, with and without the stage. The pair is the control for
# "declaring a stage changes nothing until you ask it to".
STAGE_SAMPLE = STAGE_MUSIC.replace("[A]", STAGE_BLOCK + "[A]", 1)


def check_stage_is_inert() -> tuple[bool, str]:
    """Notation without a stage compiles to exactly what it always did."""
    from .notation import arrange, parse
    from .notation.arrange import ArrangeOptions
    from .render.midi import midi_bytes

    plain = arrange(parse(SAMPLE))
    if plain.stage is not None:
        return False, "a file with no [Stage] block picked one up anyway"
    solved = [note for _track, note in plain.iter_notes() if note.emission is not None]
    if solved:
        return False, f"{len(solved)} notes carry solved times without a stage"

    written = midi_bytes(plain)
    framed = midi_bytes(arrange(parse(SAMPLE), ArrangeOptions(frame="audience")))
    if written != framed:
        return False, "asking for a listener changed a file that has no stage"

    # The same music with a stage, rendered in the score frame, is the control.
    control = midi_bytes(arrange(parse(STAGE_MUSIC)))
    scored = midi_bytes(arrange(parse(STAGE_SAMPLE), ArrangeOptions(frame="score")))
    if control != scored:
        return False, "the score frame did not reproduce the uncompensated render"
    return True, f"{len(written)} bytes identical with and without a listener"


def check_arrival_solver() -> tuple[bool, str]:
    """Players act early by the right amount, and their sound lands together."""
    from .notation import arrange, parse
    from .perform.solve import analyse

    arrangement = arrange(parse(STAGE_SAMPLE))
    if arrangement.stage is None:
        return False, "the [Stage] block was not read"

    report = analyse(arrangement)
    voices = {voice["voice"]: voice for voice in report["solution"]["voices"]}
    if set(voices) != {"timpani", "organ"}:
        return False, f"solved for {sorted(voices)}"

    # 12 metres is 35ms at 20 degrees, and a large pipe takes 140ms to speak.
    if not 33.0 <= voices["organ"]["propagation_ms"] <= 37.0:
        return False, f"12 metres solved as {voices['organ']['propagation_ms']}ms"
    if voices["organ"]["emission_ms"] > voices["timpani"]["emission_ms"]:
        return False, "the organ is not acting before the timpani"
    if report["solution"]["spread_ms"] > 1.0:
        return False, f"arrivals are {report['solution']['spread_ms']}ms apart at the podium"

    first = {
        track.name: min(note.arrival_time for note in track.notes)
        for track in arrangement.tracks
    }
    if abs(first["timpani"] - first["organ"]) > 1e-6:
        return False, f"first arrivals differ by {abs(first['timpani'] - first['organ'])} beats"
    if min(note.emission_time for _track, note in arrangement.iter_notes()) < 0.0:
        return False, "somebody has to play before the piece starts"
    return True, (
        f"organ acts {abs(voices['organ']['emission_ms']):.0f}ms early, "
        f"timpani {abs(voices['timpani']['emission_ms']):.0f}ms, arrivals within 1ms"
    )


def check_conducting() -> tuple[bool, str]:
    """One directive moves every voice's arrival together, their hands apart."""
    from .notation import arrange, parse
    from .perform import conduct

    written = arrange(parse(STAGE_SAMPLE))
    conducted = conduct.apply(
        written,
        {"directives": [{"action": "half_time", "intensity": 1.0, "duration_beats": 8}]},
    )
    if conducted.total_beats <= written.total_beats:
        return False, "half time did not make the music longer"

    def lead(arrangement, name):
        track = next(item for item in arrangement.tracks if item.name == name)
        note = min(track.notes, key=lambda item: item.start)
        return note.arrival_time - note.emission_time

    landing = {
        track.name: min(note.arrival_time for note in track.notes) for track in conducted.tracks
    }
    if abs(landing["timpani"] - landing["organ"]) > 1e-6:
        return False, "the directive pulled the ensemble apart"
    organ = lead(conducted, "organ") - lead(written, "organ")
    timpani = lead(conducted, "timpani") - lead(written, "timpani")
    if abs(organ) <= abs(timpani):
        return False, "every voice's hands moved by the same amount"
    return True, (
        f"arrivals stayed together; the organ's lead moved {organ * 1000:.0f} thousandths of a "
        f"beat against the timpani's {timpani * 1000:.0f}"
    )


def check_directive_vocabulary() -> tuple[bool, str]:
    """anticipate moves the hands and leaves the sound; push_forward moves both."""
    from .notation import arrange, parse
    from .perform import conduct

    written = arrange(parse(STAGE_SAMPLE))

    def first(arrangement, name):
        """The first note of a voice, with the global lead-in taken back off."""
        track = next(item for item in arrangement.tracks if item.name == name)
        note = min(track.notes, key=lambda item: item.start)
        return (
            note.emission_time - arrangement.lead_in,
            note.arrival_time - arrangement.lead_in,
        )

    anticipated = conduct.apply(written, {"directives": [{"action": "anticipate", "intensity": 1.0}]})
    pushed = conduct.apply(written, {"directives": [{"action": "push_forward", "intensity": 1.0}]})

    for name in ("organ", "timpani"):
        (base_emit, base_arrive) = first(written, name)
        (early_emit, early_arrive) = first(anticipated, name)
        (_ahead_emit, ahead_arrive) = first(pushed, name)
        if abs(early_emit - base_emit) < 1e-9:
            return False, f"anticipate did not move {name}'s hands"
        if abs(early_arrive - base_arrive) > 1e-9:
            return False, f"anticipate moved {name}'s sound, which is not what it means"
        if ahead_arrive >= base_arrive:
            return False, f"push_forward did not move {name}'s sound forward"

    # A push is one instruction to the whole band: everybody's hands move by the
    # same amount, so the gaps between them are exactly as they were.
    gap_before = first(written, "timpani")[0] - first(written, "organ")[0]
    gap_after = first(pushed, "timpani")[0] - first(pushed, "organ")[0]
    if abs(gap_before - gap_after) > 1e-9:
        return False, f"a push changed the gap between the players: {gap_before} -> {gap_after}"

    reading = conduct.read({"directives": [{"action": "reharmonize"}, {"action": "lay_back"}]})
    if reading.unhandled() != ["reharmonize"]:
        return False, f"unhandled actions reported as {reading.unhandled()}"
    return True, (
        "anticipate moved the hands only, push_forward moved both, and the players stayed "
        f"{gap_after:.4f} beats apart"
    )


def check_lyric_binding() -> tuple[bool, str]:
    """A bound syllable sounds on its note, and the default leaves files alone."""
    from .notation import arrange, parse
    from .notation.arrange import ArrangeOptions

    # `came` is written directly beneath `C5`. The lyric row divides the bar
    # into three and the melody into four, so written as-is it sounds two
    # thirds of a beat after the note it sits under.
    text = (
        "[V1]\n"
        "Melody: | A4  .   C5  E5 |\n"
        "Lyrics: | the tide came  |\n"
    )
    loose = arrange(parse(text), ArrangeOptions(humanize=False))
    starts = [round(event.start, 3) for event in loose.lyrics]
    if starts != [0.0, 1.333, 2.667]:
        return False, f"the default moved: expected thirds of the bar, got {starts}"

    bound = arrange(parse(text), ArrangeOptions(humanize=False, lyrics="bound"))
    starts = [round(event.start, 3) for event in bound.lyrics]
    if starts != [0.0, 2.0, 3.0]:
        return False, f"syllables did not land on their notes: {starts}"
    if round(bound.lyrics[0].duration, 3) != 2.0:
        return False, (
            "a word should carry until the next word's note, so `the` lasts while A4 is "
            f"held; got {bound.lyrics[0].duration}"
        )

    # Padding holds a column under a sustaining melody; read as melisma it
    # would consume a note and push the next word off the end of the bar.
    padded = arrange(
        parse("[V1]\nMelody: | Bb3 . F4 . |\nLyrics: | sing . every . |\n"),
        ArrangeOptions(humanize=False, lyrics="bound"),
    )
    if [event.text for event in padded.lyrics] != ["sing", "every"]:
        return False, f"padding was not ignored: {[e.text for e in padded.lyrics]}"
    if [round(e.start, 3) for e in padded.lyrics] != [0.0, 2.0]:
        return False, f"words did not land on Bb3 and F4: {[e.start for e in padded.lyrics]}"

    return True, "syllables bind to notes, padding binds to nothing, and the default is unmoved"
