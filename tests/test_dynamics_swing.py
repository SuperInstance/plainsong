"""Per-note dynamics and swing: the two things a lead sheet could not say.

A row-level ``vel: 70`` sets one loudness for a whole player; everything in
that row sounded at it. These tests hold the newer, finer controls to the bar
the repository holds everything to -- not "it compiled", but the exact bytes:

* a ``Vel:`` row marks the row above it, token by token, and the marks reach
  the arrangement as per-note velocities, not per-row ones;
* ``C4!`` and ``C4@99`` ride on the token itself, through transposition;
* ``swing:`` is a playback decision with exact arithmetic: the long eighth of
  each pair occupies the named share of the beat, and nothing written moves;
* a file that uses none of this compiles to the bytes it always did, which the
  golden fixture here asserts at the MIDI level and the corpus fingerprint
  asserts over every file in the repository.
"""

from __future__ import annotations

import struct
import unittest
from pathlib import Path

from plainsong.features import extract
from plainsong.notation import arrange, parse
from plainsong.notation.arrange import ArrangeOptions, swing_amount
from plainsong.render.midi import midi_bytes
from plainsong.transform import to_text, transpose

GOLDEN = Path(__file__).parent / "golden"


# --------------------------------------------------------------------------
# A minimal Standard MIDI File reader, so the tests assert what a sequencer
# would see rather than what the writer believes it wrote.
# --------------------------------------------------------------------------

def note_events(data: bytes) -> list[tuple[int, int, int, int]]:
    """(absolute_tick, status_nibble, pitch, velocity) for note events.

    Channel-9 drum tracks and all other channels are returned alike; the
    conductor track carries no note events, so it contributes nothing.
    """

    def read_vlq(body: bytes, index: int) -> tuple[int, int]:
        value = 0
        while True:
            byte = body[index]
            index += 1
            value = (value << 7) | (byte & 0x7F)
            if not byte & 0x80:
                return value, index

    events: list[tuple[int, int, int, int]] = []
    position = 0
    while position < len(data):
        tag = data[position : position + 4]
        size = struct.unpack(">I", data[position + 4 : position + 8])[0]
        body = data[position + 8 : position + 8 + size]
        position += 8 + size
        if tag != b"MTrk":
            continue
        tick = 0
        index = 0
        while index < len(body):
            delta, index = read_vlq(body, index)
            tick += delta
            status = body[index]
            if status == 0xFF:
                index += 1
                kind = body[index]
                index += 1
                length, index = read_vlq(body, index)
                index += length
            elif status & 0xF0 in (0x80, 0x90, 0xB0, 0xE0):
                events.append((tick, status & 0xF0, body[index + 1], body[index + 2]))
                index += 3
            elif status & 0xF0 in (0xC0, 0xD0):
                index += 2
            else:
                raise AssertionError(f"unexpected status byte {status:#x}")
    return events


def note_ons(data: bytes) -> list[tuple[int, int, int]]:
    """(tick, pitch, velocity) for every note-on, in file order."""
    return [
        (tick, pitch, velocity)
        for tick, status, pitch, velocity in note_events(data)
        if status == 0x90 and velocity > 0
    ]


def velocities(text: str, **options: object) -> list[int]:
    """The arrangement's note velocities, in order, with humanising off."""
    arrangement = arrange(parse(text), ArrangeOptions(humanize=False, **options))
    notes = [note for _track, note in arrangement.iter_notes()]
    notes.sort(key=lambda note: (note.start, note.pitch))
    return [note.velocity for note in notes]


