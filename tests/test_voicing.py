"""Which notes of a chord actually sound.

The rule under test is an ordering, not a table: the fifth is given up first,
the root second, and the third, the seventh and whatever extension the symbol
was written for are kept. Every case below is chosen because it comes out wrong
under the previous behaviour, which took the lowest four notes and therefore
discarded the named extension in half the cases where the cap bit at all.
"""

from __future__ import annotations

import unittest

from plainsong.notation.theory import parse_chord
from plainsong.notation.voicing import NATURAL, STRATEGIES, voice

NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")


def played(symbol: str, strategy: str = "guide", limit: int = 4) -> list[str]:
    chord = parse_chord(symbol)
    return [NAMES[n % 12] for n in voice(chord, octave=3, limit=limit, strategy=strategy)]


class TestTheNamedNoteSurvives(unittest.TestCase):
    """A symbol is written a particular way for a reason."""

    def test_a_ninth_chord_has_a_ninth(self):
        # The headline defect. `D9` used to render as `D F# A C` -- which is
        # `D7`, and is the one thing `D9` is not.
        self.assertIn("E", played("D9"))
        self.assertNotIn("E", played("D9", "stack"))

    def test_the_hendrix_chord_keeps_its_sharp_ninth(self):
        self.assertIn("G", played("E7#9"))
        self.assertNotIn("G", played("E7#9", "stack"))

    def test_a_thirteenth_keeps_its_thirteenth(self):
        self.assertIn("A", played("C13"))

    def test_an_altered_dominant_keeps_its_alterations(self):
        # `G7alt` names four altered degrees and cannot fit them all in four
        # voices, but it must not come out as a plain `G7`.
        notes = set(played("G7alt"))
        self.assertNotEqual(notes, set(played("G7")))
        self.assertTrue(notes & {"Ab", "Db", "Eb"}, f"no alteration survived: {notes}")


class TestWhatGetsGivenUp(unittest.TestCase):
    def test_the_fifth_goes_first(self):
        # C13 is C E G Bb D A. Six notes into four voices: the G leaves.
        self.assertNotIn("G", played("C13"))
        self.assertIn("E", played("C13"))  # third
        self.assertIn("Bb", played("C13"))  # seventh

    def test_the_root_goes_second(self):
        # ...which produces the standard rootless voicing without being told
        # about rootless voicings. C13 -> E Bb D A is the Bill Evans A form.
        self.assertEqual(played("C13"), ["E", "Bb", "D", "A"])

    def test_the_guide_tones_never_go(self):
        for symbol in ("C13", "D9", "E7#9", "Am11", "F13#11", "Cmaj9", "G7alt"):
            with self.subTest(symbol=symbol):
                chord = parse_chord(symbol)
                notes = {n % 12 for n in voice(chord, 3, 4, "guide")}
                for degree in (3, 7):
                    if degree in chord.degrees:
                        self.assertIn(
                            (chord.root_pc + chord.degrees[degree]) % 12,
                            notes,
                            f"{symbol} lost its {degree}",
                        )

    def test_an_altered_fifth_is_identity_and_stays(self):
        # `C7#5` without its sharp fifth is `C7`. The drop order must not treat
        # an altered degree as ordinary, or it throws away the whole point.
        self.assertIn("Ab", played("C7#5"))
        self.assertIn("Gb", played("C7b5"))


class TestNothingGetsWorse(unittest.TestCase):
    def test_small_chords_are_untouched(self):
        # Nothing with four notes or fewer should move at all -- that is what
        # keeps the change confined to 71 files out of 6,321.
        for symbol in ("C", "Am", "G7", "Cmaj7", "Dm7", "F6", "Bdim7", "Csus4"):
            with self.subTest(symbol=symbol):
                self.assertEqual(played(symbol, "guide"), played(symbol, "stack"))

    def test_a_slash_bass_no_longer_costs_the_chord_a_note(self):
        # The old cap counted the bass note against the chord, so `Am7/G` lost
        # its seventh to make room for its own bass and sounded like `Am/G`.
        notes = played("Am7/G")
        self.assertEqual(notes[0], "G")  # the bass, below
        self.assertIn("G", notes[1:])  # and the seventh, still there
        self.assertEqual(len(notes), 5)

    def test_a_chord_with_no_degree_map_still_voices(self):
        # Roman numerals build a Chord straight from intervals, with no degree
        # labels. Without them there is no way to tell a fifth from a seventh,
        # so the voicer must fall back rather than guess.
        from plainsong.notation.theory import Chord

        bare = Chord(0, "maj7", intervals=(0, 4, 7, 11))
        self.assertEqual(len(voice(bare, 3, 4)), 4)


