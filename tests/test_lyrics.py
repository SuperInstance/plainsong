"""Syllables bound to notes rather than to a time of their own.

Phase 2 of `proposals/02-the-voyage.md`. The change is gated: `core.lyrics`
defaults to `independent`, which is exactly what every existing file already
does, because binding moves lyric events and those reach the MIDI file as
meta events.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from plainsong import pipeline
from plainsong.notation.lyrics import is_padding
from plainsong.runtime.config import load_config

ALIGNED = (
    "**TRACK: A**\n[MetaData]\nkey: Am | tempo: 96 | time: 4/4\n\n"
    "[V1] (Verse - 1 Bars)\n"
    "Melody: | A4  .   C5  E5 |\n"
    "Lyrics: | the tide came  |\n"
)


def compile_with(text: str, mode: str):
    config = load_config()
    config.data.setdefault("core", {})["lyrics"] = mode
    result = pipeline.compile_text(text, config=config)
    return result.arrangement.lyrics, result.diagnostics


class TestTheWordLandsOnItsNote(unittest.TestCase):
    def test_independent_is_the_old_behaviour(self):
        """`came` is written under `C5` and sounds two thirds of a beat late."""
        events, _ = compile_with(ALIGNED, "independent")
        self.assertEqual(
            [(e.text, round(e.start, 3)) for e in events],
            [("the", 0.0), ("tide", 1.333), ("came", 2.667)],
        )

    def test_bound_puts_every_syllable_on_a_note(self):
        events, _ = compile_with(ALIGNED, "bound")
        self.assertEqual(
            [(e.text, round(e.start, 3)) for e in events],
            [("the", 0.0), ("tide", 2.0), ("came", 3.0)],
        )

    def test_a_word_carries_until_the_next_word(self):
        """Fewer words than notes is a melisma, and needs no mark: `the` is
        sung over A4 while it is held, and ends when `tide` arrives."""
        events, _ = compile_with(ALIGNED, "bound")
        self.assertEqual([round(e.duration, 3) for e in events], [2.0, 1.0, 1.0])

    def test_the_default_is_independent(self):
        default = pipeline.compile_text(ALIGNED).arrangement.lyrics
        independent, _ = compile_with(ALIGNED, "independent")
        self.assertEqual(
            [(e.text, e.start) for e in default],
            [(e.text, e.start) for e in independent],
        )


class TestPaddingIsNotMelisma(unittest.TestCase):
    """The plan proposed reading a sustain token in a lyric row as a melisma,
    by analogy with ABC's `_`. Real notation uses it to hold the column under a
    melody that sustains, and reading it as a melisma pushes words off the bar.
    """

    KITCHEN = Path(__file__).resolve().parent.parent / "examples" / "edge-cases" / "edge-5-kitchen-sink.song"

    def test_dots_in_a_lyric_row_bind_to_nothing(self):
        text = self.KITCHEN.read_text(encoding="utf-8")
        events, _ = compile_with(text, "bound")
        words = [e.text for e in events][:4]
        # `| sing . every . |` over `| Bb3 . F4 . |` is two words on two notes.
        self.assertEqual(words, ["sing", "every", "token", "once"])

    def test_the_words_land_on_the_notes_they_are_written_under(self):
        text = self.KITCHEN.read_text(encoding="utf-8")
        events, _ = compile_with(text, "bound")
        self.assertEqual([round(e.start, 2) for e in events][:4], [0.0, 2.0, 4.0, 6.0])

    def test_is_padding_covers_both_token_classes(self):
        for token in (".", "-", "..", "~", "hold", "_", "x", "rest", "(hold)", "(rest)"):
            with self.subTest(token=token):
                self.assertTrue(is_padding(token))
        for token in ("the", "sing", "a", "Am", "1"):
            with self.subTest(token=token):
                self.assertFalse(is_padding(token))


class TestTheBarlineResyncs(unittest.TestCase):
    def test_too_many_syllables_costs_one_bar_and_recovers(self):
        text = (
            "**TRACK: Over**\n[MetaData]\nkey: C | tempo: 100 | time: 4/4\n\n"
            "[V1] (Verse - 2 Bars)\n"
            "Melody: | C4 . D4 . | E4 . F4 . |\n"
            "Lyrics: | one two three four five | six seven |\n"
        )
        events, diagnostics = compile_with(text, "bound")
        messages = [d.message for d in diagnostics]
        self.assertTrue(any("syllable" in m and "not sung" in m for m in messages), messages)
        # Bar 1 overflowed and was truncated; bar 2 is unaffected by it.
        self.assertEqual([e.text for e in events], ["one", "two", "six", "seven"])
        self.assertEqual([round(e.start, 2) for e in events], [0.0, 2.0, 4.0, 6.0])

    def test_fewer_syllables_leaves_the_remaining_notes_wordless(self):
        text = (
            "**TRACK: Under**\n[MetaData]\nkey: C | tempo: 100 | time: 4/4\n\n"
            "[V1] (Verse - 1 Bars)\n"
            "Melody: | C4 D4 E4 F4 |\n"
            "Lyrics: | one |\n"
        )
        events, diagnostics = compile_with(text, "bound")
        self.assertEqual([e.text for e in events], ["one"])
        self.assertEqual(diagnostics, [])
        # One word over four notes lasts across all of them.
        self.assertEqual(round(events[0].duration, 2), 4.0)


class TestNothingToBindTo(unittest.TestCase):
    def test_lyrics_without_a_melody_are_kept_and_reported(self):
        """Dropping the words silently would be the worst answer available."""
        text = (
            "**TRACK: NoTune**\n[MetaData]\nkey: C | tempo: 100 | time: 4/4\n\n"
            "[V1] (Verse - 1 Bars)\n"
            "Chords: | C . . . |\n"
            "Lyrics: | just some words |\n"
        )
        events, diagnostics = compile_with(text, "bound")
        self.assertEqual([e.text for e in events], ["just", "some", "words"])
        self.assertTrue(
            any("no melody to bind to" in d.message for d in diagnostics),
            [d.message for d in diagnostics],
        )

    def test_they_sit_exactly_where_independent_would_have_put_them(self):
        text = (
            "**TRACK: NoTune**\n[MetaData]\nkey: C | tempo: 100 | time: 4/4\n\n"
            "[V1] (Verse - 1 Bars)\n"
            "Chords: | C . . . |\n"
            "Lyrics: | just some words |\n"
        )
        bound, _ = compile_with(text, "bound")
        loose, _ = compile_with(text, "independent")
        self.assertEqual(
            [(e.text, round(e.start, 4)) for e in bound],
            [(e.text, round(e.start, 4)) for e in loose],
        )


class TestTheSettingBehaves(unittest.TestCase):
    def test_an_unknown_mode_says_so(self):
        _, diagnostics = compile_with(ALIGNED, "boundd")
        self.assertTrue(
            any("unknown lyrics mode" in d.message for d in diagnostics),
            [d.message for d in diagnostics],
        )

    def test_an_unknown_mode_still_compiles_as_the_default(self):
        odd, _ = compile_with(ALIGNED, "boundd")
        loose, _ = compile_with(ALIGNED, "independent")
        self.assertEqual([(e.text, e.start) for e in odd], [(e.text, e.start) for e in loose])

    def test_binding_moves_no_note(self):
        """It is a change to lyrics, and only to lyrics."""
        text = Path(__file__).resolve().parent.parent / "examples" / "edge-cases" / "edge-5-kitchen-sink.song"
        source = text.read_text(encoding="utf-8")

        def pitches(mode):
            config = load_config()
            config.data.setdefault("core", {})["lyrics"] = mode
            arrangement = pipeline.compile_text(source, config=config).arrangement
            return sorted(
                (n.pitch, round(n.start, 6), round(n.duration, 6))
                for t in arrangement.tracks
                for n in t.notes
            )

        self.assertEqual(pitches("bound"), pitches("independent"))


if __name__ == "__main__":
    unittest.main()
