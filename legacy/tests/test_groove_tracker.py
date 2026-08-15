"""Tests for groove_tracker — ported from the Rust test suite in groove.rs."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from groove_tracker import GrooveTracker, TickEvent


def test_perfect_sync():
    tracker = GrooveTracker(100, 0.8)
    for i in range(50):
        phase = i / 50.0
        tracker.record_perfect_tick("engine", phase, float(i))
    assert tracker.groove() > 0.99


def test_one_room_late():
    tracker = GrooveTracker(100, 0.8)
    # Perfect ticks for most rooms
    for i in range(40):
        phase = i / 50.0
        tracker.record_perfect_tick("engine", phase, float(i))
        tracker.record_perfect_tick("backdeck", phase, float(i))
    # One room ticks late
    for i in range(40, 50):
        phase = i / 50.0
        tracker.record_perfect_tick("engine", phase, float(i))
        tracker.record_tick(
            TickEvent(
                room_name="backdeck",
                expected_phase=phase,
                actual_phase=phase + 0.3,  # 30% late
                timestamp=float(i),
            )
        )
    assert tracker.groove() < 0.9


def test_groove_recovers():
    tracker = GrooveTracker(20, 0.8)
    # Add some bad ticks
    for i in range(10):
        tracker.record_tick(
            TickEvent(
                room_name="engine",
                expected_phase=i / 10.0,
                actual_phase=i / 10.0 + 0.2,
                timestamp=float(i),
            )
        )
    assert tracker.groove() < 0.9
    # Now recover with perfect ticks
    for i in range(20):
        phase = i / 20.0
        tracker.record_perfect_tick("engine", phase, float(i) + 10.0)
    assert tracker.groove() > 0.9


def test_threshold_detection():
    tracker = GrooveTracker(50, 0.8)
    # Perfect ticks — no correction needed
    for i in range(30):
        tracker.record_perfect_tick("engine", i / 30.0, float(i))
    assert not tracker.needs_correction()
    # Add bad ticks
    for i in range(30):
        tracker.record_tick(
            TickEvent(
                room_name="engine",
                expected_phase=i / 30.0,
                actual_phase=i / 30.0 + 0.15,
                timestamp=float(i) + 30.0,
            )
        )
    assert tracker.needs_correction()


def test_window_size_eviction():
    tracker = GrooveTracker(5, 0.8)
    for i in range(10):
        tracker.record_perfect_tick("engine", i / 10.0, float(i))
    assert tracker.event_count() == 5


def test_reset():
    tracker = GrooveTracker(10, 0.8)
    for i in range(10):
        tracker.record_tick(
            TickEvent(
                room_name="engine",
                expected_phase=i / 10.0,
                actual_phase=i / 10.0 + 0.2,
                timestamp=float(i),
            )
        )
    assert tracker.groove() < 0.9
    tracker.reset()
    assert tracker.event_count() == 0
    assert tracker.groove() == 1.0


def test_phase_wrapping():
    # An error of 0.9 should wrap to 0.1, not count as nearly-total chaos.
    tracker = GrooveTracker(10, 0.8)
    tracker.record_tick(
        TickEvent(room_name="engine", expected_phase=0.05, actual_phase=0.95, timestamp=0.0)
    )
    assert tracker.groove() == pytest.approx(math.exp(-0.1 * 20.0))


def test_threshold_getter():
    tracker = GrooveTracker(10, 0.75)
    assert tracker.threshold == 0.75


def test_empty_tracker_is_perfect():
    tracker = GrooveTracker(10, 0.8)
    assert tracker.groove() == 1.0
    assert not tracker.needs_correction()
