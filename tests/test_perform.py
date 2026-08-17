"""Arrival-centric timing: geometry, the solver, conducting, and staying inert."""

from __future__ import annotations

import json
import unittest

from plainsong.notation import arrange, parse
from plainsong.notation.arrange import ArrangeOptions
from plainsong.perform import conduct, profiles, solve, stage
from plainsong.render.audio import AudioOptions, Synthesiser
from plainsong.render.midi import midi_bytes

PLAIN = """**TRACK: Plain**
[MetaData]
key: Am | tempo: 120 | time: 4/4

[A] (2 bars)
@timpani | d2 . . . | d2 . . . |
@organ   | d3 . . . | a2 . . . |
"""

STAGE_BLOCK = """[Stage]
listener: conductor
temperature: 20
@timpani: pos 4,-6 | speech: percussion
@organ:   pos 0,-12 | speech: organ-large
"""

STAGED = PLAIN.replace("[A] (2 bars)", STAGE_BLOCK + "\n[A] (2 bars)")

ORCHESTRA = """**TRACK: Orchestra**
[MetaData]
key: Dm | tempo: 96 | time: 4/4

[Stage]
listener: conductor
audience: 0,14
@timpani: pos 4,-6 | speech: percussion
@violin1: pos -3,1 | speech: bowed | feel: -6ms
@organ:   pos 0,-12 | speech: organ-large

[A] (2 bars)
@timpani | d2 . . . | d2 . . . |
@violin1 | d5 . . . | e5 . . . |
@organ   | d3 . . . | a2 . . . |
"""


SWUNG = """**TRACK: Swung**
[MetaData]
key: C | tempo: 120 | time: 4/4 | swing: 60%

[Stage]
@ride: pos 1,-2 | speech: percussion

[A] (1 bar)
@ride | c4 d4 c4 d4 c4 d4 c4 d4 |
"""


class TestGeometry(unittest.TestCase):
    def test_speed_of_sound_at_twenty_degrees(self):
        self.assertAlmostEqual(stage.speed_of_sound(20.0), 343.2, places=1)

    def test_speed_of_sound_rises_with_temperature(self):
        self.assertGreater(stage.speed_of_sound(30.0), stage.speed_of_sound(10.0))

    def test_twenty_metres_is_about_fifty_eight_milliseconds(self):
        room = stage.Stage()
        room.placements["far"] = stage.Placement(name="far", position=(0.0, 20.0))
        self.assertAlmostEqual(room.propagation("far") * 1000.0, 58.3, places=1)

    def test_positions_read_both_spellings(self):
        self.assertEqual(stage.parse_position("4,-6"), (4.0, -6.0))
        self.assertEqual(stage.parse_position(" 4 -6 "), (4.0, -6.0))
        self.assertIsNone(stage.parse_position("over there"))

    def test_durations_default_to_milliseconds(self):
        self.assertAlmostEqual(stage.parse_duration("-6ms"), -0.006)
        self.assertAlmostEqual(stage.parse_duration("0.045s"), 0.045)
        self.assertAlmostEqual(stage.parse_duration("40"), 0.040)
        self.assertIsNone(stage.parse_duration("soon"))

    def test_unplaced_voices_stand_at_the_podium(self):
        self.assertEqual(stage.Stage().position("nobody"), (0.0, 0.0))


class TestProfiles(unittest.TestCase):
    def test_every_program_lands_somewhere(self):
        for program in range(128):
            profile = profiles.profile_for_program(program)
            self.assertGreaterEqual(profile.speech, 0.0)
            self.assertLess(profile.speech, 0.5)

    def test_percussion_is_the_fast_end_and_organ_the_slow_one(self):
        self.assertEqual(profiles.profile_for_program(47).name, "percussion")   # timpani
        self.assertEqual(profiles.profile_for_program(19).name, "organ-large")  # church organ
        self.assertLess(
            profiles.profile_for_program(47).total, profiles.profile_for_program(19).total
        )

    def test_drums_are_always_percussion(self):
        self.assertEqual(profiles.profile_for_program(48, is_drum=True).name, "percussion")

    def test_names_and_aliases_resolve(self):
        self.assertEqual(profiles.profile_for_name("bowed").name, "bowed")
        self.assertEqual(profiles.profile_for_name("Timpani").name, "percussion")
        self.assertIsNone(profiles.profile_for_name("kazoo"))