class TestEveryStrategyIsUsable(unittest.TestCase):
    def test_each_named_strategy_returns_notes_in_range(self):
        for name in STRATEGIES:
            for symbol in ("C13", "G7alt", "Am7/G", "C", "F13#11"):
                with self.subTest(strategy=name, symbol=symbol):
                    notes = list(voice(parse_chord(symbol), 3, 4, name))
                    self.assertTrue(notes)
                    self.assertTrue(all(0 <= n <= 127 for n in notes))

    def test_an_unknown_strategy_falls_back_rather_than_raising(self):
        # A typo in a config file must not take the compiler down.
        self.assertTrue(list(voice(parse_chord("C13"), 3, 4, "nonsense")))

    def test_natural_covers_every_degree_the_parser_emits(self):
        # `NATURAL` decides which degrees count as altered, and a degree
        # missing from it would silently never be treated as identity.
        from plainsong.notation.chordsymbol import DEGREE_SEMITONES

        self.assertEqual(set(DEGREE_SEMITONES), set(NATURAL))
        self.assertEqual(DEGREE_SEMITONES, NATURAL)


class TestTheSettingIsReachable(unittest.TestCase):
    """1.0.0 changed how existing files sound and shipped no way back.

    The strategy was selectable on `ArrangeOptions` but nothing read it from
    configuration, so `core.voicing` did nothing at all.
    """

    SONG = (
        "**TRACK: Voicing**\n"
        "[MetaData]\nkey: C | tempo: 100 | time: 4/4\n\n"
        "[V1] (Verse - 1 Bars)\nChords: | D9 . . . |\n"
    )

    def _compile(self, strategy=None, *, render=None):
        from plainsong import pipeline
        from plainsong.runtime.config import load_config

        config = load_config()
        if strategy is not None:
            config.data.setdefault("core", {})["voicing"] = strategy
        if render is not None:
            config.data.setdefault("render", {})["voicing"] = render
        result = pipeline.compile_text(self.SONG, config=config)
        pitches = sorted(note.pitch for track in result.arrangement.tracks for note in track.notes)
        return [p % 12 for p in pitches], result.diagnostics

    def test_core_voicing_selects_the_strategy(self):
        guide, _ = self._compile("guide")
        stack, _ = self._compile("stack")
        self.assertNotEqual(guide, stack)
        # D9 written D F# A C E. `guide` gives up the fifth to keep the ninth;
        # `stack` is the pre-1.0.0 rendering, which is a D7.
        self.assertEqual(guide, [2, 6, 0, 4])  # D F# C E
        self.assertEqual(stack, [2, 6, 9, 0])  # D F# A C

    def test_an_unknown_strategy_says_so(self):
        # Falling back in silence is indistinguishable from being honoured.
        _, diagnostics = self._compile("stak")
        messages = [d.message for d in diagnostics]
        self.assertTrue(any("unknown voicing" in m and "stak" in m for m in messages), messages)

    def test_the_name_the_1_0_0_docs_printed_still_works(self):
        # docs/voicing.md said `render.voicing` while nothing read either name.
        # Anyone who followed it would otherwise still be ignored in silence.
        self.assertEqual(self._compile(render="stack")[0], self._compile("stack")[0])

    def test_core_wins_when_both_are_written(self):
        # `[core]` carries a default, so "was it written down?" can only be
        # answered for a value that differs from it. That is the precedence
        # documented in docs/voicing.md, and the collision needs two spellings
        # of one setting disagreeing to arise at all.
        both, _ = self._compile("shell", render="stack")
        self.assertEqual(both, self._compile("shell")[0])
        self.assertNotEqual(both, self._compile("stack")[0])

    def test_the_default_is_unchanged_when_nothing_is_configured(self):
        from plainsong import pipeline

        default = pipeline.compile_text(self.SONG)
        pitches = [p % 12 for p in sorted(n.pitch for t in default.arrangement.tracks for n in t.notes)]
        self.assertEqual(pitches, self._compile("guide")[0])


if __name__ == "__main__":
    unittest.main()
