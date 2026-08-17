"""
SWMIDI-8 Wire Format Codec — Python Implementation
Port of tensor-midi/src/swmidi.js

Every event is exactly 8 bytes. No variable-length encoding.
byte 0: status = type(4 bits) | channel(4 bits)
byte 1: pitch (action type, 7 bits)
byte 2: velocity (weight/confidence, 7 bits)
byte 3: error_mask (friction bitfield, 8 bits)
bytes 4-7: tick (uint32, little-endian, 96 PPQ)
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
from typing import List
import struct

class EventType(IntEnum):
    NoteOn = 0
    NoteOff = 1
    ControlChange = 2
    ProgramChange = 3
    Meta = 4

EVENT_NAMES = {0: 'NoteOn', 1: 'NoteOff', 2: 'ControlChange', 3: 'ProgramChange', 4: 'Meta'}

class Friction(IntEnum):
    """Friction bitfield — the error_mask byte."""
    None_ = 0x00
    Timeout = 0x01      # Agent took too long
    Conflict = 0x02     # Two agents collided
    RateLimit = 0x04    # API rate limited
    Ambiguity = 0x08    # Unclear intent
    ImportError = 0x10  # Missing dependency
    SyntaxError = 0x20  # Code didn't parse
    TypeMismatch = 0x40 # Wrong type
    NetworkError = 0x80 # Network failure

class ActionType(IntEnum):
    """Action types for conversation-as-music events."""
    MessageSent = 0
    MessageReceived = 1
    TypingStart = 2
    TypingStop = 3
    UserJoin = 4
    UserLeave = 5
    FileCreated = 10
    FileModified = 11
    FileDeleted = 12
    BuildStart = 20
    BuildComplete = 21
    BuildFailed = 22
    DeployStart = 30
    DeployComplete = 31
    IdeaProposed = 40
    IdeaAccepted = 41
    IdeaRejected = 42
    AgentSpawn = 50
    AgentComplete = 51
    Heartbeat = 60
    Error = 127

@dataclass
class SWMIDIEvent:
    """A single SWMIDI-8 event (8 bytes on the wire)."""
    event_type: int      # EventType
    channel: int         # 0-15
    pitch: int           # 0-127 (note number or action type)
    velocity: int        # 0-127 (weight/confidence)
    error_mask: int      # 0-255 (Friction bitfield)
    tick: int            # 0-4294967295 (96 PPQ grid position)

    @property
    def event_type_label(self) -> str:
        return EVENT_NAMES.get(self.event_type, 'Unknown')

    @property
    def friction_flags(self) -> List[str]:
        flags = []
        for f in Friction:
            if f == Friction.None_:
                continue
            if self.error_mask & f:
                flags.append(f.name)
        return flags

    def __repr__(self):
        return (f"SWMIDIEvent({self.event_type_label}, ch={self.channel}, "
                f"pitch={self.pitch}, vel={self.velocity}, "
                f"friction={self.friction_flags or 'none'}, tick={self.tick})")


def encode_event(event: SWMIDIEvent) -> bytes:
    """Encode a single SWMIDI-8 event to 8 bytes."""
    status = ((event.event_type & 0x0F) << 4) | (event.channel & 0x0F)
    return struct.pack('<BBBBI',
        status,
        event.pitch & 0x7F,
        event.velocity & 0x7F,
        event.error_mask & 0xFF,
        event.tick & 0xFFFFFFFF
    )


def decode_event(data: bytes, offset: int = 0) -> SWMIDIEvent:
    """Decode 8 bytes to a SWMIDI-8 event."""
    if len(data) - offset < 8:
        raise ValueError(f'Truncated: need 8 bytes, got {len(data) - offset}')
    status, pitch, velocity, error_mask, tick = struct.unpack_from('<BBBBI', data, offset)
    event_type = (status >> 4) & 0x0F
    channel = status & 0x0F
    if event_type > 4:
        raise ValueError(f'Invalid event type: {event_type}')
    return SWMIDIEvent(
        event_type=event_type,
        channel=channel,
        pitch=pitch,
        velocity=velocity,
        error_mask=error_mask,
        tick=tick
    )


def encode_stream(events: List[SWMIDIEvent]) -> bytes:
    """Encode a list of events to a contiguous byte stream."""
    return b''.join(encode_event(e) for e in events)


def decode_stream(data: bytes) -> List[SWMIDIEvent]:
    """Decode a byte stream to a list of events."""
    if len(data) % 8 != 0:
        raise ValueError(f'Stream length {len(data)} is not a multiple of 8')
    return [decode_event(data, i) for i in range(0, len(data), 8)]