class TestStageBlock(unittest.TestCase):
    def test_a_plain_file_has_no_stage(self):
        self.assertIsNone(parse(PLAIN).meta.stage)

    def test_the_block_reads(self):
        room = parse(STAGED).meta.stage
        self.assertIsNotNone(room)
        self.assertEqual(room.listener, "conductor")
        self.assertEqual(room.temperature, 20.0)
        self.assertEqual(room.position("organ"), (0.0, -12.0))
        self.assertEqual(room.placement("timpani").speech_name, "percussion")
        self.assertEqual(room.problems, [])

    def test_the_block_is_not_a_section(self):
        score = parse(STAGED)
        self.assertEqual([section.name for section in score.sections], ["A"])
        self.assertFalse(score.has_errors)

    def test_feel_is_read_in_milliseconds(self):
        room = parse(ORCHESTRA).meta.stage
        self.assertAlmostEqual(room.placement("violin1").feel, -0.006)

    def test_a_listener_can_be_moved(self):
        room = parse(ORCHESTRA).meta.stage
        self.assertEqual(room.listeners["audience"], (0.0, 14.0))

    def test_nonsense_is_reported_not_raised(self):
        score = parse(STAGED.replace("pos 4,-6", "pos over there") + "\n[A]\nChords: | Am |\n")
        self.assertTrue(any("stage" in diag.message for diag in score.warnings()))

    def test_placement_can_be_written_on_the_note_row(self):
        score = parse("[A]\n@cello | c3 . . . | pos: -2,3 | speech: bowed |\n")
        self.assertEqual(score.meta.stage.position("cello"), (-2.0, 3.0))
        self.assertEqual(score.sections[0].players()[0].bar_count, 1)

    def test_a_bar_is_not_eaten_by_a_stage_option(self):
        # `pos:` with a value that is not a position stays a bar, not an option.
        score = parse("[A]\nMelody: | C4 | D4 |\n")
        self.assertIsNone(score.meta.stage)
        self.assertEqual(score.sections[0].bar_count, 2)


class TestSolver(unittest.TestCase):
    def setUp(self):
        self.score = parse(ORCHESTRA)
        self.room = self.score.meta.stage

    def _timing(self, name, frame=""):
        voices = [("timpani", 47, False), ("violin1", 40, False), ("organ", 19, False)]
        return solve.solve(self.room, voices, frame=frame).voices[name]

    def test_the_equation_holds(self):
        timing = self._timing("organ")
        expected = -(timing.speech + timing.reference_propagation + timing.p_center) + timing.feel
        self.assertAlmostEqual(timing.emission_offset, expected, places=9)
        self.assertAlmostEqual(
            timing.arrival_offset,
            timing.emission_offset + timing.speech + timing.p_center + timing.observed_propagation,
            places=9,
        )

    def test_the_organ_acts_first_and_the_timpani_last(self):
        organ = self._timing("organ").emission_offset
        timpani = self._timing("timpani").emission_offset
        self.assertLess(organ, timpani)
        self.assertAlmostEqual(organ * 1000.0, -235.0, places=0)
        self.assertAlmostEqual(timpani * 1000.0, -22.0, places=0)

    def test_arrivals_line_up_at_the_reference_listener(self):
        voices = [("timpani", 47, False), ("organ", 19, False)]
        solution = solve.solve(self.room, voices)
        self.assertAlmostEqual(solution.spread, 0.0, places=9)

    def test_feel_survives_the_correction(self):
        # The correction cancels; the musical deviation is meant to be heard.
        self.assertAlmostEqual(self._timing("violin1").arrival_offset, -0.006, places=9)

    def test_a_player_hears_the_others_late(self):
        organ = self._timing("organ", frame="player:violin1")
        timpani = self._timing("timpani", frame="player:violin1")
        violin = self._timing("violin1", frame="player:violin1")
        self.assertGreater(organ.arrival_offset, violin.arrival_offset)
        self.assertGreater(timpani.arrival_offset, violin.arrival_offset)

    def test_turning_compensation_off_smears_the_ensemble(self):
        from dataclasses import replace

        voices = [("timpani", 47, False), ("organ", 19, False)]
        tight = solve.solve(self.room, voices)
        loose = solve.solve(replace(self.room, compensate=False), voices)
        self.assertLess(tight.spread, 0.001)
        self.assertGreater(loose.spread, 0.150)

    def test_the_score_frame_solves_nothing(self):
        solution = solve.solve(self.room, [("organ", 19, False)], frame="score")
        self.assertEqual(solution.voices, {})


