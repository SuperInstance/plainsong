"""Tests for counterpoint_analyzer — ported from the Rust test suite in
counterpoint.rs."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from counterpoint_analyzer import (
    CounterpointAnalyzer,
    Direction,
    MotionType,
    RoomSnapshot,
)


def test_contrary_motion():
    analyzer = CounterpointAnalyzer(100)
    # Room A goes up, Room B goes down
    analyzer.record([RoomSnapshot("engine", 50.0), RoomSnapshot("bilge", 30.0)])
    analyzer.record([RoomSnapshot("engine", 60.0), RoomSnapshot("bilge", 20.0)])
    assert analyzer.classify_motion("engine", "bilge") is MotionType.CONTRARY


def test_parallel_motion():
    analyzer = CounterpointAnalyzer(100)
    analyzer.record([RoomSnapshot("engine", 50.0), RoomSnapshot("bilge", 30.0)])
    analyzer.record([RoomSnapshot("engine", 60.0), RoomSnapshot("bilge", 40.0)])
    assert analyzer.classify_motion("engine", "bilge") is MotionType.PARALLEL


def test_oblique_motion():
    analyzer = CounterpointAnalyzer(100)
    analyzer.record([RoomSnapshot("engine", 50.0), RoomSnapshot("bilge", 30.0)])
    analyzer.record([RoomSnapshot("engine", 50.0), RoomSnapshot("bilge", 40.0)])
    assert analyzer.classify_motion("engine", "bilge") is MotionType.OBLIQUE


def test_motion_score_fishing_boat():
    analyzer = CounterpointAnalyzer(100)
    # Engine heating up while bilge level goes down (contrary — productive)
    for i in range(50):
        analyzer.record([RoomSnapshot("engine", 50.0 + i), RoomSnapshot("bilge", 30.0 - i * 0.5)])
    score = analyzer.motion_score("engine", "bilge")
    assert score.contrary_ratio > 0.9
    assert score.quality > 0.7


def test_productive_interaction_high_score():
    analyzer = CounterpointAnalyzer(100)
    # Mix of contrary and oblique — productive
    for i in range(30):
        engine_val = 50.0 if i % 3 == 0 else 50.0 + math.sin(i * 0.5) * 10.0
        bilge_val = 30.0 + i if i % 3 == 0 else 30.0 - math.cos(i * 0.3) * 5.0
        analyzer.record([RoomSnapshot("engine", engine_val), RoomSnapshot("bilge", bilge_val)])
    score = analyzer.motion_score("engine", "bilge")
    assert score.quality > 0.3


def test_direction_static():
    snapshots = [RoomSnapshot("engine", 50.0), RoomSnapshot("engine", 60.0)]
    assert CounterpointAnalyzer.direction(snapshots, "engine") is Direction.UP
    assert CounterpointAnalyzer.direction(snapshots, "ghost") is None


def test_classify_motion_insufficient_history():
    analyzer = CounterpointAnalyzer(100)
    assert analyzer.classify_motion("engine", "bilge") is None
    analyzer.record([RoomSnapshot("engine", 50.0), RoomSnapshot("bilge", 30.0)])
    assert analyzer.classify_motion("engine", "bilge") is None


def test_classify_motion_missing_room():
    analyzer = CounterpointAnalyzer(100)
    analyzer.record([RoomSnapshot("engine", 50.0)])
    analyzer.record([RoomSnapshot("engine", 60.0)])
    assert analyzer.classify_motion("engine", "bilge") is None


def test_motion_score_empty_history():
    analyzer = CounterpointAnalyzer(100)
    score = analyzer.motion_score("engine", "bilge")
    assert score.contrary_ratio == 0.0
    assert score.parallel_ratio == 0.0
    assert score.oblique_ratio == 1.0
    assert score.quality == 0.5


def test_parallel_motion_low_quality():
    analyzer = CounterpointAnalyzer(100)
    for i in range(20):
        analyzer.record([RoomSnapshot("engine", 50.0 + i), RoomSnapshot("bilge", 30.0 + i)])
    score = analyzer.motion_score("engine", "bilge")
    assert score.parallel_ratio == 1.0
    assert score.quality == 0.2


def test_history_eviction():
    analyzer = CounterpointAnalyzer(5)
    for i in range(10):
        analyzer.record([RoomSnapshot("engine", float(i))])
    assert analyzer.history_len() == 5
