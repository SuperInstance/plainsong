"""The chord grammar.

The engine this replaced enumerated about thirty spellings, so a symbol worked
if and only if somebody had typed it into a table. These tests are written
against the *rules* instead: each one names a rule and shows a chord that only
comes out right if the rule holds. A case that merely repeats a table entry
proves nothing, so there are none here.
"""

from __future__ import annotations

import unittest

from plainsong.notation import theory
from plainsong.notation.chordsymbol import ChordSymbolError, parse_symbol

NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")


def spell(symbol: str) -> str:
    """The chord's notes as names, low to high.

    Ordered by pitch rather than by degree number, because a suspended fourth
    is degree 11 sitting five semitones up and reading it last would make
    every expectation below harder to check by eye than it needs to be.
    """
    parsed = parse_symbol(symbol)
    return " ".join(
        NAMES[(parsed.root_pc + offset) % 12] for offset in sorted(set(parsed.degrees.values()))
    )


class TestTheRulesThatATableCannotHold(unittest.TestCase):
    """Each of these is a rule, not a lookup."""

    def test_an_alteration_displaces_its_natural_form(self):
        # The whole argument for a degree map. `b9` is not an extra note, it is
        # the ninth moved -- so there must be a Db and no D.
        self.assertEqual(spell("C7b9"), "C E G Bb Db")
        self.assertNotIn("D ", spell("C7b9") + " ")

    def test_a_thirteenth_does_not_imply_an_eleventh_over_a_major_third(self):
        # The most-cited rule in chord-scale teaching, and the one a naive
        # stacker always gets wrong: a natural 11 sits a semitone above the
        # major 3rd, so stacking past it must skip it.
        self.assertEqual(spell("C13"), "C E G Bb D A")
        self.assertEqual(spell("Cmaj13"), "C E G B D A")

    def test_but_a_minor_thirteenth_does_imply_its_eleventh(self):
        # Same stack, different third. With a minor third there is nothing for
        # the eleventh to fight, so it stays. If this passes while the previous
        # test also passes, the rule is about the third rather than about a
        # chord name -- which is the point.
        self.assertEqual(spell("Cm13"), "C Eb G Bb D F A")
        self.assertNotIn("F", spell("C13").split())

    def test_a_raised_eleventh_survives_the_same_stack(self):
        # It is a whole tone above the third rather than a semitone, so the
        # reason for the exception does not apply and the note comes back.
        self.assertEqual(spell("C13#11"), "C E G Bb D Gb A")

    def test_naming_the_eleventh_keeps_it_and_drops_the_third_instead(self):
        # `C11` asks for the eleventh on purpose. The two notes still cannot
        # both stay, so the resolution goes the other way.
        self.assertEqual(spell("C11"), "C G Bb D F")

    def test_suspending_the_third_removes_the_reason_to_avoid_the_eleventh(self):
        # `C9sus4` needs no special case: with no third, the fourth is just a
        # note. A table would need a separate entry; a rule does not.
        self.assertEqual(spell("C9sus4"), "C F G Bb D")

    def test_alt_removes_rather_than_adds(self):
        # `C7alt` is a dominant with its middle replaced, not one with things
        # piled on. The altered scale contains no natural fifth and no natural
        # ninth, so neither may appear.
        notes = spell("C7alt").split()
        self.assertIn("E", notes)
        self.assertIn("Bb", notes)
        self.assertNotIn("G", notes)  # no natural fifth
        self.assertNotIn("D", notes)  # no natural ninth
        self.assertEqual(spell("C7alt"), "C E Bb Db Gb Ab")

    def test_compound_alterations_need_no_enumeration(self):
        # None of these was ever written into a table anywhere. They work
        # because the modifiers are a list rather than part of a name.
        self.assertEqual(spell("C7b9#11"), "C E G Bb Db Gb")
        self.assertEqual(spell("Cmaj7#5"), "C E Ab B")
        self.assertEqual(spell("F13#11"), "F A C Eb G B D")