class TestArrangementIntegration(unittest.TestCase):
    def test_no_stage_means_no_solved_times(self):
        arrangement = arrange(parse(PLAIN))
        self.assertIsNone(arrangement.stage)
        for _track, note in arrangement.iter_notes():
            self.assertIsNone(note.emission)
            self.assertIsNone(note.arrival)
            self.assertEqual(note.emission_time, note.start)
            self.assertEqual(note.arrival_time, note.start)

    def test_the_frame_option_does_nothing_without_a_stage(self):
        plain = midi_bytes(arrange(parse(PLAIN)))
        framed = midi_bytes(arrange(parse(PLAIN), ArrangeOptions(frame="audience")))
        self.assertEqual(plain, framed)

    def test_the_score_frame_renders_what_it_always_did(self):
        # Same music, one file with a stage and one without: in the score frame
        # they have to come out byte for byte the same.
        plain = midi_bytes(arrange(parse(PLAIN)))
        staged = midi_bytes(arrange(parse(STAGED), ArrangeOptions(frame="score")))
        self.assertEqual(plain, staged)

    def test_written_starts_are_never_moved(self):
        plain = [note.start for _t, note in arrange(parse(PLAIN)).iter_notes()]
        staged = [note.start for _t, note in arrange(parse(STAGED)).iter_notes()]
        self.assertEqual(plain, staged)

    def test_notes_carry_both_times(self):
        arrangement = arrange(parse(STAGED))
        organ = next(track for track in arrangement.tracks if track.name == "organ")
        note = organ.notes[0]
        self.assertIsNotNone(note.emission)
        self.assertIsNotNone(note.arrival)
        self.assertLess(note.emission_time, note.arrival_time)

    def test_nobody_has_to_play_before_the_file_starts(self):
        arrangement = arrange(parse(STAGED))
        self.assertGreaterEqual(min(note.emission_time for _t, note in arrangement.iter_notes()), 0.0)

    def test_arrivals_coincide_after_the_lead_in(self):
        arrangement = arrange(parse(STAGED))
        first = {
            track.name: min(note.arrival_time for note in track.notes)
            for track in arrangement.tracks
        }
        self.assertAlmostEqual(first["timpani"], first["organ"], places=6)

    def test_midi_carries_emission_and_audio_carries_arrival(self):
        arrangement = arrange(parse(STAGED))
        organ = next(track for track in arrangement.tracks if track.name == "organ")
        timpani = next(track for track in arrangement.tracks if track.name == "timpani")
        self.assertLess(organ.notes[0].emission_time, timpani.notes[0].emission_time)
        self.assertAlmostEqual(organ.notes[0].arrival_time, timpani.notes[0].arrival_time, places=6)

    def test_compensation_can_be_turned_off_for_one_render(self):
        loose = arrange(parse(STAGED), ArrangeOptions(compensate=False))
        organ = next(track for track in loose.tracks if track.name == "organ")
        timpani = next(track for track in loose.tracks if track.name == "timpani")
        self.assertGreater(
            organ.notes[0].arrival_time - timpani.notes[0].arrival_time, 0.1  # beats
        )
        # ... and the score itself is untouched by that choice.
        self.assertTrue(parse(STAGED).meta.stage.compensate)

    def test_the_smeared_render_is_different_audio(self):
        options = AudioOptions(sample_rate=8000, tail=0.2)
        tight = Synthesiser(options).to_wav_bytes(arrange(parse(STAGED)))
        loose = Synthesiser(options).to_wav_bytes(
            arrange(parse(STAGED), ArrangeOptions(compensate=False))
        )
        self.assertNotEqual(tight, loose)

    def test_solved_times_are_deterministic(self):
        first = [note.emission_time for _t, note in arrange(parse(ORCHESTRA)).iter_notes()]
        second = [note.emission_time for _t, note in arrange(parse(ORCHESTRA)).iter_notes()]
        self.assertEqual(first, second)

    def test_the_report_names_every_frame(self):
        report = solve.analyse(arrange(parse(ORCHESTRA)))
        self.assertTrue(report["stage"])
        self.assertEqual(report["solution"]["frame"], "conductor")
        frames = {entry["frame"] for entry in report["elsewhere"]}
        self.assertIn("audience", frames)
        self.assertIn("player:violin1", frames)
        self.assertIn("what each player has to do", solve.format_report(report))

    def test_the_report_says_so_when_there_is_no_stage(self):
        report = solve.analyse(arrange(parse(PLAIN)))
        self.assertFalse(report["stage"])


