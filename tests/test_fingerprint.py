"""The corpus fingerprint.

The full 6,321-file comparison runs in CI rather than here, because it takes
about seven seconds and the suite is meant to stay fast. What is tested here is
the mechanism: that the fingerprint is stable when nothing changed, and that it
moves when something audible did. A safety net nobody has watched fail is not
evidence, and this one is guarding a claim -- "no existing file changed" -- that
was previously established by a script somebody ran once by hand.
"""

from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tapscript.fingerprint import fingerprint_file, fingerprint_paths, format_report

SONG = textwrap.dedent(
    """\
    **TRACK: Fingerprint Test**
    [MetaData]
    key: C | tempo: 120 | time: 4/4

    [V1] (Verse - 4 Bars)
    Chords: | Cmaj7 . . . | Am7 . . . | Dm7 . . . | G7 . . . |
    Melody: | C4 . E4 G4 | A4 . C5 E5 | D4 . F4 A4 | G4 . B4 D5 |
    """
)


class TestStability(unittest.TestCase):
    def setUp(self):
        self._dir = TemporaryDirectory()
        self.root = Path(self._dir.name)
        (self.root / "song.tap").write_text(SONG, encoding="utf-8")

    def tearDown(self):
        self._dir.cleanup()

    def test_the_same_file_fingerprints_the_same_way_twice(self):
        first = fingerprint_file(self.root / "song.tap")
        second = fingerprint_file(self.root / "song.tap")
        self.assertEqual(first.digest, second.digest)
        self.assertGreater(first.notes, 0)

    def test_a_changed_note_changes_the_digest(self):
        before = fingerprint_file(self.root / "song.tap").digest
        (self.root / "song.tap").write_text(SONG.replace("Am7 . . .", "Ab7 . . ."), encoding="utf-8")
        after = fingerprint_file(self.root / "song.tap")
        self.assertNotEqual(before, after.digest)

    def test_the_four_note_cap_is_currently_audible_and_wrong(self):
        # Not a feature. `arrange.Options.max_chord_notes` is 4 and the notes
        # are taken from the bottom, so `G7b9` renders exactly as `G7`: the cap
        # keeps root-third-fifth-seventh and discards the one note the symbol
        # was written to specify. Every ninth chord in the corpus loses its
        # ninth this way -- 459 occurrences, and `E7#9` comes out as `E7`.
        #
        # It is pinned rather than fixed because fixing it changes how existing
        # files sound, which is a different kind of change from teaching the
        # parser new spellings and wants its own diff. When somebody does fix
        # it this test will fail, which is the intent: it should be updated
        # deliberately, not discovered.
        before = fingerprint_file(self.root / "song.tap").digest
        (self.root / "song.tap").write_text(SONG.replace("G7 . . .", "G7b9 . . ."), encoding="utf-8")
        self.assertEqual(
            before,
            fingerprint_file(self.root / "song.tap").digest,
            "the four-note cap no longer hides an added ninth -- if that was "
            "intended, re-record the corpus fingerprint and update this test",
        )

    def test_a_changed_pitch_moves_the_digest_without_moving_the_note_count(self):
        # The case the note count cannot see, and the reason a hash is needed.
        # Flattening a seventh across the bundled songbook leaves every count
        # untouched; `tapscript check` and the library.compat spec both pass.
        before = fingerprint_file(self.root / "song.tap")
        (self.root / "song.tap").write_text(SONG.replace("Cmaj7", "C7"), encoding="utf-8")
        after = fingerprint_file(self.root / "song.tap")
        self.assertEqual(before.notes, after.notes)
        self.assertNotEqual(before.digest, after.digest)

    def test_a_comment_does_not_change_the_digest(self):
        # The fingerprint is of the music, not of the source. Reformatting,
        # retitling and commenting must all be free, or the guard cries wolf
        # and somebody re-records it without reading the diff.
        before = fingerprint_file(self.root / "song.tap").digest
        (self.root / "song.tap").write_text(SONG + "\n# a trailing comment\n", encoding="utf-8")
        self.assertEqual(before, fingerprint_file(self.root / "song.tap").digest)


class TestReport(unittest.TestCase):
    def setUp(self):
        self._dir = TemporaryDirectory()
        self.root = Path(self._dir.name)
        for name in ("b.tap", "a.tap", "c.tap"):
            (self.root / name).write_text(SONG, encoding="utf-8")

    def tearDown(self):
        self._dir.cleanup()

    def test_files_come_out_in_a_stable_order(self):
        # Sorted by posix path so Windows and Linux produce the same file. The
        # separator is part of the string, so unsorted output would make the
        # recorded baseline platform-specific and the CI job useless.
        names = [line.split()[-1] for line in format_report(fingerprint_paths([str(self.root)])).splitlines()[:-1]]
        self.assertEqual(names, sorted(names))

    def test_the_total_line_is_last(self):
        # So that a change to the total does not shift every line above it and
        # turn a one-file diff into a whole-file diff.
        lines = format_report(fingerprint_paths([str(self.root)])).splitlines()
        self.assertTrue(lines[-1].startswith("#"))
        self.assertFalse(any(line.startswith("#") for line in lines[:-1]))

    def test_a_file_that_stops_compiling_is_recorded_rather_than_raised(self):
        # A crash is a fingerprint result. Raising here would mean the one
        # change most worth catching takes the whole report down with it.
        (self.root / "broken.tap").write_text("\x00 not notation at all", encoding="utf-8")
        entries = {Path(e.path).name: e for e in fingerprint_paths([str(self.root)])}
        self.assertIn("broken.tap", entries)


class TestTheRecordedBaselineIsCurrent(unittest.TestCase):
    def test_the_baseline_exists_and_covers_the_corpus(self):
        # Cheap sanity only -- the real comparison is the CI job. This catches
        # the baseline being deleted, truncated, or committed empty, any of
        # which would make that job pass while checking nothing.
        baseline = Path(__file__).resolve().parent / "corpus-fingerprint.txt"
        self.assertTrue(baseline.is_file(), "the recorded corpus fingerprint is missing")
        lines = baseline.read_text(encoding="utf-8").splitlines()
        self.assertGreater(len(lines), 6000, "the baseline covers far fewer files than the corpus has")
        self.assertTrue(lines[-1].startswith("#"))
        self.assertIn("0 failed", lines[-1])


if __name__ == "__main__":
    unittest.main()