class TestSpellingsFromRealCharts(unittest.TestCase):
    """Every case here came out of the corpus, not out of a textbook."""

    def test_brazil_writes_a_major_seventh_as_7M(self):
        # 39 occurrences in this repository, the largest single group of
        # chords the old parser could not read. From *sétima maior*.
        self.assertEqual(spell("C7M"), spell("Cmaj7"))
        self.assertEqual(spell("F7M"), spell("Fmaj7"))
        self.assertEqual(spell("Cm7M"), spell("CmMaj7"))

    def test_a_seven_before_an_m_is_not_a_minor_seventh(self):
        # The rule above must not swallow the ordinary spelling. `Cm7` and
        # `C7M` differ only in the order of two characters and are different
        # chords; getting this backwards would have been silent.
        self.assertEqual(spell("Cm7"), "C Eb G Bb")
        self.assertEqual(spell("C7M"), "C E G B")

    def test_case_does_not_decide_a_word_but_does_decide_a_letter(self):
        # `Maj7` must work -- 22 occurrences failed on capitalisation alone --
        # while `M` and `m` must keep meaning opposite things.
        self.assertEqual(spell("EbMaj7"), spell("Ebmaj7"))
        self.assertEqual(spell("CM7"), "C E G B")
        self.assertEqual(spell("Cm7"), "C Eb G Bb")

    def test_a_minus_before_a_seven_is_minor_not_a_flattened_seventh(self):
        # `Bb-7` is B-flat minor seven in every chart ever printed. Reading the
        # minus as an accidental turns 22 minor chords in this repository into
        # dominants -- a chart that sounds wrong without looking wrong.
        self.assertEqual(spell("Bb-7"), spell("Bbm7"))
        self.assertEqual(spell("C-7"), "C Eb G Bb")

    def test_the_minus_is_a_quality_for_every_extension_not_just_the_seventh(self):
        # `C-9`, `C-11` and `C-13` are minor ninth, eleventh and thirteenth.
        # This is what makes the "a minus only reads as an accidental once a
        # quality has been named" guard load-bearing: without it the minus
        # would eat the digit here and flatten a degree instead.
        self.assertEqual(spell("C-9"), spell("Cm9"))
        self.assertEqual(spell("C-11"), spell("Cm11"))
        self.assertEqual(spell("C-13"), spell("Cm13"))
        self.assertEqual(spell("C-6"), spell("Cm6"))

    def test_but_a_minus_after_a_quality_is_an_accidental(self):
        # `Cm7-5` is the older spelling of `Cm7b5`, and it still has to work.
        self.assertEqual(spell("Cm7-5"), spell("Cm7b5"))
        self.assertEqual(spell("C-7b5"), spell("Cm7b5"))

    def test_the_two_triangles_are_different_codepoints(self):
        # U+0394 GREEK CAPITAL LETTER DELTA and U+2206 INCREMENT look
        # identical and both appear in real charts. Knowing only one of them
        # fails on half the input for a reason invisible on screen.
        self.assertEqual(spell("CΔ 7".replace(" ", "")), spell("Cmaj7"))
        self.assertEqual(spell("C∆7"), spell("Cmaj7"))

    def test_a_bare_triangle_means_the_seventh_chord(self):
        # `GbΔ` is a major seventh, not a triad -- unlike `GbM`, which is.
        # The distinction belongs to the spelling, not to the quality.
        self.assertEqual(spell("CΔ"), spell("Cmaj7"))
        self.assertEqual(spell("CM"), "C E G")

    def test_a_bare_slashed_circle_likewise(self):
        self.assertEqual(spell("Cø"), spell("Cm7b5"))

    def test_a_unicode_flat_works_in_an_alteration_not_just_a_root(self):
        self.assertEqual(spell("E7♭9"), spell("E7b9"))

    def test_brackets_carry_no_meaning(self):
        self.assertEqual(spell("G7(b13)"), spell("G7b13"))
        self.assertEqual(spell("C7(#9)"), spell("C7#9"))

    def test_a_slash_before_a_nine_is_not_a_bass_note(self):
        # `C6/9` is one quality. The test is whether what follows the slash
        # names a note, which is also how the transposer decides.
        self.assertEqual(spell("C6/9"), "C E G A D")
        self.assertEqual(spell("C69"), spell("C6/9"))
        self.assertEqual(parse_symbol("C6/9").bass_pc, None)
        self.assertEqual(parse_symbol("C/E").bass_pc, 4)