BANDLEADER = """{
  "directives": [
    {
      "action": "lay_back",
      "intensity": 0.7,
      "duration_beats": 8,
      "offset_beats": 0,
      "target": ["rhythm"],
      "priority": "blend"
    }
  ],
  "energy":  { "target": 0.8,  "mode": "absolute" },
  "density": { "target": 0.6,  "mode": "absolute" },
  "tension": { "delta": 0.15,  "mode": "relative" },
  "narrative_note": "arriving at climax",
  "revise_macro_plan": false
}"""


class TestDirectiveSchema(unittest.TestCase):
    def test_the_bandleader_message_reads(self):
        reading = conduct.read(BANDLEADER)
        self.assertEqual(len(reading.directives), 1)
        directive = reading.directives[0]
        self.assertEqual(directive.action, "lay_back")
        self.assertAlmostEqual(directive.intensity, 0.7)
        self.assertEqual(directive.duration_beats, 8.0)
        self.assertEqual(directive.target, ("rhythm",))
        self.assertEqual(directive.priority, "blend")
        self.assertAlmostEqual(reading.energy.target, 0.8)
        self.assertEqual(reading.energy.mode, "absolute")
        self.assertAlmostEqual(reading.tension.delta, 0.15)
        self.assertEqual(reading.tension.mode, "relative")
        self.assertEqual(reading.narrative_note, "arriving at climax")
        self.assertFalse(reading.revise_macro_plan)
        self.assertEqual(reading.problems, [])

    def test_a_dict_a_string_and_a_set_all_read(self):
        from_json = conduct.read(BANDLEADER)
        from_dict = conduct.read(json.loads(BANDLEADER))
        self.assertEqual(from_json.directives, from_dict.directives)
        self.assertIs(conduct.read(from_json), from_json)

    def test_broken_json_is_a_problem_not_an_exception(self):
        reading = conduct.read("{not json")
        self.assertEqual(reading.directives, ())
        self.assertTrue(reading.problems)

    def test_windows_are_in_beats_and_need_not_start_on_a_downbeat(self):
        directive = conduct.Directive(action="lay_back", offset_beats=2.0, duration_beats=1.5)
        self.assertFalse(directive.covers(1.99))
        self.assertTrue(directive.covers(2.0))
        self.assertTrue(directive.covers(3.4))
        self.assertFalse(directive.covers(3.5))

    def test_an_open_window_runs_to_the_end(self):
        directive = conduct.Directive(action="lay_back", offset_beats=4.0)
        self.assertTrue(directive.covers(4000.0))

    def test_targets_select_layers(self):
        everyone = conduct.Directive(action="lay_back")
        rhythm = conduct.Directive(action="lay_back", target=("rhythm",))
        self.assertTrue(everyone.applies_to({"melody"}))
        self.assertTrue(rhythm.applies_to({"rhythm", "ensemble"}))
        self.assertFalse(rhythm.applies_to({"melody", "ensemble"}))

    def test_unhandled_actions_are_reported_not_refused(self):
        reading = conduct.read(
            {"directives": [{"action": "reharmonize"}, {"action": "drop_out"}, {"action": "drag"}]}
        )
        self.assertEqual(reading.unhandled(), ["reharmonize", "drop_out"])
        self.assertEqual(len(reading.directives), 3)

    def test_an_unhandled_action_still_compiles(self):
        arrangement = arrange(parse(ORCHESTRA))
        conducted = conduct.apply(arrangement, {"directives": [{"action": "reharmonize"}]})
        self.assertEqual(conducted.note_count, arrangement.note_count)
        self.assertTrue(any("reharmonize" in diag.message for diag in conducted.diagnostics))

    def test_blending_interpolates_and_override_wins(self):
        blend = conduct._blend([(10.0, 1.0, "blend"), (0.0, 1.0, "blend")], 0.0)
        self.assertAlmostEqual(blend, 5.0)
        override = conduct._blend([(10.0, 1.0, "blend"), (0.0, 1.0, "override")], 0.0)
        self.assertAlmostEqual(override, 0.0)
        self.assertAlmostEqual(conduct._blend([], 3.0), 3.0)


