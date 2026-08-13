"""Tests for SWMIDI-8 codec."""
import pytest
from swmidi8 import (
    SWMIDIEvent, EventType, Friction, ActionType,
    encode_event, decode_event, encode_stream, decode_stream
)

class TestEncodeDecode:
    def test_roundtrip_basic(self):
        e = SWMIDIEvent(EventType.NoteOn, 0, 60, 100, 0, 96)
        data = encode_event(e)
        assert len(data) == 8
        decoded = decode_event(data)
        assert decoded.event_type == EventType.NoteOn
        assert decoded.channel == 0
        assert decoded.pitch == 60
        assert decoded.velocity == 100
        assert decoded.error_mask == 0
        assert decoded.tick == 96

    def test_all_event_types(self):
        for et in EventType:
            e = SWMIDIEvent(et, 0, 60, 64, 0, 0)
            d = decode_event(encode_event(e))
            assert d.event_type == et

    def test_all_channels(self):
        for ch in range(16):
            e = SWMIDIEvent(EventType.NoteOn, ch, 60, 64, 0, 0)
            d = decode_event(encode_event(e))
            assert d.channel == ch

    def test_max_tick(self):
        e = SWMIDIEvent(EventType.NoteOn, 0, 60, 64, 0, 4294967295)
        d = decode_event(encode_event(e))
        assert d.tick == 4294967295

    def test_truncated_raises(self):
        with pytest.raises(ValueError, match='Truncated'):
            decode_event(b'\x00\x00\x00\x00')

class TestFriction:
    def test_no_friction(self):
        e = SWMIDIEvent(EventType.NoteOn, 0, 60, 64, 0, 0)
        assert e.friction_flags == []

    def test_single_friction(self):
        e = SWMIDIEvent(EventType.NoteOn, 0, 60, 64, Friction.Timeout, 0)
        assert 'Timeout' in e.friction_flags

    def test_multiple_friction(self):
        mask = Friction.Timeout | Friction.RateLimit | Friction.NetworkError
        e = SWMIDIEvent(EventType.NoteOn, 0, 60, 64, mask, 0)
        flags = e.friction_flags
        assert 'Timeout' in flags
        assert 'RateLimit' in flags
        assert 'NetworkError' in flags
        assert len(flags) == 3

class TestStream:
    def test_stream_roundtrip(self):
        events = [
            SWMIDIEvent(EventType.NoteOn, 0, 60, 100, 0, 0),
            SWMIDIEvent(EventType.NoteOn, 0, 64, 80, 0, 48),
            SWMIDIEvent(EventType.NoteOff, 0, 60, 0, 0, 96),
            SWMIDIEvent(EventType.NoteOff, 0, 64, 0, 0, 96),
        ]
        data = encode_stream(events)
        assert len(data) == 32
        decoded = decode_stream(data)
        assert len(decoded) == 4
        assert decoded[0].pitch == 60
        assert decoded[1].pitch == 64
        assert decoded[2].event_type == EventType.NoteOff

    def test_empty_stream(self):
        data = encode_stream([])
        assert data == b''
        assert decode_stream(data) == []

class TestActionTypes:
    def test_conversation_action(self):
        e = SWMIDIEvent(EventType.NoteOn, 0, ActionType.MessageSent, 90, 0, 0)
        d = decode_event(encode_event(e))
        assert d.pitch == ActionType.MessageSent

    def test_build_action_with_friction(self):
        e = SWMIDIEvent(
            EventType.NoteOn, 0, ActionType.BuildFailed, 50,
            Friction.SyntaxError | Friction.TypeMismatch, 192
        )
        d = decode_event(encode_event(e))
        assert d.pitch == ActionType.BuildFailed
        assert 'SyntaxError' in d.friction_flags
        assert 'TypeMismatch' in d.friction_flags

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