class TestNoChord(unittest.TestCase):
    """`N.C.` is a chord row saying there is no chord.

    Tested here rather than beside the other rest tokens because it is a thing
    a *chord row* says, and because it was found by the same warning pass that
    surfaced the unreadable spellings above -- it was being reported as a
    mistake by a file that had said exactly what it meant.
    """

    SPELLINGS = ("N.C.", "N.C", "NC", "n.c.")

    def _arrange(self, token: str):
        from plainsong.notation import arrange, parse

        return arrange(
            parse(
                "**TRACK: T**\n[MetaData]\nkey: C | tempo: 120 | time: 4/4\n\n"
                f"[V1] (Verse - 2 Bars)\nChords: | C . . . | {token} . . . |\n"
            )
        )

    def test_no_chord_is_silence_and_says_nothing_about_it(self):
        for token in self.SPELLINGS:
            with self.subTest(token=token):
                arrangement = self._arrange(token)
                self.assertEqual(arrangement.note_count, 3, "only the C triad should sound")
                self.assertEqual([d.message for d in arrangement.diagnostics], [])

    def test_it_is_a_rest_rather_than_a_sustain(self):
        # "No chord" means the harmony stops, not that it hangs on. Holding the
        # previous chord through an N.C. bar would be the opposite of what the
        # marking asks for, and would sound like nothing was wrong.
        held = self._arrange("N.C.")
        sounding = [n for _t, n in held.iter_notes() if n.start > 0]
        self.assertEqual(sounding, [], "nothing should sound in the second bar")


class TestRefusal(unittest.TestCase):
    def test_prose_is_not_a_chord(self):
        # An unreadable token used to become a rest, so a bar of prose in a
        # chord row compiled to silence and reported success.
        for word in ("bass", "guitar", "fade)", "bar,", "both", "Xm9"):
            with self.assertRaises(ChordSymbolError, msg=word):
                parse_symbol(word)

    def test_the_false_positive_surface_has_not_grown(self):
        # Single lowercase letters do parse as major triads. That is old
        # behaviour the corpus depends on -- it writes voicings in lowercase --
        # and this test pins it so a future change to the root scanner cannot
        # widen it without somebody noticing.
        accepted = [w for w in ("a", "b", "c", "d", "e", "f", "g", "am", "ebb") if _parses(w)]
        self.assertEqual(accepted, ["a", "b", "c", "d", "e", "f", "g", "am", "ebb"])
        for word in ("bad", "cab", "dab", "face", "fade", "deaf", "decaf", "beef"):
            self.assertFalse(_parses(word), word)


