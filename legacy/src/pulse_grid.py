"""
PulseGrid — the temporal foundation for TapScript.

Based on tensor-midi's 12-pulse architecture and slackwater-tempo's BeatClock.
The grid is 96 PPQ (pulses per quarter note), same as standard MIDI.

The 3:4 polyrhythm architecture:
- ECN (4-pulse) fires on pulses 1, 4, 7, 10 — reflex actions
- DMN (3-pulse) fires on pulses 1, 5, 9 — creative actions  
- They converge on pulse 1 — the resolution (Chinese Remainder Theorem)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import random

PPQ = 96  # Pulses per quarter note (standard MIDI resolution)

@dataclass
class TimeSignature:
    numerator: int = 4
    denominator: int = 4
    
    @property
    def ticks_per_bar(self) -> int:
        """Total ticks in one bar at 96 PPQ."""
        return PPQ * self.numerator * (4 // self.denominator)

@dataclass  
class PulseGrid:
    """
    Converts between musical time (bar:beat:tick) and absolute PulseTick.
    
    All timing is on a 96 PPQ grid. The grid is the single source of truth
    for when events happen. Swing and humanization modify the grid position
    of individual events without changing the underlying tempo.
    """
    bpm: float = 120.0
    time_signature: TimeSignature = None
    
    def __post_init__(self):
        if self.time_signature is None:
            self.time_signature = TimeSignature()
    
    @property
    def ticks_per_beat(self) -> int:
        return PPQ
    
    @property 
    def ticks_per_bar(self) -> int:
        return self.time_signature.ticks_per_bar
    
    @property
    def seconds_per_tick(self) -> float:
        return 60.0 / (self.bpm * PPQ)
    
    def beat_tick(self, bar: int, beat: int, tick: int = 0) -> int:
        """Convert bar:beat:tick to absolute PulseTick."""
        return bar * self.ticks_per_bar + beat * PPQ + tick
    
    def from_tick(self, tick: int) -> tuple:
        """Convert absolute PulseTick back to (bar, beat, tick)."""
        bar = tick // self.ticks_per_bar
        remaining = tick % self.ticks_per_bar
        beat = remaining // PPQ
        sub_tick = remaining % PPQ
        return (bar, beat, sub_tick)
    
    def apply_swing(self, tick: int, swing_percent: float) -> int:
        """
        Apply swing to an off-beat tick.
        Swing pushes odd-numbered 8th notes later by a percentage.
        0% = straight, ~30% = triplet feel.
        """
        beat_position = tick % PPQ
        # Only swing 8th note off-beats (the "and" of each beat)
        if beat_position == PPQ // 2:  # On the off-beat
            push = int((PPQ // 2) * (swing_percent / 100.0))
            return tick + push
        return tick
    
    def humanize(self, tick: int, amount: int = 2, seed: Optional[int] = None) -> int:
        """
        Add subtle timing variation for human feel.
        amount = max ticks to deviate (±amount)
        seed = for reproducibility
        """
        rng = random.Random(seed) if seed is not None else random
        offset = rng.randint(-amount, amount)
        return max(0, tick + offset)
    
    def tick_to_seconds(self, tick: int) -> float:
        """Convert PulseTick to wall-clock seconds."""
        return tick * self.seconds_per_tick
    
    def seconds_to_tick(self, seconds: float) -> int:
        """Convert wall-clock seconds to nearest PulseTick."""
        return int(seconds / self.seconds_per_tick)
