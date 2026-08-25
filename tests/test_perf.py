"""``[Perf]`` blocks: performance channels over the piece's own voices.

The first ship-step of the perf spec (``docs/perf-spec-draft.md`` §18),
seminar-gated to literal values (seminar response A1 -- expressions and
recursion are v2, behind demonstrated need). These tests hold:

* parsing: a ``[Perf]`` section is read, not played; its rows are channel
  tables ``@voice.channel | values |``, and anything else warns;
* alignment: the k-th value of a cell holds the k-th token of that voice's
  bar, through the same ``walk_bars`` the ``Vel:`` row uses; a voice running
  across several rows is one stream, marked in order;
* velocity: a ``vel`` channel drives per-note MIDI velocity, and the bytes
  carry it;
* precedence: ``[Perf]`` wins over ``Vel:`` rows and inline ``@n``/``!``
  marks; a ``.`` leaves those standing;
* data: unknown channels are kept, addressed and queryable, with zero effect
  on the compile;
* backward compatibility: a piece with no ``[Perf]`` block compiles to the
  very bytes it did before the block existed (golden digests below, captured
  from the pre-change compiler), and the corpus fingerprint does not move;
* round-trip: emitted notation carries the block, so a transposed take keeps
  its channels.
"""

from __future__ import annotations

import hashlib
import unittest

from plainsong.notation import arrange, parse
from plainsong.notation.arrange import ArrangeOptions
from plainsong.notation.ir import ROLE_PERF
from plainsong.render.midi import midi_bytes
from plainsong.transform import describe, to_text, transpose

try:  # the helper lives beside the dynamics tests; copying it would duplicate
    from tests.test_dynamics_swing import note_ons
except ImportError:  # pragma: no cover - direct-file run fallback
    from test_dynamics_swing import note_ons  # type: ignore[no-redef]


def resolved(text: str, **options: object):
    """The arrangement of *text* with humanising off, so numbers are exact."""
    return arrange(parse(text), ArrangeOptions(humanize=False, **options))


def velocities(arrangement) -> list[int]:
    """Every note-on velocity in onset order, as the arrangement holds it."""
    notes = sorted(
        ((note.start, note.pitch, note.velocity) for _track, note in arrangement.iter_notes()),
    )
    return [velocity for _start, _pitch, velocity in notes]


def wire_velocities(arrangement) -> list[int]:
    """Every note-on velocity in onset order, as the MIDI file carries it."""
    played = sorted(note_ons(midi_bytes(arrangement)))
    return [velocity for _tick, _pitch, velocity in played]


class TestPerfParsing(unittest.TestCase):
    def test_channel_rows_parse_not_played(self) -> None:
        score = parse("[V1]\nMelody: | C4 D4 E4 F4 |\n[Perf]\n@melody.vel | 40 90 40 90 |\n")
        self.assertEqual(len(score.sections), 1)
        self.assertEqual([line.role for line in score.sections[0].lines], ["melody"])
        self.assertEqual(len(score.perf), 1)
        row = score.perf[0]
        self.assertEqual((row.role, row.name, row.options["voice"]), (ROLE_PERF, "vel", "melody"))
        self.assertEqual([cell.tokens for cell in row.cells], [["40", "90", "40", "90"]])
        self.assertFalse(score.warnings())

    def test_bare_row_kind_and_player_names(self) -> None:
        text = (
            "[V1]\n@piano | C4 . E4 . | G4 . . . |\nChords: | Am . . . |\n"
            "[Perf]\npiano.vel | 60 . 70 . |\nchords.vel | 50 . . . |\n"
        )
        score = parse(text)
        self.assertEqual(
            [(row.options["voice"], row.name) for row in score.perf],
            [("piano", "vel"), ("chords", "vel")],
        )

    def test_junk_values_warn_and_are_kept(self) -> None:
        score = parse("[V1]\nMelody: | C4 D4 |\n[Perf]\nmelody.vel | mf cresc |\n")
        self.assertTrue(any("v1 values are numbers" in d.message for d in score.warnings()))
        self.assertEqual(score.perf[0].cells[0].tokens, ["mf", "cresc"])

    def test_unrecognised_row_warns(self) -> None:
        score = parse("[V1]\nMelody: | C4 D4 |\n[Perf]\nnot a channel row\n")
        self.assertTrue(any("[Perf] row not understood" in d.message for d in score.warnings()))
        self.assertEqual(score.perf, [])

    def test_comments_are_allowed(self) -> None:
        score = parse("[V1]\nMelody: | C4 D4 |\n[Perf]\n# the take\n@melody.vel | 40 90 |\n")
        self.assertEqual(len(score.perf), 1)
        self.assertFalse(score.warnings())

    def test_block_ends_at_the_next_header(self) -> None:
        score = parse(
            "[V1]\nMelody: | C4 D4 |\n[Perf]\nmelody.vel | 40 90 |\n"
            "[V2]\nMelody: | E4 F4 |\n"
        )
        self.assertEqual([s.name for s in score.sections], ["V1", "V2"])
        self.assertEqual(len(score.sections[1].lines), 1)  # no perf row leaked in

    def test_no_block_constructs_nothing_phantom(self) -> None:
        score = parse("[V1]\nMelody: | C4 D4 |\n")
        self.assertEqual(score.perf, [])
        self.assertEqual(arrange(score).perf, [])


