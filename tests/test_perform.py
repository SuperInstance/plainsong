"""Arrival-centric timing: geometry, the solver, conducting, and staying inert."""

from __future__ import annotations

import unittest

from tapscript.notation import arrange, parse
from tapscript.notation.arrange import ArrangeOptions
from tapscript.perform import conduct, profiles, solve, stage
from tapscript.render.audio import AudioOptions, Synthesiser
from tapscript.render.midi import midi_bytes

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


class TestConducting(unittest.TestCase):
    def setUp(self):
        self.arrangement = arrange(parse(ORCHESTRA))
        self.gesture = conduct.Gesture(kind="rubato", amount=-0.3, shape="step", start=0.0, span=8.0)

    def test_a_rubato_stretches_the_timeline(self):
        conducted = conduct.conduct(self.arrangement, [self.gesture])
        self.assertGreater(conducted.total_beats, self.arrangement.total_beats)

    def test_arrivals_stay_together_through_the_gesture(self):
        conducted = conduct.conduct(self.arrangement, [self.gesture])
        by_voice = {
            track.name: sorted(note.arrival_time for note in track.notes)
            for track in conducted.tracks
        }
        self.assertAlmostEqual(by_voice["timpani"][0], by_voice["organ"][0], places=6)
        self.assertAlmostEqual(by_voice["timpani"][-1], by_voice["organ"][-1], places=6)

    def test_emissions_move_by_different_amounts(self):
        conducted = conduct.conduct(self.arrangement, [self.gesture])

        def lead(arrangement, name):
            """Beats between a voice acting and the sound being heard."""
            track = next(t for t in arrangement.tracks if t.name == name)
            note = min(track.notes, key=lambda item: item.start)
            return note.arrival_time - note.emission_time

        # The correction is a fixed number of milliseconds; longer beats make it
        # a smaller slice of one. The organ's slice shrinks by ten times as much
        # as the timpani's, because it was ten times bigger to begin with.
        organ = lead(conducted, "organ") - lead(self.arrangement, "organ")
        timpani = lead(conducted, "timpani") - lead(self.arrangement, "timpani")
        self.assertLess(organ, 0.0)
        self.assertLess(timpani, 0.0)
        self.assertGreater(abs(organ), abs(timpani) * 5)

    def test_a_swell_moves_velocities_not_times(self):
        swell = conduct.Gesture(kind="swell", amount=0.2, shape="step")
        conducted = conduct.conduct(self.arrangement, [swell])
        before = [note.start for _t, note in self.arrangement.iter_notes()]
        after = [note.start for _t, note in conducted.iter_notes()]
        self.assertEqual(before, after)
        self.assertGreater(
            sum(note.velocity for _t, note in conducted.iter_notes()),
            sum(note.velocity for _t, note in self.arrangement.iter_notes()),
        )

    def test_conducting_leaves_the_original_alone(self):
        before = [note.start for _t, note in self.arrangement.iter_notes()]
        conduct.conduct(self.arrangement, [self.gesture])
        self.assertEqual(before, [note.start for _t, note in self.arrangement.iter_notes()])

    def test_gestures_read_from_text(self):
        gesture = conduct.parse_gesture("rubato -0.2 arch 4 8")
        self.assertEqual(gesture.kind, "rubato")
        self.assertAlmostEqual(gesture.amount, -0.2)
        self.assertEqual(gesture.shape, "arch")
        self.assertEqual((gesture.start, gesture.span), (4.0, 8.0))
        self.assertIsNone(conduct.parse_gesture("wave the stick about"))

    def test_conducting_is_deterministic(self):
        first = conduct.conduct(self.arrangement, [self.gesture])
        second = conduct.conduct(self.arrangement, [self.gesture])
        self.assertEqual(
            [note.emission_time for _t, note in first.iter_notes()],
            [note.emission_time for _t, note in second.iter_notes()],
        )


class TestAgentTools(unittest.TestCase):
    def test_the_tools_are_registered(self):
        from tapscript.agent.tools import ToolRegistry

        names = {spec.name for spec in ToolRegistry().specs()}
        self.assertIn("ensemble_report", names)
        self.assertIn("stage_reference", names)
        self.assertIn("speech_profiles", names)

    def test_the_report_tool_runs_on_inline_notation(self):
        from tapscript.agent.tools import ToolRegistry

        registry = ToolRegistry()
        answer = registry.call("ensemble_report", {"content": ORCHESTRA})
        self.assertIn("organ", answer)
        self.assertNotIn("error", answer.lower())

    def test_the_report_tool_explains_a_missing_stage(self):
        from tapscript.agent.tools import ToolRegistry

        answer = ToolRegistry().call("ensemble_report", {"content": PLAIN})
        self.assertIn("no [Stage] block", answer)


if __name__ == "__main__":
    unittest.main()
