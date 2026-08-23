"""The neutral core must answer exactly what the music solver answers.

An extraction is only safe if it is inert, and "I read both and they look the
same" is not evidence -- this repository has paid for that lesson more than
once. So this drives `plainsong.perform.solve` and `coordinate` with the same
inputs and requires bit-identical results, over a grid of cases chosen to hit
the terms that could plausibly diverge: alignment off, intent scaled, an
observer away from the reference point, and a lead that must move the action
without moving the effect.

If this passes, `coordinate.solve_one` can replace the equation in
`VoiceTiming.offsets` without moving a single note.

Run: python3 -m unittest discover -s coordinate -t .
"""

from __future__ import annotations

import sys
import unittest
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coordinate import Latency, Participant, Shaping, delay_for, divide, index_at, schedule
from plainsong.perform.solve import Shaping as MusicShaping
from plainsong.perform.solve import VoiceTiming

# Deliberately awkward numbers. Round ones hide ordering differences, because
# floating-point addition is not associative and 0.5 + 0.25 is exact.
ACTUATION = (0.0, 0.0031, 0.017, 0.1234567)
BIAS = (0.0, -0.0042, 0.0091)
INTENT = (0.0, 0.0237, -0.0158)
REFERENCE = (0.0, 0.0291, 0.1013)
OBSERVED = (0.0, 0.0291, 0.0044, 0.2007)

SHAPINGS = (
    (0.0, 0.0, 1.0, 1.0),      # neutral
    (0.0, 0.0, 0.0, 1.0),      # alignment off -- no correction applied
    (0.0, 0.0, 0.35, 1.0),     # partial trust
    (0.021, 0.0, 1.0, 1.0),    # the whole group leaning
    (0.0, 0.013, 1.0, 1.0),    # lead: moves the action, not the effect
    (0.0, 0.013, 0.5, 0.0),    # lead under partial alignment, intent discarded
    (-0.007, 0.004, 0.8, 2.0), # everything at once
)


def music_offsets(actuation, bias, intent, reference, observed, shaping, compensate):
    timing = VoiceTiming(
        name="v",
        position=(0.0, 0.0),
        profile="test",
        speech=actuation,
        p_center=bias,
        feel=intent,
        reference_distance=0.0,
        reference_propagation=reference,
        observed_distance=0.0,
        observed_propagation=observed,
        emission_offset=0.0,
        arrival_offset=0.0,
    )
    return timing.offsets(
        MusicShaping(
            feel=shaping[0], preparation=shaping[1], alignment=shaping[2], feel_scale=shaping[3]
        ),
        compensate,
    )


def neutral_offsets(actuation, bias, intent, reference, observed, shaping, compensate):
    participant = Participant(
        name="v",
        latency=Latency(name="test", actuation=actuation, bias=bias),
        intent=intent,
        reference_delay=reference,
        observed_delay=observed,
    )
    result = schedule(
        [participant],
        Shaping(
            intent_shift=shaping[0], lead=shaping[1], alignment=shaping[2], intent_scale=shaping[3]
        ),
        compensate,
    )
    timing = result.timings["v"]
    return timing.act_at, timing.effect_at


class TestTheExtractionIsInert(unittest.TestCase):
    def test_every_combination_agrees_to_the_bit(self):
        cases = 0
        for actuation, bias, intent, reference, observed, shaping, compensate in product(
            ACTUATION, BIAS, INTENT, REFERENCE, OBSERVED, SHAPINGS, (True, False)
        ):
            args = (actuation, bias, intent, reference, observed, shaping, compensate)
            with self.subTest(args=args):
                # assertEqual, not assertAlmostEqual. A reordered sum is a
                # different implementation even when it is close, and close is
                # what accumulates.
                self.assertEqual(music_offsets(*args), neutral_offsets(*args))
            cases += 1
        self.assertGreater(cases, 3000, "the grid collapsed; this proves nothing")


