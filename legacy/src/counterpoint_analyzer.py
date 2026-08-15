"""Counterpoint analysis — detect productive vs wasteful room interactions.

Inspired by species counterpoint in music theory:
- **Contrary motion**: one room's value goes up while another goes down (productive)
- **Parallel motion**: both go same direction (potentially wasteful/redundant)
- **Oblique motion**: one stable, other changing (normal operation)

The MotionScore quantifies the quality of room coordination.

Ported from plato-music-sync/src/counterpoint.rs.
"""

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Optional

_EPSILON = 1e-6


class Direction(Enum):
    """Direction of a room's value change."""

    UP = "up"
    DOWN = "down"
    STABLE = "stable"


class MotionType(Enum):
    """Type of motion between two rooms."""

    # Both rooms move in opposite directions — productive interaction.
    CONTRARY = "contrary"
    # Both rooms move in the same direction — potentially redundant.
    PARALLEL = "parallel"
    # One room stable, other changing — normal operation.
    OBLIQUE = "oblique"


@dataclass
class RoomSnapshot:
    """A snapshot of a room's value at a point in time."""

    name: str
    value: float


@dataclass
class MotionScore:
    """Score quantifying the quality of room coordination."""

    # Fraction of contrary motion (productive).
    contrary_ratio: float
    # Fraction of parallel motion (potentially wasteful).
    parallel_ratio: float
    # Fraction of oblique motion (neutral).
    oblique_ratio: float
    # Overall quality: 0.0 (bad) to 1.0 (excellent).
    quality: float


def _classify_pair(dir_a: Direction, dir_b: Direction) -> MotionType:
    if (dir_a, dir_b) in (
        (Direction.UP, Direction.DOWN),
        (Direction.DOWN, Direction.UP),
    ):
        return MotionType.CONTRARY
    if (dir_a, dir_b) in (
        (Direction.UP, Direction.UP),
        (Direction.DOWN, Direction.DOWN),
    ):
        return MotionType.PARALLEL
    return MotionType.OBLIQUE


def _diff_direction(diff: float) -> Direction:
    if diff > _EPSILON:
        return Direction.UP
    if diff < -_EPSILON:
        return Direction.DOWN
    return Direction.STABLE


class CounterpointAnalyzer:
    """Detects motion patterns between room pairs."""

    def __init__(self, max_history: int) -> None:
        self._history: deque = deque(maxlen=max_history)
        self.max_history = max_history

    def record(self, snapshot: list) -> None:
        """Record a snapshot of all rooms at a point in time."""
        self._history.append(list(snapshot))

    @staticmethod
    def direction(snapshots: list, room_name: str) -> Optional[Direction]:
        """Determine the direction of change for a room between two snapshots."""
        values = [s.value for s in snapshots if s.name == room_name]
        if len(values) < 2:
            return None
        return _diff_direction(values[-1] - values[-2])

    @staticmethod
    def _direction_pair(prev: list, curr: list, room: str) -> Optional[Direction]:
        prev_val = next((s.value for s in prev if s.name == room), None)
        curr_val = next((s.value for s in curr if s.name == room), None)
        if prev_val is None or curr_val is None:
            return None
        return _diff_direction(curr_val - prev_val)

    def classify_motion(self, room_a: str, room_b: str) -> Optional[MotionType]:
        """Classify the motion type between two rooms."""
        if len(self._history) < 2:
            return None
        latest = self._history[-1]
        prev = self._history[-2]

        dir_a = self._direction_pair(prev, latest, room_a)
        if dir_a is None:
            return None
        dir_b = self._direction_pair(prev, latest, room_b)
        if dir_b is None:
            return None
        return _classify_pair(dir_a, dir_b)

    def motion_score(self, room_a: str, room_b: str) -> MotionScore:
        """Compute the MotionScore for a pair of rooms over the entire history."""
        contrary = 0
        parallel = 0
        oblique = 0

        history = list(self._history)
        for i in range(1, len(history)):
            prev = history[i - 1]
            curr = history[i]

            dir_a = self._direction_pair(prev, curr, room_a)
            dir_b = self._direction_pair(prev, curr, room_b)
            if dir_a is None or dir_b is None:
                continue
            motion = _classify_pair(dir_a, dir_b)
            if motion is MotionType.CONTRARY:
                contrary += 1
            elif motion is MotionType.PARALLEL:
                parallel += 1
            else:
                oblique += 1

        total = contrary + parallel + oblique
        if total == 0:
            return MotionScore(
                contrary_ratio=0.0,
                parallel_ratio=0.0,
                oblique_ratio=1.0,
                quality=0.5,
            )

        contrary_ratio = contrary / total
        parallel_ratio = parallel / total
        oblique_ratio = oblique / total

        # Quality: contrary is good, oblique is neutral, parallel is bad
        quality = contrary_ratio * 1.0 + oblique_ratio * 0.5 + parallel_ratio * 0.2
        quality = min(1.0, max(0.0, quality))

        return MotionScore(
            contrary_ratio=contrary_ratio,
            parallel_ratio=parallel_ratio,
            oblique_ratio=oblique_ratio,
            quality=quality,
        )

    def history_len(self) -> int:
        """Get the history length."""
        return len(self._history)
