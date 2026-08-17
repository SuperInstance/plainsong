"""The common time matrix.

Phase 1 of `proposals/02-the-voyage.md`. The grid must record what the arranger
already computed and must not influence it: the exit criterion for this phase is
that a lyric gains a position while every one of the 6,321 fingerprinted files
still compiles to exactly the music it did.
"""

from __future__ import annotations

import unittest

from plainsong import pipeline
from plainsong.notation.timegrid import Placement, TimeGrid

ALIGNED = (
    "**TRACK: Align**\n"
    "[MetaData]\nkey: Am | tempo: 96 | time: 4/4\n\n"
    "[V1] (Verse - 1 Bars)\n"
    "Chords: | Am  .   .   .  |\n"
    "Melody: | A4  .   C5  E5 |\n"
    "Lyrics: | the tide came  |\n"
)


def grid_of(text: str) -> TimeGrid:
    return pipeline.compile_text(text).arrangement.grid


class TestEveryTokenGetsAPosition(unittest.TestCase):
    def test_a_lyric_has_a_position(self):
        """The exit criterion for Phase 1, stated as a test."""
        lyrics = [p for p in grid_of(ALIGNED).placements if p.row == "lyrics"]
        self.assertEqual([p.token for p in lyrics], ["the", "tide", "came"])
        self.assertEqual([round(p.unit, 3) for p in lyrics], [0.0, 0.333, 0.667])

    def test_tokens_that_make_no_sound_still_occupy_their_column(self):
        # A rest and a sustain produce no note, so nothing downstream would
        # record them -- but a renderer still has to leave room, and a merge
        # still has to see them as occupied.
        kinds = {p.kind for p in grid_of(ALIGNED).placements}
        self.assertIn("sustain", kinds)
        self.assertIn("text", kinds)

    def test_a_lyric_and_a_note_are_positioned_by_the_same_arithmetic(self):
        """The property the whole design rests on. `came` is written directly
        beneath `C5` and is not in the same column, and the grid says so."""
        grid = grid_of(ALIGNED)
        c5 = next(p for p in grid.placements if p.token == "C5")
        came = next(p for p in grid.placements if p.token == "came")
        self.assertEqual(c5.unit, 0.5)
        self.assertAlmostEqual(came.unit, 2 / 3)
        # The column at C5 contains the chord row and the melody row, and does
        # not contain the lyric that appears to be sitting in it.
        column = [p.row for p in grid.column(c5.bar, c5.unit)]
        self.assertIn("melody", column)
        self.assertNotIn("lyrics", column)

    def test_disagreements_names_the_bar_and_the_counts(self):
        self.assertEqual(
            grid_of(ALIGNED).disagreements(),
            [(0, {"chords": 4, "melody": 4, "lyrics": 3})],
        )

    def test_rows_that_agree_do_not_disagree(self):
        even = ALIGNED.replace("Lyrics: | the tide came  |", "Lyrics: | the tide came now |")
        self.assertEqual(grid_of(even).disagreements(), [])


class TestTheRowAxisIsDisjoint(unittest.TestCase):
    """Merging is set intersection on (row, bar, unit), which is only a proof
    of non-collision if two different rows never share a row key."""

    def test_each_row_kind_is_its_own_axis(self):
        grid = grid_of(ALIGNED)
        self.assertEqual(set(grid.rows()), {"chords", "melody", "lyrics"})

    def test_players_are_separated_by_name(self):
        text = (
            "**TRACK: Two**\n[MetaData]\nkey: C | tempo: 100 | time: 4/4\n\n"
            "[V1] (Verse - 1 Bars)\n"
            "@bass  | c2 . g1 . |\n"
            "@keys  | e3 . g3 . |\n"
        )
        rows = set(grid_of(text).rows())
        self.assertEqual(rows, {"player:bass", "player:keys"})


class TestBarsAreCountedNotAccumulated(unittest.TestCase):
    def test_a_later_bar_lands_on_the_bar_it_is_written_in(self):
        text = (
            "**TRACK: Bars**\n[MetaData]\nkey: C | tempo: 120 | time: 4/4\n\n"
            "[V1] (Verse - 4 Bars)\n"
            "Melody: | C4 . . . | D4 . . . | E4 . . . | F4 . . . |\n"
        )
        grid = grid_of(text)
        heads = [p for p in grid.placements if p.unit == 0.0]
        self.assertEqual([p.token for p in heads], ["C4", "D4", "E4", "F4"])
        self.assertEqual([p.bar for p in heads], [0, 1, 2, 3])

    def test_a_bar_boundary_that_arrives_slightly_short_is_not_the_bar_before(self):
        # Onsets are produced by division, so a downbeat can arrive as
        # 11.999999999999998. Flooring that lands it a whole bar early.
        grid = TimeGrid(bar_beats=4.0)
        placement = grid.add(
            token="x", row="melody", kind="note", onset=11.999999999999998, width=1.0
        )
        self.assertEqual(placement.bar, 3)
        self.assertEqual(placement.unit, 0.0)

    def test_a_triplet_keeps_its_thirds(self):
        grid = TimeGrid(bar_beats=4.0)
        units = [
            grid.add(token=str(i), row="melody", kind="note", onset=i * 4 / 3, width=4 / 3).unit
            for i in range(3)
        ]
        self.assertEqual([round(u, 6) for u in units], [0.0, 0.333333, 0.666667])


class TestTheGridDoesNotChangeTheMusic(unittest.TestCase):
    def test_building_it_moves_no_note(self):
        """Phase 1 changes no behaviour. The corpus fingerprint is the real
        guard; this is the fast version of it."""
        result = pipeline.compile_text(ALIGNED)
        pitches = [
            (n.pitch, round(n.start, 6), round(n.duration, 6))
            for t in result.arrangement.tracks
            for n in t.notes
        ]
        self.assertEqual(
            pitches,
            [
                (57, 0.0, 4.0), (60, 0.0, 4.0), (64, 0.0, 4.0),   # Am, held
                (69, 0.0, 2.0), (72, 2.0, 1.0), (76, 3.0, 1.0),   # A4 . C5 E5
            ],
        )

    def test_it_emits_no_diagnostic(self):
        # Reporting a disagreement is Phase 2's job and is a notation change.
        self.assertEqual(pipeline.compile_text(ALIGNED).diagnostics, [])


class TestPlacement(unittest.TestCase):
    def test_sounds_distinguishes_a_note_from_a_column_holder(self):
        self.assertTrue(
            Placement("C4", "melody", "note", 0, 0.0, 1.0, 0.0).sounds
        )
        self.assertFalse(
            Placement("the", "lyrics", "text", 0, 0.0, 1.0, 0.0).sounds
        )


if __name__ == "__main__":
    unittest.main()