class TestTheClaimsThatMakeItGeneral(unittest.TestCase):
    """The properties the docstring asserts. If these are not true, the
    generalisation is decoration."""

    def test_at_the_reference_point_the_effect_lands_where_written(self):
        p = Participant(
            "a", Latency(actuation=0.02, bias=0.005), reference_delay=0.03, observed_delay=0.03
        )
        timing = schedule([p]).timings["a"]
        self.assertAlmostEqual(timing.effect_at, 0.0, places=12)
        self.assertLess(timing.act_at, 0.0, "the participant must act early")

    def test_away_from_the_reference_point_it_does_not(self):
        p = Participant(
            "a", Latency(actuation=0.02, bias=0.005), reference_delay=0.03, observed_delay=0.09
        )
        timing = schedule([p]).timings["a"]
        self.assertAlmostEqual(timing.effect_at, 0.06, places=12)

    def test_spread_is_zero_at_the_tuning_point_and_not_elsewhere(self):
        """The claim the whole model rests on: a group compensated for one
        observer lands together *there* and smeared anywhere else."""
        near = Participant("near", Latency(actuation=0.01), reference_delay=0.01, observed_delay=0.01)
        far = Participant("far", Latency(actuation=0.03), reference_delay=0.08, observed_delay=0.08)
        self.assertAlmostEqual(schedule([near, far]).spread, 0.0, places=12)

        moved = replace_observed(near, 0.05), replace_observed(far, 0.02)
        self.assertGreater(schedule(list(moved)).spread, 0.0)

    def test_intent_survives_compensation_and_lead_does_not(self):
        """The distinction that must never be merged: one is an intention, the
        other a correction, and they are the same shape in the arithmetic."""
        base = Participant("a", Latency(actuation=0.02), reference_delay=0.01, observed_delay=0.01)

        intended = replace_intent(base, 0.05)
        self.assertAlmostEqual(schedule([intended]).timings["a"].effect_at, 0.05, places=12)

        led = schedule([base], Shaping(lead=0.05)).timings["a"]
        self.assertAlmostEqual(led.effect_at, 0.0, places=12)
        plain = schedule([base]).timings["a"]
        self.assertAlmostEqual(led.act_at, plain.act_at - 0.05, places=12)

    def test_without_compensation_nothing_is_solved_away(self):
        p = Participant("a", Latency(actuation=0.02, bias=0.01), observed_delay=0.03)
        timing = schedule([p], compensate=False).timings["a"]
        self.assertEqual(timing.act_at, 0.0)
        self.assertAlmostEqual(timing.effect_at, 0.06, places=12)


class TestIntervalDivision(unittest.TestCase):
    def test_contents_divide_the_interval(self):
        self.assertEqual(divide(4), [0.0, 0.25, 0.5, 0.75])
        self.assertEqual(len(divide(12)), 12)

    def test_nothing_spills_past_the_end(self):
        for count in range(1, 65):
            with self.subTest(count=count):
                self.assertLess(max(divide(count)), 1.0)

    def test_positions_are_computed_not_accumulated(self):
        """Accumulation drifts, and which divisors drift is not guessable.

        A twelfth added twelve times lands on exactly 1.0; a seventh added
        seven times lands on 0.9999999999999998, and a ninth overshoots. So
        "it worked when I tried it" is worth nothing here -- the ones that
        drift are found by measuring, which is the argument for computing
        every position from the start rather than walking a cursor.
        """
        drifted = []
        for count in range(2, 65):
            accumulated = 0.0
            for _ in range(count):
                accumulated += 1.0 / count
            if accumulated != 1.0:
                drifted.append(count)
        self.assertGreater(len(drifted), 20, "expected many divisors to drift")
        self.assertIn(7, drifted)
        self.assertNotIn(12, drifted)  # the intuitive example is the exact one

        # Computed positions never drift, whichever divisor it is.
        for count in drifted:
            with self.subTest(count=count):
                self.assertEqual(divide(count)[0], 0.0)
                self.assertLess(max(divide(count)), 1.0)
        self.assertEqual(divide(3, span=12.0)[2], 8.0)

    def test_a_boundary_lands_in_the_slot_it_belongs_to(self):
        """0.3 arrives from division as 0.29999999999999993; a bare floor puts
        it one slot low."""
        for count in (3, 5, 6, 7, 12, 13):
            for index, position in enumerate(divide(count)):
                with self.subTest(count=count, index=index):
                    self.assertEqual(index_at(position, count), index)


class TestMediumIsAParameter(unittest.TestCase):
    def test_sound_is_the_default_not_the_assumption(self):
        self.assertAlmostEqual(delay_for(343.2), 1.0, places=6)
        self.assertAlmostEqual(delay_for(1.0, speed=2.0), 0.5, places=12)

    def test_a_nonsense_medium_is_refused(self):
        with self.assertRaises(ValueError):
            delay_for(1.0, speed=0.0)


def replace_observed(participant: Participant, observed: float) -> Participant:
    from dataclasses import replace as _replace

    return _replace(participant, observed_delay=observed)


def replace_intent(participant: Participant, intent: float) -> Participant:
    from dataclasses import replace as _replace

    return _replace(participant, intent=intent)


if __name__ == "__main__":
    unittest.main()
