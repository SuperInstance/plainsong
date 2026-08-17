"""Standard MIDI File writer.

Written against the SMF specification rather than a library, because a MIDI
file is a few hundred bytes of well-documented structure and the alternative is
making every user install a package to hear anything. The output is a format-1
file: one conductor track carrying tempo and metre, then one track per voice.

``pretty_midi`` and ``mido`` are never required. If they happen to be
installed, nothing here changes -- they are only used for reading files back in
:mod:`plainsong.render.backends`.

Notes are written at their *emission* times: the moment a player or a sequencer
has to act. On a piece that declares no stage that is the written time and this
file is byte for byte what it always was. See ``docs/performance.md``.
"""

from __future__ import annotations

import struct
from pathlib import Path

from ..notation.ir import Arrangement

DEFAULT_TICKS_PER_BEAT = 480

# Meta event identifiers.
META_TEXT = 0x01
META_TRACK_NAME = 0x03
META_LYRIC = 0x05
META_MARKER = 0x06
META_TEMPO = 0x51
META_TIME_SIGNATURE = 0x58
META_KEY_SIGNATURE = 0x59
META_END_OF_TRACK = 0x2F


def variable_length(value: int) -> bytes:
    """Encode an integer as a MIDI variable-length quantity."""
    if value < 0:
        value = 0
    buffer = bytearray([value & 0x7F])
    value >>= 7
    while value:
        buffer.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(buffer))


def _meta(kind: int, payload: bytes) -> bytes:
    return bytes([0xFF, kind]) + variable_length(len(payload)) + payload


def _text_meta(kind: int, text: str) -> bytes:
    return _meta(kind, text.encode("utf-8", errors="replace")[:127])


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return tag + struct.pack(">I", len(payload)) + payload


def _serialise(events: list[tuple[int, int, bytes]]) -> bytes:
    """Turn (tick, order, payload) triples into a track chunk body.

    *order* breaks ties so that note-offs are written before note-ons at the
    same tick; a note that ends exactly where the next begins should not
    truncate its neighbour on a synthesiser that tracks note counts.
    """
    events.sort(key=lambda event: (event[0], event[1]))
    body = bytearray()
    previous = 0
    for tick, _order, payload in events:
        body += variable_length(tick - previous)
        body += payload
        previous = tick
    body += variable_length(0) + _meta(META_END_OF_TRACK, b"")
    return bytes(body)


class MidiWriter:
    """Build a format-1 Standard MIDI File from an :class:`Arrangement`."""

    def __init__(self, ticks_per_beat: int = DEFAULT_TICKS_PER_BEAT, include_lyrics: bool = True) -> None:
        self.ticks_per_beat = ticks_per_beat
        self.include_lyrics = include_lyrics

    def _ticks(self, beats: float) -> int:
        return max(0, int(round(beats * self.ticks_per_beat)))

    def _conductor_track(self, arrangement: Arrangement) -> bytes:
        meta = arrangement.meta
        events: list[tuple[int, int, bytes]] = []
        title = meta.title or "Plainsong"
        events.append((0, 0, _text_meta(META_TRACK_NAME, title)))

        microseconds = int(round(60_000_000 / max(meta.tempo, 1e-6)))
        events.append((0, 1, _meta(META_TEMPO, struct.pack(">I", microseconds)[1:])))

        denominator_power = max(0, (meta.meter.denominator).bit_length() - 1)
        events.append(
            (
                0,
                2,
                _meta(
                    META_TIME_SIGNATURE,
                    bytes([meta.meter.numerator, denominator_power, 24, 8]),
                ),
            )
        )

        # Key signature: accidentals as a signed byte, then major/minor flag.
        sharps_by_pc = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 1: -5, 8: -4, 3: -3, 10: -2, 5: -1}
        is_minor = meta.key.mode in {"minor", "aeolian", "harmonic_minor", "melodic_minor"}
        accidentals = sharps_by_pc.get(meta.key.tonic_pc, 0)
        events.append(
            (0, 3, _meta(META_KEY_SIGNATURE, struct.pack("bB", accidentals, 1 if is_minor else 0)))
        )

        for name, beat in arrangement.section_starts:
            events.append((self._ticks(beat), 4, _text_meta(META_MARKER, name)))

        if self.include_lyrics:
            for lyric in arrangement.lyrics:
                events.append((self._ticks(lyric.start), 5, _text_meta(META_LYRIC, lyric.text)))

        return _chunk(b"MTrk", _serialise(events))

    def _voice_track(self, track) -> bytes:
        events: list[tuple[int, int, bytes]] = []
        channel = 9 if track.is_drum else (track.channel & 0x0F)
        events.append((0, 0, _text_meta(META_TRACK_NAME, track.name or track.role)))
        events.append((0, 1, bytes([0xC0 | channel, track.program & 0x7F])))

        for note in track.notes:
            # Emission, not arrival: a MIDI file is an instruction to a player
            # or a sequencer, and what it needs to be told is when to act. On a
            # piece with no stage this is the written time, unchanged.
            start = self._ticks(note.emission_time)
            end = max(start + 1, self._ticks(note.emission_time + note.duration))
            pitch = max(0, min(127, int(note.pitch)))
            velocity = max(1, min(127, int(note.velocity)))
            events.append((start, 2, bytes([0x90 | channel, pitch, velocity])))
            events.append((end, 1, bytes([0x80 | channel, pitch, 0])))

        return _chunk(b"MTrk", _serialise(events))

    def to_bytes(self, arrangement: Arrangement) -> bytes:
        tracks = [self._conductor_track(arrangement)]
        for track in arrangement.tracks:
            if track.notes:
                tracks.append(self._voice_track(track))
        header = _chunk(
            b"MThd",
            struct.pack(">HHH", 1, len(tracks), self.ticks_per_beat),
        )
        return header + b"".join(tracks)

    def write(self, arrangement: Arrangement, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.to_bytes(arrangement))
        return target


def write_midi(
    arrangement: Arrangement,
    path: str | Path,
    ticks_per_beat: int = DEFAULT_TICKS_PER_BEAT,
) -> Path:
    """Write *arrangement* to a Standard MIDI File and return the path."""
    return MidiWriter(ticks_per_beat=ticks_per_beat).write(arrangement, path)


def midi_bytes(arrangement: Arrangement, ticks_per_beat: int = DEFAULT_TICKS_PER_BEAT) -> bytes:
    return MidiWriter(ticks_per_beat=ticks_per_beat).to_bytes(arrangement)