class TestTranspositionSurvivesTheNewVocabulary(unittest.TestCase):
    """The emitter has to spell back what the parser read.

    A chord suffix is defined relative to its root and says nothing about which
    root it sits on, so a transpose respells one letter and leaves the rest
    alone. That is what lets `C7b9#11` move at all -- no quality name could
    carry those alterations, so reconstructing the symbol from one would lose
    them silently, which is the failure this test exists to catch.
    """

    SYMBOLS = (
        "C7b9#11",
        "G7alt",
        "EbMaj7",
        "C7M",
        "C6/9",
        "Cm7b5",
        "F13#11",
        "Bmaj7#5",
        "C9sus4",
        "Cadd11",
        "Am",
        "D/F#",
        "Cm/Bb",
        "C∆7",
        "Bb-7",
        "Cø",
        "C7(b13)",
        "Cdim7",
        "C5",
        "C",
        "Csus4",
    )

    def test_one_step_keeps_the_pitch_classes(self):
        for symbol in self.SYMBOLS:
            with self.subTest(symbol=symbol):
                chord = theory.parse_chord(symbol)
                moved = theory.parse_chord(chord.transpose(2).name())
                self.assertEqual(
                    {(chord.root_pc + i + 2) % 12 for i in chord.intervals()},
                    {(moved.root_pc + i) % 12 for i in moved.intervals()},
                )

    def test_twelve_steps_come_home(self):
        # Round the circle and back. Any spelling that degrades a little on
        # each transpose shows up here even when one step looks clean.
        for symbol in self.SYMBOLS:
            with self.subTest(symbol=symbol):
                start = theory.parse_chord(symbol)
                here = start
                for _ in range(12):
                    here = theory.parse_chord(here.transpose(1).name())
                self.assertEqual(
                    {(start.root_pc + i) % 12 for i in start.intervals()},
                    {(here.root_pc + i) % 12 for i in here.intervals()},
                )


class TestNothingThatCompiledBeforeCompilesDifferently(unittest.TestCase):
    """The compatibility claim, pinned.

    Accepting more spellings is only safe if it changes none of the ones
    already understood. This was checked across all 181,419 chord occurrences
    in the repository when the grammar landed; the sample below is what keeps
    it true afterwards.
    """

    KNOWN = {
        "C": (0, 4, 7),
        "Cm": (0, 3, 7),
        "C7": (0, 4, 7, 10),
        "Cmaj7": (0, 4, 7, 11),
        "Cm7": (0, 3, 7, 10),
        "Cdim": (0, 3, 6),
        "Cdim7": (0, 3, 6, 9),
        "Caug": (0, 4, 8),
        "Csus2": (0, 2, 7),
        "Csus4": (0, 5, 7),
        "C6": (0, 4, 7, 9),
        "Cm6": (0, 3, 7, 9),
        "C9": (0, 4, 7, 10, 14),
        "Cmaj9": (0, 4, 7, 11, 14),
        "Cm9": (0, 3, 7, 10, 14),
        "C7sus4": (0, 5, 7, 10),
        "Cm7b5": (0, 3, 6, 10),
        "Cadd9": (0, 4, 7, 14),
        "C7b9": (0, 4, 7, 10, 13),
        "C7#9": (0, 4, 7, 10, 15),
        "C7b5": (0, 4, 6, 10),
        "C7#5": (0, 4, 8, 10),
        "CmMaj7": (0, 3, 7, 11),
        "C5": (0, 7),
    }

    def test_the_common_vocabulary_is_unchanged(self):
        for symbol, intervals in self.KNOWN.items():
            with self.subTest(symbol=symbol):
                self.assertEqual(theory.parse_chord(symbol).intervals(), intervals)


class TestTheDocumentationIsTrue(unittest.TestCase):
    """`docs/chords.md` prints a table of accepted spellings.

    A table of spellings in prose is a promise, and prose does not fail to
    compile. The academy taught a language that did not exist for months for
    exactly this reason, so the promise is checked here instead of trusted.
    """

    def test_every_spelling_the_documentation_claims_actually_parses(self):
        import pathlib
        import re

        doc = pathlib.Path(__file__).resolve().parent.parent / "docs" / "chords.md"
        text = doc.read_text(encoding="utf-8")
        table = text.split("## What it accepts")[1].split("Accidentals may be")[0]
        symbols = re.findall(r"`([A-G][^`\s]*)`", table)
        self.assertGreater(len(symbols), 60, "the table lost most of its rows")
        for symbol in symbols:
            with self.subTest(symbol=symbol):
                parse_symbol(symbol)


def _parses(token: str) -> bool:
    try:
        parse_symbol(token)
        return True
    except ChordSymbolError:
        return False


if __name__ == "__main__":
    unittest.main()
