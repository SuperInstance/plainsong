"""Groove tracking — measuring how "in the groove" the fleet is.

Groove = alignment of ticks across rooms. Each room's tick should land on the
expected phase within the master cycle. The groove score ranges from 0.0 (chaos)
to 1.0 (perfect sync). When groove drops below a threshold, sync correction is needed.

Ported from plato-music-sync/src/groove.rs.
"""

import math
from collections import deque
from dataclasses import dataclass


@dataclass
class TickEvent:
    """A tick event from a room."""

    room_name: str
    expected_phase: float
    actual_phase: float
    timestamp: float


class GrooveTracker:
    """Measures fleet alignment over time.

    Keeps a ring buffer of recent tick events and derives a groove score
    from their average phase error.
    """

    def __init__(self, window_size: int, threshold: float) -> None:
        self._events: deque[TickEvent] = deque(maxlen=window_size)
        self.window_size = window_size
        self._threshold = threshold
        self._current_groove = 1.0

    def record_tick(self, event: TickEvent) -> None:
        """Record a tick event and update the groove score."""
        self._events.append(event)
        self._recompute_groove()

    def record_perfect_tick(self, room_name: str, phase: float, timestamp: float) -> None:
        """Record a perfect tick (no phase error)."""
        self.record_tick(
            TickEvent(
                room_name=room_name,
                expected_phase=phase,
                actual_phase=phase,
                timestamp=timestamp,
            )
        )

    def _recompute_groove(self) -> None:
        """Recompute the groove score from recent events."""
        if not self._events:
            self._current_groove = 1.0
            return
        total_error = 0.0
        for e in self._events:
            err = abs(e.expected_phase - e.actual_phase)
            # Phase wrapping: minimum of err and 1-err
            total_error += min(err, 1.0 - err)
        avg_error = total_error / len(self._events)
        # Groove: 1.0 when error is 0, approaches 0.0 as error increases
        # Using exponential decay: groove = exp(-error * 20)
        self._current_groove = min(1.0, max(0.0, math.exp(-avg_error * 20.0)))

    def groove(self) -> float:
        """Get the current groove score."""
        return self._current_groove

    def needs_correction(self) -> bool:
        """Check if groove is below threshold (sync correction needed)."""
        return self._current_groove < self._threshold

    @property
    def threshold(self) -> float:
        """Get the threshold."""
        return self._threshold

    def event_count(self) -> int:
        """Number of tracked events."""
        return len(self._events)

    def reset(self) -> None:
        """Reset the tracker."""
        self._events.clear()
        self._current_groove = 1.0
