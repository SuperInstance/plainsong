"""Theory, parsing and arrangement."""

from __future__ import annotations

import unittest

from plainsong.notation import arrange, parse, theory
from plainsong.notation.arrange import ArrangeOptions

BASIC = """**TRACK: Test Piece**
[MetaData]
key: Am | tempo: 120 | swing: 0% | subdivision: 8th
time: 4/4

[V1] (Verse - 2 Bars)
Chords: | Am . . . | F . . . |
Melody: | A4 . C5 E5 | F4 . A4 C5 |
Lyrics: | one two | three four |
@bass | a1 . e2 . | f1 . c2 . | vel: 70
"""


class TestPitch(unittest.TestCase):
    def test_middle_c(self):
        self.assertEqual(theory.parse_pitch("C4"), 60)

    def test_accidentals(self):
        self.assertEqual(theory.parse_pitch("C#4"), 61)
        self.assertEqual(theory.parse_pitch("Db4"), 61)
        self.assertEqual(theory.parse_pitch("Cb4"), 59)

    def test_case_insensitive(self):
        self.assertEqual(theory.parse_pitch("a2"), theory.parse_pitch("A2"))

    def test_octaves(self):
        self.assertEqual(theory.parse_pitch("A0"), 21)
        self.assertEqual(theory.parse_pitch("C8"), 108)

    def test_default_octave(self):
        self.assertEqual(theory.parse_pitch("G", default_octave=3), theory.parse_pitch("G3"))

    def test_round_trip(self):
        for midi in range(21, 108):
            self.assertEqual(theory.parse_pitch(theory.pitch_name(midi)), midi)

    def test_rejects_nonsense(self):
        for token in ("H4", "", "hello", "4C"):
            with self.assertRaises(theory.TheoryError):
                theory.parse_pitch(token)


class TestChords(unittest.TestCase):
    def test_major_and_minor(self):
        self.assertEqual(theory.parse_chord("C").notes(4), [60, 64, 67])
        self.assertEqual(theory.parse_chord("Cm").notes(4), [60, 63, 67])

    def test_sevenths(self):
        self.assertEqual(theory.parse_chord("C7").notes(4), [60, 64, 67, 70])
        self.assertEqual(theory.parse_chord("Cmaj7").notes(4), [60, 64, 67, 71])
        self.assertEqual(theory.parse_chord("Cm7").notes(4), [60, 63, 67, 70])

    def test_slash_chord_puts_bass_underneath(self):
        notes = theory.parse_chord("C/G").notes(4)
        self.assertEqual(notes[0] % 12, 7)
        self.assertLess(notes[0], notes[1])

    def test_suspended_and_altered(self):
        self.assertEqual(theory.parse_chord("Csus4").notes(4), [60, 65, 67])
        self.assertEqual(theory.parse_chord("Cm7b5").notes(4), [60, 63, 66, 70])

    def test_transpose(self):
        self.assertEqual(theory.parse_chord("Am").transpose(3).name(), "Cm")

    def test_unknown_quality_raises(self):
        with self.assertRaises(theory.TheoryError):
            theory.parse_chord("Cwobble")


class TestKeys(unittest.TestCase):
    def test_minor_forms(self):
        for text in ("Am", "A minor", "Amin"):
            self.assertEqual(theory.parse_key(text).mode, "minor")

    def test_modes(self):
        self.assertEqual(theory.parse_key("D dorian").mode, "dorian")

    def test_roman_numerals_follow_the_key(self):
        key = theory.parse_key("Am")
        self.assertEqual(theory.parse_roman("i", key).name(), "Am")
        self.assertEqual(theory.parse_roman("iv", key).name(), "Dm")
        self.assertEqual(theory.parse_roman("V7", key).quality, "7")

    def test_interval_takes_the_short_way(self):
        self.assertEqual(theory.transpose_interval(theory.parse_key("C"), theory.parse_key("A")), -3)