class TestVelRowParsing(unittest.TestCase):
    def test_a_vel_row_is_a_row_of_its_own_kind(self):
        score = parse("[V1]\nMelody: | C4 D4 E4 F4 |\nVel: | 90 . 60 70 |\n")
        self.assertEqual(len(score.sections), 1)
        roles = [line.role for line in score.sections[0].lines]
        self.assertEqual(roles, ["melody", "velocity"])
        marks = score.sections[0].lines[1].cells[0].tokens
        self.assertEqual(marks, ["90", ".", "60", "70"])

    def test_a_vel_row_without_a_row_above_it_warns_at_parse_time(self):
        score = parse("[V1]\nVel: | 90 90 90 90 |\n")
        self.assertIn(
            "Vel: row has no playable row above it to mark",
            " ".join(diag.message for diag in score.warnings()),
        )

    def test_a_vel_row_is_emitted_and_reads_back(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nVel: | 90 . 60 70 |\n"
        again = to_text(parse(text))
        reparsed = parse(again)
        roles = [line.role for line in reparsed.sections[0].lines]
        self.assertEqual(roles, ["melody", "velocity"])
        self.assertEqual(reparsed.sections[0].lines[1].cells[0].tokens, ["90", ".", "60", "70"])

    def test_transposing_leaves_the_vel_row_where_it_was(self):
        text = (
            "[V1]\nMelody: | C4 D4 E4 F4 |\nVel: | 90 . 60 70 |\n"
            "@bass | c2 . g1 . | vel: 70\n"
        )
        moved = transpose(text, 2)
        reparsed = parse(moved)
        vel_row = [line for line in reparsed.sections[0].lines if line.role == "velocity"]
        self.assertEqual(vel_row[0].cells[0].tokens, ["90", ".", "60", "70"])
        # The marked melody moved; its marks did not turn into bars.
        melody = reparsed.sections[0].lines[0]
        self.assertEqual(melody.bar_count, 1)
        self.assertEqual(melody.cells[0].tokens, ["D4", "E4", "F#4", "G4"])


class TestPerNoteVelocities(unittest.TestCase):
    def test_marks_land_on_the_notes_they_are_written_under(self):
        text = "[V1]\nMelody: | A4 B4 C5 D5 |\nVel: | 90 . 60 70 |\n"
        # The mark holds until the next one: 90, 90, 60, 70.
        self.assertEqual(velocities(text), [90, 90, 60, 70])

    def test_a_mark_over_a_sustain_marks_nothing(self):
        text = "[V1]\nMelody: | A4 . C5 D5 |\nVel: | 90 . 60 70 |\n"
        self.assertEqual(velocities(text), [90, 60, 70])

    def test_named_dynamics_hold_until_changed(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nVel: | p . . f |\n"
        self.assertEqual(velocities(text), [48, 48, 48, 96])

    def test_deltas_ride_on_the_row_base(self):
        text = "[V1]\n@bass | e1 e1 e1 e1 | vel: 60\nVel: | +20 . -10 . |\n"
        self.assertEqual(velocities(text), [80, 80, 70, 70])

    def test_crescendo_reaches_its_target_on_the_marked_note(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 G4 |\nVel: | p . cresc . mf |\n"
        # 48 held, then a ramp 48 -> 80 over three notes, 80 on the marked one.
        self.assertEqual(velocities(text), [48, 48, 48, 64, 80])

    def test_a_crescendo_without_a_target_climbs_twenty_four(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nVel: | cresc . . . |\n"
        self.assertEqual(velocities(text), [88, 96, 104, 112])

    def test_a_diminuendo_falls(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nVel: | ff . dim . |\n"
        self.assertEqual(velocities(text), [112, 112, 112, 88])

    def test_the_midi_file_carries_the_velocities_per_note(self):
        text = "[V1]\nMelody: | A4 B4 C5 D5 |\nVel: | 100 . 40 70 |\n"
        arrangement = arrange(parse(text), ArrangeOptions(humanize=False))
        data = midi_bytes(arrangement)
        played = sorted(note_ons(data))
        self.assertEqual(
            played,
            [(0, 69, 100), (480, 71, 100), (960, 72, 40), (1440, 74, 70)],
        )

    def test_extra_marks_warn_rather_than_vanish(self):
        text = "[V1]\nMelody: | C4 D4 |\nVel: | 90 90 90 90 |\n"
        arrangement = arrange(parse(text), ArrangeOptions(humanize=False))
        messages = " ".join(diag.message for diag in arrangement.diagnostics)
        self.assertIn("Vel: bar 1 writes 4 mark(s) over 2 token(s)", messages)

    def test_an_unreadable_mark_warns(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 |\nVel: | loudly . . . |\n"
        arrangement = arrange(parse(text), ArrangeOptions(humanize=False))
        messages = " ".join(diag.message for diag in arrangement.diagnostics)
        self.assertIn("Vel: row: nothing understood loudly", messages)


class TestInlineDynamics(unittest.TestCase):
    def test_an_accent_adds_twenty(self):
        self.assertEqual(velocities("[V1]\nMelody: | C4! D4 E4 F4 |\n"), [108, 88, 88, 88])

    def test_an_exact_velocity_is_clamped_to_the_midi_range(self):
        self.assertEqual(velocities("[V1]\nMelody: | C4@40 D4@999 E4 F4 |\n"), [40, 127, 88, 88])

    def test_accent_and_exact_combine(self):
        self.assertEqual(velocities("[V1]\nMelody: | C4@40! D4 E4 F4 |\n"), [60, 88, 88, 88])

    def test_a_stack_is_marked_as_one_attack(self):
        self.assertEqual(velocities("[V1]\n@p | c3-e3-g3! . . . |\n"), [96, 96, 96])

    def test_a_chord_symbol_can_carry_a_mark(self):
        self.assertEqual(velocities("[V1]\nChords: | Am! . G@70 . |\n"), [84, 84, 84, 70, 70, 70])

    def test_sustains_come_after_the_mark(self):
        self.assertEqual(velocities("[V1]\nMelody: | C4!~~~ . . . |\n"), [108])

    def test_the_midi_file_carries_the_accent(self):
        arrangement = arrange(
            parse("[V1]\nMelody: | C4! D4 E4 F4 |\n"), ArrangeOptions(humanize=False)
        )
        played = sorted(note_ons(midi_bytes(arrangement)))
        self.assertEqual(
            [velocity for _tick, _pitch, velocity in played], [108, 88, 88, 88]
        )

    def test_a_mark_survives_transposition(self):
        moved = transpose("[V1]\nMelody: | C4! D4 E4 F4 |\nChords: | Am! . F . |\n", 1)
        arrangement = arrange(parse(moved), ArrangeOptions(humanize=False))
        by_role = {track.role: track for track in arrangement.tracks}
        self.assertEqual(
            [note.velocity for note in sorted(by_role["melody"].notes, key=lambda n: n.start)],
            [108, 88, 88, 88],
        )
        chord_velocities = [
            note.velocity
            for note in sorted(by_role["chords"].notes, key=lambda n: (n.start, n.pitch))
        ]
        # The marked chord accents, the one after it does not.
        self.assertEqual(chord_velocities, [84, 84, 84, 64, 64, 64])

    def test_relative_degrees_take_marks_too(self):
        text = "key: C\n[V1]\n| 1 . 3! . |\n"
        arrangement = arrange(parse(text), ArrangeOptions(humanize=False))
        notes = sorted(arrangement.tracks[0].notes, key=lambda note: note.start)
        self.assertEqual([note.pitch for note in notes], [60, 64])
        self.assertEqual([note.velocity for note in notes], [88, 108])

    def test_an_inline_mark_wins_over_the_vel_row(self):
        text = "[V1]\nMelody: | C4! D4 E4@50 F4 |\nVel: | 90 . 90 . |\n"
        self.assertEqual(velocities(text), [110, 90, 50, 90])


class TestSwingTiming(unittest.TestCase):
    def straight_eighths(self, swing: float) -> list[tuple[int, int]]:
        text = "[V1]\nMelody: | C4 D4 E4 F4 G4 A4 B4 C5 |\n"
        arrangement = arrange(
            parse(text), ArrangeOptions(humanize=False, swing=swing)
        )
        return sorted((tick, pitch) for tick, pitch, _velocity in note_ons(midi_bytes(arrangement)))

    def test_sixty_six_percent_is_a_triplet(self):
        played = self.straight_eighths(2.0 / 3.0)
        self.assertEqual(
            [tick for tick, _pitch in played],
            [0, 320, 480, 800, 960, 1280, 1440, 1760],
        )

    def test_sixty_six_percent_written_in_the_header_rounds_the_same_way(self):
        text = "[MetaData]\nswing: 66%\n\n[V1]\nMelody: | C4 D4 E4 F4 G4 A4 B4 C5 |\n"
        arrangement = arrange(parse(text), ArrangeOptions(humanize=False))
        played = sorted(note_ons(midi_bytes(arrangement)))
        # 0.5 + 0.16 = 0.66 of a beat = 316.8 ticks, written as 317.
        self.assertEqual(
            [tick for tick, _p, _v in played], [0, 317, 480, 797, 960, 1277, 1440, 1757]
        )

    def test_seventy_five_is_dotted(self):
        played = self.straight_eighths(0.75)
        self.assertEqual(
            [tick for tick, _pitch in played],
            [0, 360, 480, 840, 960, 1320, 1440, 1800],
        )

    def test_fifty_percent_is_straight(self):
        played = self.straight_eighths(0.5)
        self.assertEqual([tick for tick, _pitch in played], [0, 240, 480, 720, 960, 1200, 1440, 1680])

    def test_below_fifty_reads_as_straight(self):
        self.assertEqual(self.straight_eighths(0.3), self.straight_eighths(0.5))

    def test_above_ninety_is_held_at_ninety(self):
        played = self.straight_eighths(0.95)
        self.assertEqual([tick for tick, _pitch in played][1], round(0.9 * 480))

    def test_the_pair_is_long_short_not_late(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 G4 A4 B4 C5 |\n"
        arrangement = arrange(parse(text), ArrangeOptions(humanize=False, swing=2.0 / 3.0))
        data = midi_bytes(arrangement)
        ons = sorted(tick for tick, _p, _v in note_ons(data))
        offs = sorted(tick for tick, status, _p, _v in note_events(data) if status == 0x80)
        # Long eighth: on 0, off 320. Short: on 320, off 480. Nothing overlaps.
        self.assertEqual(ons, [0, 320, 480, 800, 960, 1280, 1440, 1760])
        self.assertEqual(offs, [320, 480, 800, 960, 1280, 1440, 1760, 1920])

    def test_the_written_times_do_not_move(self):
        text = "[MetaData]\nswing: 66%\n\n[V1]\nChords: | Am . . . |\nMelody: | C4 D4 E4 F4 G4 A4 B4 C5 |\n"
        arrangement = arrange(parse(text), ArrangeOptions(humanize=False))
        # The grid is the notation's own timing: every token where it was written.
        melody_units = sorted(
            placement.onset
            for placement in arrangement.grid.placements
            if placement.row == "melody"
        )
        self.assertEqual(melody_units, [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5])
        # Chord events -- what a lead sheet or a chart reads -- stay straight.
        self.assertEqual([chord.start for chord in arrangement.chords], [0.0])
        # And the played melody did swing.
        played = sorted(note.start for note in arrangement.tracks[1].notes)
        self.assertEqual(played[1], 0.5 + 0.16)

    def test_a_tie_stretches_to_the_moved_offbeat(self):
        # Sixteenth tokens: C4 is held by the sustain onto the half-beat, then
        # rests. The tie has to reach the moved off-beat, not the written one.
        text = "[V1]\nMelody: | C4 . r r E4 . r r G4 . r r B4 . r r |\n"
        straight = arrange(parse(text), ArrangeOptions(humanize=False))
        swung = arrange(parse(text), ArrangeOptions(humanize=False, swing=0.75))
        self.assertEqual(straight.tracks[0].notes[0].end, 0.5)
        self.assertAlmostEqual(swung.tracks[0].notes[0].end, 0.75, places=6)

    def test_the_last_eighth_of_a_bar_never_crosses_the_bar_line(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 | G4 A4 B4 C5 |\n"
        arrangement = arrange(parse(text), ArrangeOptions(humanize=False, swing=0.9))
        ends = [note.end for note in sorted(arrangement.tracks[0].notes, key=lambda n: n.start)]
        self.assertEqual(ends[3], 4.0)
        self.assertEqual(ends[7], 8.0)

    def test_the_swing_amount_is_clamped(self):
        self.assertEqual(swing_amount(0.0), 0.5)
        self.assertEqual(swing_amount(0.66), 0.66)
        self.assertEqual(swing_amount(1.0), 0.9)
        self.assertEqual(swing_amount(-0.2), 0.5)


class TestBackwardCompatibility(unittest.TestCase):
    def test_a_file_without_the_new_syntax_compiles_byte_identically(self):
        song = (GOLDEN / "compat.song").read_text()
        arrangement = arrange(parse(song))
        self.assertEqual(midi_bytes(arrangement), (GOLDEN / "compat.song.golden").read_bytes())

    def test_the_same_file_with_humanising_off_is_also_unchanged(self):
        song = (GOLDEN / "compat.song").read_text()
        arrangement = arrange(parse(song), ArrangeOptions(humanize=False))
        self.assertEqual(
            midi_bytes(arrangement), (GOLDEN / "compat_noHumanize.song.golden").read_bytes()
        )


class TestFeaturesRespond(unittest.TestCase):
    def test_velocity_features_see_per_note_dynamics(self):
        flat = extract(
            arrange(
                parse("[V1]\nMelody: | C4 D4 E4 F4 |\n"),
                ArrangeOptions(humanize=False),
            )
        )
        marked = extract(
            arrange(
                parse("[V1]\nMelody: | C4 D4 E4 F4 |\nVel: | 120 . 40 120 |\n"),
                ArrangeOptions(humanize=False),
            ),
        )
        self.assertEqual(flat[0].values["velocity_std"], 0.0)
        self.assertGreater(marked[0].values["velocity_std"], 0.1)
        self.assertEqual(marked[0].values["dynamic_range"], round((120 - 40) / 127, 6))
        # The mean moved too: the marks are not decorative.
        self.assertGreater(marked[0].values["velocity_mean"], flat[0].values["velocity_mean"])

    def test_swing_does_not_change_the_written_features(self):
        text = "[V1]\nMelody: | C4 D4 E4 F4 G4 A4 B4 C5 |\n"
        straight = extract(arrange(parse(text), ArrangeOptions(humanize=False)))
        swung = extract(arrange(parse(text), ArrangeOptions(humanize=False, swing=0.66)))
        # Rhythmic complexity reads the played times, so it moves; the notes
        # themselves -- density, pitch, contour -- must not.
        for name in ("note_density", "avg_pitch", "contour_direction", "interval_size"):
            self.assertEqual(
                straight[0].values[name], swung[0].values[name], f"{name} moved under swing"
            )


class TestRoundTripWithDynamics(unittest.TestCase):
    def test_repeated_transposition_does_not_grow_the_rows(self):
        text = (
            "[V1]\nMelody: | C4! D4 E4@50 F4 |\nVel: | 90 . 60 70 |\n"
            "@bass | c2 . g1 . | vel: 70\n"
        )
        widths: list[tuple[int, int, int]] = []
        current = text
        for _ in range(3):
            score = parse(current)
            widths.append(
                (
                    score.sections[0].lines[0].bar_count,
                    len(score.sections[0].lines[0].cells[0].tokens),
                    len(score.sections[0].lines[1].cells[0].tokens),
                )
            )
            current = to_text(score)
            current = transpose(current, 1)
        self.assertEqual(len(set(widths)), 1, f"rows drifted: {widths}")

    def test_emitted_notation_reparses_to_the_same_shape(self):
        text = "[V1]\nMelody: | C4! D4 E4@50 F4 |\nVel: | 90 . 60 cresc |\n"
        score = parse(text)
        again = parse(to_text(score))
        self.assertEqual(
            [line.role for line in score.sections[0].lines],
            [line.role for line in again.sections[0].lines],
        )
        self.assertEqual(
            score.sections[0].lines[0].cells[0].tokens,
            again.sections[0].lines[0].cells[0].tokens,
        )
        self.assertEqual(
            score.sections[0].lines[1].cells[0].tokens,
            again.sections[0].lines[1].cells[0].tokens,
        )


if __name__ == "__main__":
    unittest.main()