class TestPerfAlignment(unittest.TestCase):
    def test_values_hold_their_columns(self) -> None:
        arrangement = resolved(
            "[V1]\n@piano | C4 . E4 (rest) | G4 F4 . . |\n"
            "[Perf]\npiano.vel | 40 . 70 . | . 64 . . |\n"
        )
        # Bar 1: attacks at C4 (40) and E4 (70); the rest consumes nothing.
        # Bar 2: F4 takes 64 from its column; G4 keeps the row base.
        self.assertEqual(velocities(arrangement), [40, 70, 76, 64])

    def test_a_voice_running_across_rows_is_one_stream(self) -> None:
        arrangement = resolved(
            "[V1] (4 Bars)\n"
            "@piano | C4 . E4 . | F4 . . . |\n"
            "@piano | G4 . B4 . | C5 . . . |\n"
            "[Perf]\npiano.vel | 40 . 50 . | 60 . . . | 70 . 80 . | . . . . |\n"
        )
        self.assertEqual(velocities(arrangement), [40, 50, 60, 70, 80, 76])

    def test_extra_values_warn_and_do_nothing(self) -> None:
        arrangement = resolved(
            "[V1]\nMelody: | C4 . E4 . |\n[Perf]\nmelody.vel | 40 50 60 70 80 90 |\n"
        )
        self.assertTrue(
            any("writes 6 value(s) over 4 token(s)" in d.message for d in arrangement.diagnostics)
        )
        self.assertEqual(velocities(arrangement), [40, 60])

    def test_unmatched_voice_warns(self) -> None:
        arrangement = resolved(
            "[V1]\nMelody: | C4 D4 |\n[Perf]\n@cello.vel | 40 90 |\n"
        )
        self.assertTrue(
            any("names a voice the piece does not play" in d.message for d in arrangement.diagnostics)
        )
        self.assertEqual(velocities(arrangement), [88, 88])

    def test_second_vel_channel_over_one_voice_is_a_conflict(self) -> None:
        arrangement = resolved(
            "[V1]\nMelody: | C4 D4 |\n"
            "[Perf]\nmelody.vel | 40 90 |\nmelody.vel | 100 110 |\n"
        )
        self.assertTrue(any("the first stands" in d.message for d in arrangement.diagnostics))
        self.assertEqual(velocities(arrangement), [40, 90])


class TestPerfVelocityToMidi(unittest.TestCase):
    def test_velocities_reach_the_wire(self) -> None:
        arrangement = resolved(
            "[V1]\n@piano | C3-G3-D4 . E4 G4 (rest) C5 . . |\n"
            "[Perf]\npiano.vel | 96 . 70 20 . 110 . . . |\n"
        )
        # The stack is one attack and takes one value; spacers sit over the
        # sustain and the rest, which consume nothing.
        self.assertEqual(velocities(arrangement), [96, 96, 96, 70, 20, 110])
        self.assertEqual(wire_velocities(arrangement), velocities(arrangement))

    def test_velocities_are_clamped_to_the_midi_range(self) -> None:
        arrangement = resolved(
            "[V1]\nMelody: | C4 D4 E4 |\n[Perf]\nmelody.vel | 1 999 64 |\n"
        )
        self.assertEqual(velocities(arrangement), [1, 127, 64])

    def test_floats_are_data_not_velocities(self) -> None:
        arrangement = resolved(
            "[V1]\nMelody: | C4 D4 |\n[Perf]\nmelody.vel | 60.5 90 |\n"
        )
        self.assertTrue(
            any("velocities are integers 1-127" in d.message for d in arrangement.diagnostics)
        )
        self.assertEqual(velocities(arrangement), [88, 90])


class TestPerfPrecedence(unittest.TestCase):
    def test_perf_wins_over_vel_row_and_inline_marks(self) -> None:
        arrangement = resolved(
            "[V1]\nMelody: | C4! D4@40 E4 F4 |\nVel: | mf . f . |\n"
            "[Perf]\nmelody.vel | . . 30 . |\n"
        )
        # C4: mf + accent = 100, the channel says nothing. D4: the @40 mark.
        # E4: 30 beats Vel:'s f. F4: f holds, 96.
        self.assertEqual(velocities(arrangement), [100, 40, 30, 96])

    def test_spacers_compose_rather_than_flatten(self) -> None:
        arrangement = resolved(
            "[V1]\nMelody: | C4 D4 E4 F4 |\nVel: | 40 . 90 . |\n"
            "[Perf]\nmelody.vel | . 70 . 110 |\n"
        )
        # Every other note from each source: the take speaks between the marks.
        self.assertEqual(velocities(arrangement), [40, 70, 90, 110])


