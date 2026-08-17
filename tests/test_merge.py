"""Merging two edits to one score.

Phase 4 of `proposals/02-the-voyage.md`. The claim being tested is that a
conflict is *decidable* rather than guessed: an edit occupies a set of
`(row, bar)` cells and two edits collide exactly when those sets intersect.
"""

from __future__ import annotations

import unittest

from plainsong.notation.merge import Cell, cells_of, merge, touched
from plainsong.notation.parser import parse

BASE = (
    "**TRACK: Session**\n[MetaData]\nkey: Am | tempo: 96 | time: 4/4\n\n"
    "[V1] (Verse - 2 Bars)\n"
    "Chords: | Am . . . | F . . . |\n"
    "Melody: | A4 . C5 E5 | F4 . A4 C5 |\n"
    "@bass   | a1 . e2 . | f1 . c2 . |\n"
)


def swap(text: str, old: str, new: str) -> str:
    assert old in text, f"fixture drifted: {old!r} not present"
    return text.replace(old, new)


class TestDisjointEditsMerge(unittest.TestCase):
    def test_two_agents_on_different_rows_do_not_conflict(self):
        """The exit criterion: `@bass` and `Melody:` rewritten concurrently."""
        mine = swap(BASE, "@bass   | a1 . e2 . | f1 . c2 . |", "@bass   | a1 a1 e2 e2 | f1 f1 c2 c2 |")
        theirs = swap(BASE, "Melody: | A4 . C5 E5 |", "Melody: | A4 B4 C5 E5 |")
        result = merge(BASE, mine, theirs)
        self.assertTrue(result.ok, result.explain())
        self.assertEqual(result.conflicts, [])
        # Both changes survive.
        self.assertEqual(result.cells[Cell(0, "player:bass", 0)], ["a1", "a1", "e2", "e2"])
        self.assertEqual(result.cells[Cell(0, "melody", 0)], ["A4", "B4", "C5", "E5"])

    def test_the_same_row_in_different_bars_does_not_conflict(self):
        """What the row axis alone cannot express, and the matrix can. A
        file-per-voice model has to serialise these; they are disjoint."""
        mine = swap(BASE, "| A4 . C5 E5 |", "| A4 B4 C5 E5 |")
        theirs = swap(BASE, "| F4 . A4 C5 |", "| F4 G4 A4 C5 |")
        result = merge(BASE, mine, theirs)
        self.assertTrue(result.ok, result.explain())
        self.assertEqual(result.cells[Cell(0, "melody", 0)], ["A4", "B4", "C5", "E5"])
        self.assertEqual(result.cells[Cell(0, "melody", 1)], ["F4", "G4", "A4", "C5"])

    def test_an_untouched_side_does_not_revert_the_other(self):
        """Three-way, and this is why. One agent changes the melody; the other
        submits the whole file having changed only the bass. Two-way diffing
        would see the second agent's stale melody and undo the first."""
        mine = swap(BASE, "| A4 . C5 E5 |", "| A4 B4 C5 E5 |")
        theirs = swap(BASE, "@bass   | a1 . e2 . |", "@bass   | a1 a1 e2 . |")
        result = merge(BASE, mine, theirs)
        self.assertTrue(result.ok, result.explain())
        self.assertEqual(result.cells[Cell(0, "melody", 0)], ["A4", "B4", "C5", "E5"])
        self.assertEqual(result.cells[Cell(0, "player:bass", 0)], ["a1", "a1", "e2", "."])

    def test_players_are_disjoint_by_name(self):
        base = (
            "**TRACK: Band**\n[MetaData]\nkey: C | tempo: 100 | time: 4/4\n\n"
            "[V1] (Verse - 1 Bars)\n"
            "@bass | c2 . g1 . |\n"
            "@keys | e3 . g3 . |\n"
        )
        mine = swap(base, "@bass | c2 . g1 . |", "@bass | c2 c2 g1 g1 |")
        theirs = swap(base, "@keys | e3 . g3 . |", "@keys | e3 e3 g3 g3 |")
        self.assertTrue(merge(base, mine, theirs).ok)


