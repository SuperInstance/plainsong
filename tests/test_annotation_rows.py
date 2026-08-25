"""Generic annotation rows: any dimension a composer can name.

The Vel: row marked the playable row above it, positionally, and compiled to
velocities. These tests hold the generalisation to the same bar:

* any ``Name:`` row of bar-aligned cells is a first-class layer -- parsed,
  preserved, addressable, round-tripped -- whatever the name happens to be;
* the linking rule is shared, not duplicated: a ``Breath:`` value and a
  ``Vel:`` mark over the same column land on the same event, because both
  walk ``annotations.pair_annotation_rows`` and ``annotations.walk_bars``;
* each resolved value carries its address (voice, bar, beat window, target),
  read off the same time-grid arithmetic that timed the notes;
* unknown rows never warn and never change a byte of the compile;
* files without layers construct nothing phantom;
* ``plainsong.features`` can compute mean/std over any *numeric* layer.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from plainsong.features import annotation_stats, annotation_values
from plainsong.notation import arrange, parse
from plainsong.notation.annotations import ANNOTATION_SEMANTICS
from plainsong.notation.arrange import ArrangeOptions
from plainsong.notation.ir import ROLE_ANNOTATION, ROLE_VELOCITY
from plainsong.render.midi import midi_bytes
from plainsong.transform import describe, to_text, transpose

GOLDEN = Path(__file__).parent / "golden"


def resolved(text: str, **options: object):
    """The arrangement of *text* with humanising off, so numbers are exact."""
    return arrange(parse(text), ArrangeOptions(humanize=False, **options))


class TestGenericRowParsing(unittest.TestCase):
    def test_any_labelled_bar_row_is_a_layer_of_its_own_kind(self):
        score = parse("[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | deep . shallow . |\n")
        self.assertEqual(len(score.sections), 1)
        roles = [line.role for line in score.sections[0].lines]
        self.assertEqual(roles, ["melody", ROLE_ANNOTATION])
        layer = score.sections[0].lines[1]
        self.assertEqual(layer.name, "Breath")  # as written, not lowercased
        self.assertEqual(layer.cells[0].tokens, ["deep", ".", "shallow", "."])

    def test_unknown_rows_never_warn_and_never_fail(self):
        text = (
            "[V1]\n"
            "Melody: | C4 D4 E4 F4 |\n"
            "Breath: | deep . light . |\n"
            "Mute: | palm . . open . |\n"
            "Gaze: | far . near . |\n"
            "Emotion: | joy . grief . |\n"
        )
        score = parse(text)
        self.assertEqual(score.warnings(), [])
        arrangement = arrange(score)
        self.assertEqual(
            [diag for diag in arrangement.diagnostics if diag.severity == "warning"],
            [],
        )

    def test_rows_a_composer_does_not_write_do_not_exist(self):
        score = parse("[V1]\nMelody: | C4 D4 E4 F4 |\n")
        self.assertEqual(score.annotation_rows(), [])
        self.assertEqual(arrange(score).annotations, [])

    def test_the_semantic_extension_table_is_consulted(self):
        # The velocity family is the built-in; those names are claimed as
        # roles before the generic path runs, so a generic layer with one of
        # those names never reaches the table through the parser. A name with
        # no entry is pure data.
        score = parse("[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | . . . . |\n")
        layer = score.annotation_rows()[0]
        self.assertEqual(layer.options.get("semantic"), "")
        # Registering a name is one line, and the parser records it.
        with mock.patch.dict(ANNOTATION_SEMANTICS, {"mute": "string-mute"}):
            score = parse("[V1]\nMelody: | C4 D4 E4 F4 |\nMute: | . on . |\n")
            self.assertEqual(score.annotation_rows()[0].options.get("semantic"), "string-mute")

    def test_an_orphaned_layer_is_preserved_without_a_word(self):
        score = parse("[V1]\nBreath: | deep . . . |\nMelody: | C4 D4 E4 F4 |\n")
        self.assertEqual(score.warnings(), [])
        self.assertEqual(len(score.annotation_rows()), 1)
        self.assertEqual(arrange(score).annotations, [])  # nothing above it to mark

    def test_names_the_compiler_plays_are_still_roles(self):
        # "Dynamics" is a Vel: alias; it must not become a data layer.
        score = parse("[V1]\nMelody: | C4 D4 E4 F4 |\nDynamics: | p . . f |\n")
        self.assertEqual(score.sections[0].lines[1].role, ROLE_VELOCITY)
        self.assertEqual(score.annotation_rows(), [])


class TestLinkingAndTimestamps(unittest.TestCase):
    def test_values_resolve_to_the_events_they_are_written_under(self):
        text = "[V1]\nMelody: | C4 . E4 G4 | A4 G4 E4 C4 |\nBreath: | 1.0 . 0.6 0.9 | . 0.2 . . |\n"
        arrangement = resolved(text)
        addresses = [(a.token, a.onset, a.width, a.target) for a in arrangement.annotations]
        self.assertEqual(
            addresses,
            [
                ("1.0", 0.0, 1.0, "C4"),
                ("0.6", 2.0, 1.0, "E4"),
                ("0.9", 3.0, 1.0, "G4"),
                ("0.2", 5.0, 1.0, "G4"),
            ],
        )

    def test_addresses_carry_voice_bar_and_unit(self):
        # `mu` and `nu`, not `x` and `y`: the rest spellings are spacers in a
        # layer too, the shared vocabulary holding its column.
        text = "[V1]\nMelody: | C4 D4 E4 F4 | G4 A4 B4 C5 |\nBreath: | . mu . . | . nu . . |\n"
        arrangement = resolved(text)
        by_token = {a.token: a for a in arrangement.annotations}
        self.assertEqual(
            (by_token["mu"].voice, by_token["mu"].bar, by_token["mu"].unit, by_token["mu"].role),
            ("melody", 0, 0.25, "melody"),
        )
        self.assertEqual(
            (by_token["nu"].voice, by_token["nu"].bar, by_token["nu"].unit),
            ("melody", 1, 0.25),
        )

    def test_the_address_joins_onto_the_time_grid(self):
        # A mark and the note it marks went through the same arithmetic: the
        # grid placement at (row, bar, onset) is the mark's target.
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | . deep . . |\n"
        arrangement = resolved(text)
        annotation = arrangement.annotations[0]
        placement = arrangement.grid.column(annotation.bar, annotation.unit)[0]
        self.assertEqual((placement.row, placement.token, placement.onset), ("melody", "D4", 1.0))
        self.assertEqual(annotation.onset, placement.onset)

    def test_a_player_row_is_marked_by_its_own_key(self):
        text = "[V1]\n@bass | c2 . g1 . | vel: 70\nGaze: | far . near . |\n"
        arrangement = resolved(text)
        self.assertEqual(
            [(a.token, a.voice, a.role, a.target) for a in arrangement.annotations],
            [("far", "player:bass", "player", "c2"), ("near", "player:bass", "player", "g1")],
        )

    def test_bars_are_absolute_across_sections(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | a . . . |\n[V2]\nMelody: | G4 A4 B4 C5 |\nBreath: | . b . . |\n"
        arrangement = resolved(text)
        by_token = {a.token: a for a in arrangement.annotations}
        self.assertEqual((by_token["a"].bar, by_token["a"].onset), (0, 0.0))
        self.assertEqual((by_token["b"].bar, by_token["b"].onset), (1, 5.0))

    def test_two_layers_mark_the_same_row(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | deep . . . |\nGaze: | far . . . |\n"
        arrangement = resolved(text)
        names = sorted({a.name for a in arrangement.annotations})
        self.assertEqual(names, ["Breath", "Gaze"])
        self.assertEqual([a.onset for a in arrangement.annotations], [0.0, 0.0])

    def test_a_layer_between_a_row_and_its_vel_row_steals_nothing(self):
        # Breath: sits between Melody: and Vel:. Vel: still marks the melody,
        # and the melody's velocities are untouched by the data layer.
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | . . deep . |\nVel: | 90 . 60 . |\n"
        arrangement = resolved(text)
        velocities = [note.velocity for _t, note in arrangement.iter_notes()]
        self.assertEqual(velocities, [90, 90, 60, 60])
        breath = [(a.token, a.onset) for a in arrangement.annotations if a.name == "Breath"]
        self.assertEqual(breath, [("deep", 2.0)])

    def test_vel_and_a_layer_over_the_same_column_agree(self):
        # The shared walk: both rows mark the third token, and the two
        # resolutions name the same event.
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | . . deep . |\nVel: | . . 60 . |\n"
        arrangement = resolved(text)
        annotation = arrangement.annotations[0]
        marked = [note for _t, note in arrangement.iter_notes() if note.start == annotation.onset]
        self.assertEqual([note.velocity for note in marked], [60])

    def test_spacers_hold_their_column_and_say_nothing(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | . . . . |\n"
        self.assertEqual(resolved(text).annotations, [])

    def test_a_value_over_a_rest_is_still_data(self):
        text = "[V1]\nMelody: | C4 r E4 r |\nBreath: | a . b . |\n"
        arrangement = resolved(text)
        kinds = {a.token: a.target_kind for a in arrangement.annotations}
        self.assertEqual(kinds, {"a": "note", "b": "note"})
        # The second value stands over a rest: preserved, marked as such.
        text = "[V1]\nMelody: | C4 r E4 r |\nBreath: | . mu . nu |\n"
        arrangement = resolved(text)
        self.assertEqual(
            {a.token: a.target_kind for a in arrangement.annotations},
            {"mu": "rest", "nu": "rest"},
        )

    def test_a_layer_shorter_than_its_row_marks_only_what_it_wrote(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | one . |\n"
        arrangement = resolved(text)
        self.assertEqual([(a.token, a.onset) for a in arrangement.annotations], [("one", 0.0)])

    def test_an_unbarred_target_is_marked_by_position(self):
        text = "[V1]\nMelody: C4 D4 E4\nBreath: | one . two |\n"
        arrangement = resolved(text)
        self.assertEqual(
            [(a.token, a.onset, a.target) for a in arrangement.annotations],
            [("one", 0.0, "C4"), ("two", 1.0, "E4")],
        )

    def test_an_explicit_target_names_its_row(self):
        text = "[V1]\nBreath: | deep . light . | on: @bass\nChords: | Am . F . |\n@bass | a1 . e2 . |\n"
        arrangement = resolved(text)
        self.assertEqual(
            [(a.token, a.voice, a.target) for a in arrangement.annotations],
            [("deep", "player:bass", "a1"), ("light", "player:bass", "e2")],
        )

    def test_an_unmatched_explicit_target_stays_data(self):
        score = parse("[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | q . . . | on: strings\n")
        self.assertEqual(score.warnings(), [])
        self.assertEqual(len(score.annotation_rows()), 1)
        self.assertEqual(arrange(score).annotations, [])


class TestRoundTrip(unittest.TestCase):
    def test_a_layer_round_trips_under_its_own_name(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | deep . light . |\n"
        again = parse(to_text(parse(text)))
        self.assertEqual(
            [line.role for line in again.sections[0].lines], ["melody", ROLE_ANNOTATION]
        )
        layer = again.sections[0].lines[1]
        self.assertEqual(layer.name, "Breath")
        self.assertEqual(layer.cells[0].tokens, ["deep", ".", "light", "."])

    def test_repeated_transposition_never_grows_a_layer(self):
        text = (
            "[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | deep . light . |\n"
            "@bass | c2 . g1 . | vel: 70\n"
        )
        current = text
        widths = []
        for _ in range(3):
            score = parse(current)
            melody, breath = score.sections[0].lines[0], score.sections[0].lines[1]
            widths.append((melody.bar_count, len(melody.cells[0].tokens), breath.bar_count, len(breath.cells[0].tokens)))
            current = transpose(to_text(score), 1)
        self.assertEqual(len(set(widths)), 1, f"rows drifted: {widths}")

    def test_transposition_moves_the_music_and_not_the_layer(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | deep . light . |\n"
        moved = parse(transpose(text, 2))
        melody, breath = moved.sections[0].lines
        self.assertEqual(melody.cells[0].tokens, ["D4", "E4", "F#4", "G4"])
        self.assertEqual(breath.cells[0].tokens, ["deep", ".", "light", "."])
        self.assertEqual(breath.bar_count, 1)

    def test_transposition_does_not_corrupt_alignment(self):
        # The layer still marks the tokens it was written under, by address,
        # after the notes beneath it have moved.
        text = "[V1]\n@bass | a1 . e2 . | vel: 70\nBreath: | deep . light . |\n"
        arrangement = resolved(transpose(text, 3))
        self.assertEqual(
            [(a.token, a.onset, a.target) for a in arrangement.annotations],
            [("deep", 0.0, "c2"), ("light", 2.0, "g2")],
        )

    def test_an_explicit_target_round_trips(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | deep . . . | on: melody\n"
        again = parse(to_text(parse(text)))
        layer = again.sections[0].lines[1]
        self.assertEqual(layer.options.get("on"), "melody")
        self.assertEqual(len(layer.cells), 1)  # the option was not read back as a bar


class TestNoCompileEffect(unittest.TestCase):
    def test_a_layer_changes_no_byte_of_the_compile(self):
        base = "[V1]\nMelody: | C4 D4 E4 F4 |\nChords: | Am . F . |\n"
        layered = "[V1]\nMelody: | C4 D4 E4 F4 |\nEmotion: | joy . grief . |\nChords: | Am . F . |\n"
        self.assertEqual(midi_bytes(resolved(base)), midi_bytes(resolved(layered)))

    def test_a_file_without_layers_still_compiles_byte_identically(self):
        song = (GOLDEN / "compat.song").read_text()
        self.assertEqual(
            midi_bytes(arrange(parse(song))), (GOLDEN / "compat.song.golden").read_bytes()
        )


class TestFeaturesOverAnnotations(unittest.TestCase):
    LAYERED = (
        "[V1]\n"
        "Melody: | C4 . E4 G4 | A4 G4 E4 C4 |\n"
        "Breath: | 1.0 . 0.6 0.9 | . 0.2 . . |\n"
        "Gaze: | far . near . | . close . . |\n"
    )

    def test_numeric_layers_report_mean_and_std(self):
        stats = annotation_stats(resolved(self.LAYERED), "Breath")
        self.assertEqual(stats["count"], 4)
        self.assertEqual(stats["mean"], 0.675)
        self.assertEqual(stats["std"], 0.311247)
        self.assertEqual((stats["min"], stats["max"]), (0.2, 1.0))

    def test_word_layers_report_zero_rather_than_inventing_numbers(self):
        stats = annotation_stats(resolved(self.LAYERED), "Gaze")
        self.assertEqual(stats["count"], 0)
        self.assertEqual(stats["mean"], 0.0)

    def test_values_filter_by_voice(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | 1 2 3 4 |\n@bass | c2 . g1 . |\nBreath: | 9 . 8 . |\n"
        arrangement = resolved(text)
        self.assertEqual(annotation_values(arrangement, "Breath"), [1.0, 2.0, 3.0, 4.0, 9.0, 8.0])
        self.assertEqual(annotation_values(arrangement, "Breath", voice="player:bass"), [9.0, 8.0])
        self.assertEqual(annotation_stats(arrangement, "breath", voice="player:bass")["mean"], 8.5)

    def test_a_piece_without_layers_has_no_values(self):
        arrangement = resolved("[V1]\nMelody: | C4 D4 E4 F4 |\n")
        self.assertEqual(annotation_values(arrangement, "Breath"), [])
        self.assertEqual(annotation_stats(arrangement, "Breath")["count"], 0)


class TestPublicApi(unittest.TestCase):
    def test_annotation_rows_filters_case_insensitively(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | a . . . |\nGaze: | b . . . |\n"
        score = parse(text)
        self.assertEqual([line.name for line in score.annotation_rows()], ["Breath", "Gaze"])
        self.assertEqual([line.name for line in score.annotation_rows("breath")], ["Breath"])
        self.assertEqual([line.name for line in score.annotation_rows("nope")], [])

    def test_describe_names_the_layers(self):
        text = (
            "[V1]\nMelody: | C4 D4 E4 F4 |\nBreath: | a . . . |\n"
            "@bass | c2 . g1 . |\nBreath: | b . c . | on: @bass\n"
        )
        summary = describe(text)
        self.assertEqual(
            summary["annotations"],
            {"Breath": {"values": 3, "voices": ["melody", "player:bass"]}},
        )

    def test_describe_of_a_plain_file_has_no_annotations_key(self):
        summary = describe("[V1]\nMelody: | C4 D4 E4 F4 |\n")
        self.assertNotIn("annotations", summary)


if __name__ == "__main__":
    unittest.main()