class TestPerfDataChannels(unittest.TestCase):
    def test_unknown_channels_are_addressed_and_queryable(self) -> None:
        arrangement = resolved(
            "[V1]\nMelody: | C4 D4 E4 (rest) | F4 . . . |\n"
            "[Perf]\nmelody.ache | 0.2 0.9 0.5 . | 0.7 . . . |\n"
        )
        self.assertEqual(len(arrangement.perf), 4)
        marked = next(a for a in arrangement.perf if a.token == "0.9")
        self.assertEqual(
            (marked.name, marked.voice, marked.bar, marked.onset, marked.target),
            ("ache", "melody", 0, 1.0, "D4"),
        )
        # The address agrees with the time grid: same arithmetic or nothing.
        column = arrangement.grid.column(marked.bar, marked.unit)
        self.assertTrue(column and column[0].token == "D4")

    def test_vel_channel_is_data_too(self) -> None:
        arrangement = resolved(
            "[V1]\nMelody: | C4 D4 |\n[Perf]\nmelody.vel | 40 90 |\n"
        )
        tokens = [(a.name, a.token) for a in arrangement.perf]
        self.assertEqual(tokens, [("vel", "40"), ("vel", "90")])

    def test_data_channels_change_no_byte(self) -> None:
        music = "[V1]\n@piano | C3-G3-D4 . E4 G4 | vel: 82\n"
        bare = resolved(music)
        layered = resolved(music + "[Perf]\npiano.ache | 0.2 0.9 0.5 0.4 |\n")
        self.assertEqual(midi_bytes(bare), midi_bytes(layered))

    def test_describe_reports_channels(self) -> None:
        summary = describe(
            "[V1]\nMelody: | C4 D4 |\n[Perf]\nmelody.vel | 40 90 |\nmelody.ache | 0.2 . |\n"
        )
        self.assertEqual(
            summary["perf"],
            {
                "vel": {"values": 2, "voices": ["melody"]},
                "ache": {"values": 1, "voices": ["melody"]},
            },
        )


class TestPerfBackwardCompatibility(unittest.TestCase):
    FIXTURE = """**TRACK: Perf Compat**
[MetaData]
key: Am | tempo: 96 | time: 4/4

[V1] (4 Bars)
Chords: | Am . . . | F . . . | C . . . | G . . . |
Melody: | A4 . C5! E5@40 | F4 . A4 C5 | E4 . G4 C5 | D4 . F4 B4 |
Lyrics: | the tide came | in before dawn | and left a | line of salt |
Vel: | mf . . f | . . cresc . | . dim . . | . . . . |
@bass   | a1 . e2 . | f1 . c2 . | c1 . g1 . | g1 . d2 . | vel: 70
"""

    # Captured from the compiler before [Perf] existed: a piece with no block
    # must meet these digests exactly, humanised and not. If this test fails,
    # the block changed notation it was never addressing.
    GOLDEN_HUMANIZED = "acc7ce3b39478b338ef32bf95a8e00e77005cc0b9f4f6719efed0bab45b78633"
    GOLDEN_EXACT = "cf1724d880db973edb54224087e78d94901ff7352590153aac4fde5450102e2b"

    def test_no_block_is_byte_identical(self) -> None:
        exact = midi_bytes(resolved(self.FIXTURE))
        self.assertEqual(hashlib.sha256(exact).hexdigest(), self.GOLDEN_EXACT)
        humanized = midi_bytes(arrange(parse(self.FIXTURE)))
        self.assertEqual(hashlib.sha256(humanized).hexdigest(), self.GOLDEN_HUMANIZED)

    def test_data_only_block_is_byte_identical(self) -> None:
        bare = midi_bytes(resolved(self.FIXTURE))
        layered = midi_bytes(resolved(self.FIXTURE + "[Perf]\nmelody.ache | 0.2 . | . . | . . | . . |\n"))
        self.assertEqual(bare, layered)


class TestPerfRoundTrip(unittest.TestCase):
    def test_emitted_text_carries_the_block(self) -> None:
        score = parse(
            "[V1]\nMelody: | C4 D4 E4 F4 |\n[Perf]\nmelody.vel | 40 90 40 90 |\nmelody.ache | 0.2 . . . |\n"
        )
        again = parse(to_text(score))
        self.assertEqual(len(again.perf), 2)
        self.assertEqual(
            [(r.options["voice"], r.name, [c.tokens for c in r.cells]) for r in again.perf],
            [
                ("melody", "vel", [["40", "90", "40", "90"]]),
                ("melody", "ache", [["0.2", ".", ".", "."]]),
            ],
        )

    def test_transposing_a_take_keeps_its_channels(self) -> None:
        text = (
            "[V1]\nMelody: | C4 D4 E4 F4 |\n[Perf]\nmelody.vel | 40 90 40 90 |\n"
        )
        moved = transpose(text, 2)
        again = parse(moved)
        self.assertEqual([r.name for r in again.perf], ["vel"])
        self.assertEqual(
            velocities(resolved(moved)),
            velocities(resolved(text)),
        )
        notes = sorted(again.sections[0].lines[0].cells[0].tokens)
        self.assertEqual(notes, ["D4", "E4", "F#4", "G4"])


if __name__ == "__main__":
    unittest.main()