class TestOverlapIsRefused(unittest.TestCase):
    def test_the_same_bar_written_two_ways_conflicts(self):
        mine = swap(BASE, "| A4 . C5 E5 |", "| A4 B4 C5 E5 |")
        theirs = swap(BASE, "| A4 . C5 E5 |", "| A4 G4 C5 E5 |")
        result = merge(BASE, mine, theirs)
        self.assertFalse(result.ok)
        self.assertEqual(result.conflicts, [Cell(0, "melody", 0)])

    def test_the_conflict_names_a_coordinate_a_person_can_find(self):
        mine = swap(BASE, "| A4 . C5 E5 |", "| A4 B4 C5 E5 |")
        theirs = swap(BASE, "| A4 . C5 E5 |", "| A4 G4 C5 E5 |")
        self.assertEqual(str(merge(BASE, mine, theirs).conflicts[0]), "section 1, melody, bar 1")

    def test_writing_the_same_thing_is_agreement_not_collision(self):
        same = swap(BASE, "| A4 . C5 E5 |", "| A4 B4 C5 E5 |")
        result = merge(BASE, same, same)
        self.assertTrue(result.ok, result.explain())
        self.assertEqual(result.cells[Cell(0, "melody", 0)], ["A4", "B4", "C5", "E5"])


class TestRemovalIsAChange(unittest.TestCase):
    def test_deleting_a_row_is_touched(self):
        """Otherwise a deletion looks like no change, and the other side's edit
        to the deleted row is resurrected by a merge that thought nobody
        objected."""
        gone = swap(BASE, "@bass   | a1 . e2 . | f1 . c2 . |\n", "")
        edit = touched(cells_of(parse(BASE)), cells_of(parse(gone)))
        self.assertEqual(
            sorted(edit.cells),
            [Cell(0, "player:bass", 0), Cell(0, "player:bass", 1)],
        )

    def test_a_deletion_conflicts_with_an_edit_to_the_same_bar(self):
        gone = swap(BASE, "@bass   | a1 . e2 . | f1 . c2 . |\n", "")
        edited = swap(BASE, "@bass   | a1 . e2 . |", "@bass   | a1 a1 e2 e2 |")
        result = merge(BASE, gone, edited)
        self.assertFalse(result.ok)
        self.assertIn(Cell(0, "player:bass", 0), result.conflicts)


class TestBarsAreNumberedTheWayTheArrangerCountsThem(unittest.TestCase):
    def test_a_repeated_row_continues_rather_than_restarting(self):
        """Two `Melody:` rows in a section are eight bars, not four played
        twice. Numbering them per row would make two agents editing bar 1 of
        each look like one collision when they are two separate bars."""
        text = (
            "**TRACK: Runon**\n[MetaData]\nkey: C | tempo: 100 | time: 4/4\n\n"
            "[V1] (Verse - 4 Bars)\n"
            "Melody: | C4 . . . | D4 . . . |\n"
            "Melody: | E4 . . . | F4 . . . |\n"
        )
        cells = cells_of(parse(text))
        melody = sorted(c for c in cells if c.row == "melody")
        self.assertEqual([c.bar for c in melody], [0, 1, 2, 3])
        self.assertEqual(cells[Cell(0, "melody", 2)], ["E4", ".", ".", "."])

    def test_two_agents_editing_the_two_halves_do_not_conflict(self):
        text = (
            "**TRACK: Runon**\n[MetaData]\nkey: C | tempo: 100 | time: 4/4\n\n"
            "[V1] (Verse - 4 Bars)\n"
            "Melody: | C4 . . . | D4 . . . |\n"
            "Melody: | E4 . . . | F4 . . . |\n"
        )
        mine = swap(text, "| C4 . . . |", "| C4 D4 E4 F4 |")
        theirs = swap(text, "| F4 . . . |", "| F4 G4 A4 B4 |")
        self.assertTrue(merge(text, mine, theirs).ok)

    def test_sections_are_their_own_space(self):
        text = (
            "**TRACK: Two**\n[MetaData]\nkey: C | tempo: 100 | time: 4/4\n\n"
            "[V1] (Verse - 1 Bars)\nMelody: | C4 . . . |\n\n"
            "[C] (Chorus - 1 Bars)\nMelody: | G4 . . . |\n"
        )
        cells = cells_of(parse(text))
        self.assertIn(Cell(0, "melody", 0), cells)
        self.assertIn(Cell(1, "melody", 0), cells)
        mine = swap(text, "| C4 . . . |", "| C4 D4 . . |")
        theirs = swap(text, "| G4 . . . |", "| G4 A4 . . |")
        self.assertTrue(merge(text, mine, theirs).ok)


if __name__ == "__main__":
    unittest.main()