class TestParser(unittest.TestCase):
    def setUp(self):
        self.score = parse(BASIC)

    def test_metadata(self):
        self.assertEqual(self.score.meta.title, "Test Piece")
        self.assertEqual(self.score.meta.tempo, 120)
        self.assertEqual(self.score.meta.key.name(), "Am")
        self.assertEqual(str(self.score.meta.meter), "4/4")

    def test_structure(self):
        self.assertEqual(len(self.score.sections), 1)
        section = self.score.sections[0]
        self.assertEqual(section.name, "V1")
        self.assertEqual(section.description, "Verse - 2 Bars")
        self.assertEqual(section.bar_count, 2)

    def test_players(self):
        self.assertEqual(self.score.player_names(), ["bass"])

    def test_velocity_option_is_not_a_bar(self):
        player = self.score.sections[0].players()[0]
        self.assertEqual(player.bar_count, 2)
        self.assertEqual(player.options["velocity"], 70)

    def test_no_errors(self):
        self.assertFalse(self.score.has_errors)

    def test_time_signature(self):
        score = parse("[A]\nkey: C | tempo: 90\ntime: 3/4\nChords: | C | G |\n")
        self.assertEqual(score.meta.meter.beats_per_bar, 3.0)

    def test_declaration_is_not_played(self):
        score = parse("[A]\nChords: | C | G |\n@player: piano, arpeggiate gently\n")
        self.assertEqual(score.player_names(), [])
        self.assertEqual(arrange(score).summary()["tracks"][0]["role"], "chords")

    def test_markdown_fence_is_stripped(self):
        score = parse("```plainsong\n[A]\nChords: | C | G |\n```\n")
        self.assertFalse(score.has_errors)
        self.assertEqual(score.sections[0].bar_count, 2)

    def test_prose_is_not_mistaken_for_notation(self):
        score = parse("[A]\nChords: | C | G |\nthis line is a note to the player, not music\n")
        self.assertEqual(len([line for line in score.sections[0].lines if line.cells]), 1)

    def test_relative_dialect_detected(self):
        score = parse("key: D minor\ntempo: 65\n\n[A]\n| i . . . | iv . . . |\n| 1 . 2 . | 3 . 2 . |\n")
        self.assertEqual(score.dialect, "relative")
        roles = {line.role for line in score.sections[0].lines if line.cells}
        self.assertEqual(roles, {"chords", "melody"})

    def test_empty_input_reports_an_error(self):
        self.assertTrue(parse("").has_errors)

    def test_mismatched_rows_warn(self):
        score = parse("[A]\nChords: | C | G | Am | F |\nMelody: | C4 | D4 |\n")
        self.assertTrue(any("covers" in diag.message for diag in score.warnings()))


class TestArrange(unittest.TestCase):
    def test_timing(self):
        arrangement = arrange(parse(BASIC))
        self.assertEqual(arrangement.total_beats, 8.0)
        self.assertAlmostEqual(arrangement.duration_seconds, 4.0, places=6)

    def test_voices(self):
        arrangement = arrange(parse(BASIC))
        roles = {track.role for track in arrangement.tracks}
        self.assertEqual(roles, {"chords", "melody", "player"})

    def test_bass_gets_a_bass_program(self):
        arrangement = arrange(parse(BASIC))
        bass = next(track for track in arrangement.tracks if track.name == "bass")
        self.assertTrue(32 <= bass.program <= 39)

    def test_lyrics_are_positioned(self):
        arrangement = arrange(parse(BASIC))
        self.assertEqual([lyric.text for lyric in arrangement.lyrics], ["one", "two", "three", "four"])
        self.assertEqual(arrangement.lyrics[0].start, 0.0)
        self.assertEqual(arrangement.lyrics[2].start, 4.0)

    def test_tokens_divide_the_bar(self):
        for count in (3, 5, 7, 12, 17):
            tokens = " ".join(["C4"] * count)
            arrangement = arrange(parse(f"[A]\nMelody: | {tokens} |\n"))
            self.assertEqual(arrangement.total_beats, 4.0, f"{count} tokens")
            notes = arrangement.tracks[0].notes
            self.assertEqual(len(notes), count)
            self.assertAlmostEqual(notes[-1].end, 4.0, places=6)

    def test_grid_mode_reports_what_it_drops(self):
        tokens = " ".join(["C4"] * 17)
        score = parse(f"[A]\nMelody: | {tokens} |\n")
        arrangement = arrange(score, ArrangeOptions(bar_fill="grid"))
        self.assertTrue(any("dropped" in diag.message for diag in arrangement.diagnostics))

    def test_dot_sustains_the_previous_note(self):
        arrangement = arrange(parse("[A]\nMelody: | C4 . . . |\n"))
        notes = arrangement.tracks[0].notes
        self.assertEqual(len(notes), 1)
        self.assertAlmostEqual(notes[0].duration, 4.0, places=6)

    def test_rest_ends_the_note(self):
        arrangement = arrange(parse("[A]\nMelody: | C4 (rest) C4 . |\n"))
        notes = arrangement.tracks[0].notes
        self.assertEqual(len(notes), 2)
        self.assertAlmostEqual(notes[0].duration, 1.0, places=6)

    def test_tilde_extends_a_note(self):
        arrangement = arrange(parse("[A]\nMelody: | C4~~~ D4~~~ |\n"))
        notes = arrangement.tracks[0].notes
        self.assertEqual(len(notes), 2)
        self.assertAlmostEqual(notes[0].duration, 2.0, places=6)

    def test_chord_stack_sounds_together(self):
        arrangement = arrange(parse("[A]\n@keys | c3-e3-g3 . . . |\n"))
        notes = arrangement.tracks[0].notes
        self.assertEqual(len(notes), 3)
        self.assertEqual({note.start for note in notes}, {0.0})

    def test_repeated_rows_run_in_sequence(self):
        arrangement = arrange(parse("[A]\nMelody: | C4 | D4 |\nMelody: | E4 | F4 |\n"))
        self.assertEqual(arrangement.total_beats, 16.0)
        starts = sorted(note.start for note in arrangement.tracks[0].notes)
        self.assertEqual(starts, [0.0, 4.0, 8.0, 12.0])

    def test_different_rows_sound_together(self):
        arrangement = arrange(parse("[A]\nChords: | C |\nMelody: | E4 |\n"))
        self.assertEqual(arrangement.total_beats, 4.0)

    def test_unbarred_rows_use_the_subdivision(self):
        arrangement = arrange(parse("[A]\nMelody: C4~~~ D4~~~ E4~~~ F4~~~\n"))
        notes = arrangement.tracks[0].notes
        self.assertEqual(len(notes), 4)
        self.assertAlmostEqual(notes[0].duration, 2.0, places=6)

    def test_swing_delays_the_offbeat(self):
        text = "[A]\nkey: C | tempo: 120 | swing: 100%\nMelody: | C4 D4 C4 D4 C4 D4 C4 D4 |\n"
        notes = arrange(parse(text)).tracks[0].notes
        self.assertAlmostEqual(notes[0].start, 0.0, places=6)
        self.assertGreater(notes[1].start, 0.5)

    def test_humanising_is_deterministic(self):
        first = arrange(parse(BASIC))
        second = arrange(parse(BASIC))
        self.assertEqual(
            [note.velocity for _t, note in first.iter_notes()],
            [note.velocity for _t, note in second.iter_notes()],
        )

    def test_relative_degrees_resolve_against_the_key(self):
        score = parse("key: C major\ntempo: 100\n\n[A]\n| 1 . 3 . | 5 . 1^ . |\n")
        self.assertEqual(score.dialect, "relative")
        pitches = [note.pitch for note in arrange(score).tracks[0].notes]
        self.assertEqual(pitches, [60, 64, 67, 72])