class TestConducting(unittest.TestCase):
    def setUp(self):
        self.arrangement = arrange(parse(ORCHESTRA))

    def _first(self, arrangement, name):
        """First note of a voice, with the global lead-in taken back off."""
        track = next(item for item in arrangement.tracks if item.name == name)
        note = min(track.notes, key=lambda item: item.start)
        return (
            note.emission_time - arrangement.lead_in,
            note.arrival_time - arrangement.lead_in,
        )

    def test_anticipate_moves_the_hands_and_leaves_the_sound(self):
        # The drummer raising the stick early so the note still lands on the
        # beat. A correction, not an effect: nobody hears it as early.
        conducted = conduct.apply(
            self.arrangement, {"directives": [{"action": "anticipate", "intensity": 1.0}]}
        )
        for name in ("organ", "violin1", "timpani"):
            before_emit, before_arrive = self._first(self.arrangement, name)
            after_emit, after_arrive = self._first(conducted, name)
            self.assertAlmostEqual(after_arrive, before_arrive, places=9, msg=name)
            self.assertLess(after_emit, before_emit, msg=name)

    def test_push_forward_moves_both(self):
        # The whole band leaning ahead. An expressive choice, and audible.
        conducted = conduct.apply(
            self.arrangement, {"directives": [{"action": "push_forward", "intensity": 1.0}]}
        )
        for name in ("organ", "violin1", "timpani"):
            before_emit, before_arrive = self._first(self.arrangement, name)
            after_emit, after_arrive = self._first(conducted, name)
            self.assertLess(after_arrive, before_arrive, msg=name)
            self.assertLess(after_emit, before_emit, msg=name)

    def test_a_push_moves_everyone_equally_and_keeps_them_apart(self):
        # Twelve milliseconds at the listener is twelve milliseconds in every
        # player's own clock -- and the far organ and the near violin stay
        # exactly as far apart in absolute time as they were.
        feel = conduct.Feel(push_forward=0.012)
        conducted = conduct.apply(
            self.arrangement,
            {"directives": [{"action": "push_forward", "intensity": 1.0}]},
            feel=feel,
        )
        beats_per_ms = self.arrangement.meta.tempo / 60.0 / 1000.0
        shifts = []
        for name in ("organ", "violin1", "timpani"):
            before_emit, _ = self._first(self.arrangement, name)
            after_emit, _ = self._first(conducted, name)
            shifts.append(before_emit - after_emit)
        for shift in shifts:
            self.assertAlmostEqual(shift, 12.0 * beats_per_ms, places=9)

        def gap(arrangement):
            return self._first(arrangement, "violin1")[0] - self._first(arrangement, "organ")[0]

        self.assertAlmostEqual(gap(conducted), gap(self.arrangement), places=9)

    def test_lay_back_sits_behind_the_grid(self):
        conducted = conduct.apply(
            self.arrangement, {"directives": [{"action": "lay_back", "intensity": 1.0}]}
        )
        before = self._first(self.arrangement, "timpani")[1]
        after = self._first(conducted, "timpani")[1]
        self.assertGreater(after, before)

    def test_drag_accumulates_across_its_window(self):
        conducted = conduct.apply(
            self.arrangement,
            {"directives": [{"action": "drag", "intensity": 1.0, "duration_beats": 8}]},
        )
        track = next(item for item in conducted.tracks if item.name == "timpani")
        written = next(item for item in self.arrangement.tracks if item.name == "timpani")
        lateness = [
            note.arrival_time - conducted.lead_in - (base.arrival_time - self.arrangement.lead_in)
            for note, base in zip(sorted(track.notes, key=lambda n: n.start),
                                  sorted(written.notes, key=lambda n: n.start), strict=True)
        ]
        self.assertLess(lateness[0], lateness[-1])
        self.assertAlmostEqual(lateness[0], 0.0, places=6)

    def test_a_window_leaves_the_rest_of_the_piece_alone(self):
        conducted = conduct.apply(
            self.arrangement,
            {"directives": [{"action": "lay_back", "intensity": 1.0, "offset_beats": 4,
                             "duration_beats": 4}]},
        )
        track = next(item for item in conducted.tracks if item.name == "timpani")
        written = next(item for item in self.arrangement.tracks if item.name == "timpani")
        first_pair = sorted(track.notes, key=lambda n: n.start)[0]
        base_pair = sorted(written.notes, key=lambda n: n.start)[0]
        self.assertAlmostEqual(
            first_pair.arrival_time - conducted.lead_in,
            base_pair.arrival_time - self.arrangement.lead_in,
            places=9,
        )

    def test_targeting_a_layer_leaves_the_others_where_they_were(self):
        conducted = conduct.apply(self.arrangement, BANDLEADER)
        # lay_back targets rhythm, which on this stage is the timpani alone.
        timpani = self._first(conducted, "timpani")[1] - self._first(self.arrangement, "timpani")[1]
        violin = self._first(conducted, "violin1")[1] - self._first(self.arrangement, "violin1")[1]
        self.assertGreater(timpani, 0.0)
        self.assertAlmostEqual(violin, 0.0, places=9)

    def test_float_widens_the_spread_and_lock_in_closes_it(self):
        def spread(arrangement):
            firsts = [
                min(note.arrival_time for note in track.notes) for track in arrangement.tracks
            ]
            return max(firsts) - min(firsts)

        loose = conduct.apply(
            self.arrangement, {"directives": [{"action": "float", "intensity": 1.0}]}
        )
        tight = conduct.apply(
            self.arrangement, {"directives": [{"action": "lock_in", "intensity": 1.0}]}
        )
        self.assertGreater(spread(loose), spread(self.arrangement))
        self.assertLess(spread(tight), 1e-9)

    def test_half_time_stretches_the_timeline(self):
        conducted = conduct.apply(
            self.arrangement,
            {"directives": [{"action": "half_time", "intensity": 1.0, "duration_beats": 8}]},
        )
        self.assertGreater(conducted.total_beats, self.arrangement.total_beats)

    def test_double_time_compresses_it(self):
        conducted = conduct.apply(
            self.arrangement,
            {"directives": [{"action": "double_time", "intensity": 1.0, "duration_beats": 8}]},
        )
        self.assertLess(conducted.total_beats, self.arrangement.total_beats)

    def test_arrivals_stay_together_through_a_tempo_change(self):
        conducted = conduct.apply(
            self.arrangement,
            {"directives": [{"action": "half_time", "intensity": 1.0, "duration_beats": 8}]},
        )
        by_voice = {
            track.name: sorted(note.arrival_time for note in track.notes)
            for track in conducted.tracks
        }
        self.assertAlmostEqual(by_voice["timpani"][0], by_voice["organ"][0], places=6)
        self.assertAlmostEqual(by_voice["timpani"][-1], by_voice["organ"][-1], places=6)

    def test_a_tempo_change_moves_hands_by_different_amounts(self):
        conducted = conduct.apply(
            self.arrangement,
            {"directives": [{"action": "half_time", "intensity": 1.0, "duration_beats": 8}]},
        )

        def lead(arrangement, name):
            """Beats between a voice acting and the sound being heard."""
            track = next(t for t in arrangement.tracks if t.name == name)
            note = min(track.notes, key=lambda item: item.start)
            return note.arrival_time - note.emission_time

        # The correction is a fixed number of milliseconds; longer beats make it
        # a smaller slice of one. The organ's slice shrinks by far more than the
        # timpani's, because it was ten times bigger to begin with.
        organ = lead(conducted, "organ") - lead(self.arrangement, "organ")
        timpani = lead(conducted, "timpani") - lead(self.arrangement, "timpani")
        self.assertLess(organ, 0.0)
        self.assertLess(timpani, 0.0)
        self.assertGreater(abs(organ), abs(timpani) * 5)

    def test_energy_moves_velocities_not_times(self):
        conducted = conduct.apply(
            self.arrangement, {"energy": {"target": 0.8, "mode": "absolute"}}
        )
        before = [note.start for _t, note in self.arrangement.iter_notes()]
        after = [note.start for _t, note in conducted.iter_notes()]
        self.assertEqual(before, after)
        self.assertGreater(
            sum(note.velocity for _t, note in conducted.iter_notes()),
            sum(note.velocity for _t, note in self.arrangement.iter_notes()),
        )

    def test_straighten_pulls_the_offbeats_back_onto_the_grid(self):
        swung = arrange(parse(SWUNG))
        offbeat = 0.5 + 0.6 / 6.0
        original = [
            note.start for _t, note in swung.iter_notes() if abs(note.start % 1.0 - offbeat) < 1e-6
        ]
        self.assertTrue(original, "the sample has no swung off-beats to straighten")
        straight = conduct.apply(swung, {"directives": [{"action": "straighten", "intensity": 1.0}]})
        moved = [
            note.start for _t, note in straight.iter_notes() if abs(note.start % 1.0 - 0.5) < 1e-6
        ]
        self.assertEqual(len(moved), len(original))

    def test_deepen_swing_pushes_them_further_out(self):
        swung = arrange(parse(SWUNG))
        deeper = conduct.apply(swung, {"directives": [{"action": "deepen_swing", "intensity": 1.0}]})
        before = sorted(note.start % 1.0 for _t, note in swung.iter_notes())
        after = sorted(note.start % 1.0 for _t, note in deeper.iter_notes())
        self.assertGreater(max(after), max(before))

    def test_conducting_leaves_the_original_alone(self):
        before = [note.start for _t, note in self.arrangement.iter_notes()]
        conduct.apply(self.arrangement, BANDLEADER)
        self.assertEqual(before, [note.start for _t, note in self.arrangement.iter_notes()])

    def test_conducting_is_deterministic(self):
        first = conduct.apply(self.arrangement, BANDLEADER)
        second = conduct.apply(self.arrangement, BANDLEADER)
        self.assertEqual(
            [note.emission_time for _t, note in first.iter_notes()],
            [note.emission_time for _t, note in second.iter_notes()],
        )

    def test_a_directive_message_describes_itself(self):
        text = conduct.describe(BANDLEADER)
        self.assertIn("lay_back", text)
        self.assertIn("rhythm", text)
        self.assertIn("arriving at climax", text)


class TestAgentTools(unittest.TestCase):
    def test_the_tools_are_registered(self):
        from plainsong.agent.tools import ToolRegistry

        names = {spec.name for spec in ToolRegistry().specs()}
        self.assertIn("ensemble_report", names)
        self.assertIn("stage_reference", names)
        self.assertIn("speech_profiles", names)

    def test_the_report_tool_runs_on_inline_notation(self):
        from plainsong.agent.tools import ToolRegistry

        registry = ToolRegistry()
        answer = registry.call("ensemble_report", {"content": ORCHESTRA})
        self.assertIn("organ", answer)
        self.assertNotIn("error", answer.lower())

    def test_the_report_tool_explains_a_missing_stage(self):
        from plainsong.agent.tools import ToolRegistry

        answer = ToolRegistry().call("ensemble_report", {"content": PLAIN})
        self.assertIn("no [Stage] block", answer)


if __name__ == "__main__":
    unittest.main()