class TestRoundTrip(unittest.TestCase):
    """Emitting notation and reading it back must give the same music."""

    def test_transposing_repeatedly_does_not_grow_the_bars(self):
        """A player row with options used to gain an empty bar every transpose.

        `_format_row` closed the row with `|` and then wrote ` | vel: 70`, so the
        text carried `... | | vel: 70`. Reading that back saw the empty cell as a
        real bar, so each round trip pushed the player row one bar further out of
        step with the rest of its section -- silent corruption of a file the user
        thought they had only changed the key of.
        """
        from plainsong.transform import transpose

        text = BASIC
        for key in ("D", "E", "F", "G"):
            text = transpose(text, key)
            widths = {
                line.role: len(line.cells)
                for section in parse(text).sections
                for line in section.lines
            }
            self.assertEqual(
                set(widths.values()), {2}, f"a row changed width after transposing to {key}"
            )

    def test_emitted_player_rows_read_back_identically(self):
        """The text a transpose writes must parse to the same shape it came from."""
        from plainsong.transform import to_text

        original = parse(BASIC)
        reparsed = parse(to_text(original))
        self.assertEqual(
            [(line.role, len(line.cells)) for line in original.sections[0].lines],
            [(line.role, len(line.cells)) for line in reparsed.sections[0].lines],
        )


class TestDocumentedNotation(unittest.TestCase):
    """Every example in the prose must be notation this compiler accepts.

    The academy shipped for months teaching a language that did not exist -- one
    lesson on "dynamics and velocity" was a bouncing-ball physics simulation,
    because a generator saw the word velocity. Nothing caught it: `plainsong
    check` walked only `.song` files, and the academy contains none, so pointing
    the check at it passed while every lesson in it was wrong.

    A block tagged ```plainsong is a promise. Syntax that is only proposed goes
    in a ```plainsong-proposed block, and anything that is not Plainsong at all
    should not claim to be.
    """

    def _blocks(self):
        import re
        from pathlib import Path

        fence = re.compile(r"^```(?:plainsong|tap)[ \t]*$(.*?)^```", re.S | re.M)
        root = Path(__file__).resolve().parent.parent
        for markdown in sorted(root.rglob("*.md")):
            if "legacy" in markdown.parts or "node_modules" in markdown.parts:
                continue
            text = markdown.read_text(encoding="utf-8", errors="replace")
            for match in fence.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                yield f"{markdown.relative_to(root)}:{line}", match.group(1)

    def test_every_documented_example_compiles(self):
        for label, block in self._blocks():
            with self.subTest(example=label):
                score = parse(block)
                self.assertEqual(
                    [diagnostic.format() for diagnostic in score.errors()], [], label
                )

    def test_every_documented_example_makes_a_sound(self):
        """Parsing is not enough: a block that yields no notes teaches nothing."""
        for label, block in self._blocks():
            with self.subTest(example=label):
                self.assertGreater(arrange(parse(block)).note_count, 0, label)


if __name__ == "__main__":
    unittest.main()
