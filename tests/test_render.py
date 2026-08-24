"""MIDI writing, audio synthesis and the compile pipeline."""

from __future__ import annotations

import struct
import tempfile
import unittest
import wave
from pathlib import Path

from plainsong.notation import arrange, parse
from plainsong.pipeline import compile_text, slugify
from plainsong.render.audio import AudioOptions, Synthesiser, midi_to_hz
from plainsong.render.midi import midi_bytes, variable_length, write_midi
from plainsong.render.voices import voice_for_program
from plainsong.runtime.config import load_config

PIECE = """**TRACK: Render Test**
[MetaData]
key: C | tempo: 120 | subdivision: 8th
time: 4/4

[A] (2 Bars)
Chords: | C . . . | G . . . |
Melody: | C4 D4 E4 F4 | G4 . . . |
@bass | c2 . g1 . | g1 . d2 . | vel: 80
"""


def read_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """Split a MIDI file into (tag, body) pairs, verifying the lengths."""
    chunks = []
    position = 0
    while position < len(data):
        tag = data[position : position + 4]
        size = struct.unpack(">I", data[position + 4 : position + 8])[0]
        chunks.append((tag, data[position + 8 : position + 8 + size]))
        position += 8 + size
    assert position == len(data), "chunk lengths do not add up to the file size"
    return chunks


def count_notes(body: bytes) -> tuple[int, int]:
    """Count note-on and note-off events in a track body."""
    position = 0
    ons = offs = 0

    def read_vlq(index: int) -> tuple[int, int]:
        value = 0
        while True:
            byte = body[index]
            index += 1
            value = (value << 7) | (byte & 0x7F)
            if not byte & 0x80:
                return value, index

    while position < len(body):
        _delta, position = read_vlq(position)
        status = body[position]
        if status == 0xFF:
            position += 2
            length, position = read_vlq(position)
            position += length
        elif status & 0xF0 == 0x90:
            ons += 1
            position += 3
        elif status & 0xF0 == 0x80:
            offs += 1
            position += 3
        elif status & 0xF0 in (0xC0, 0xD0):
            position += 2
        else:
            position += 3
    return ons, offs


class TestVariableLength(unittest.TestCase):
    def test_known_values(self):
        # From the Standard MIDI File specification.
        self.assertEqual(variable_length(0), b"\x00")
        self.assertEqual(variable_length(127), b"\x7f")
        self.assertEqual(variable_length(128), b"\x81\x00")
        self.assertEqual(variable_length(8192), b"\xc0\x00")
        self.assertEqual(variable_length(0x0FFFFFFF), b"\xff\xff\xff\x7f")


class TestMidiWriter(unittest.TestCase):
    def setUp(self):
        self.arrangement = arrange(parse(PIECE))
        self.data = midi_bytes(self.arrangement)
        self.chunks = read_chunks(self.data)

    def test_header(self):
        tag, body = self.chunks[0]
        self.assertEqual(tag, b"MThd")
        fmt, tracks, division = struct.unpack(">HHH", body)
        self.assertEqual(fmt, 1)
        self.assertEqual(division, 480)
        self.assertEqual(tracks, len(self.chunks) - 1)

    def test_every_note_is_switched_off(self):
        for tag, body in self.chunks[1:]:
            self.assertEqual(tag, b"MTrk")
            ons, offs = count_notes(body)
            self.assertEqual(ons, offs)

    def test_note_count_matches_the_arrangement(self):
        total = sum(count_notes(body)[0] for _tag, body in self.chunks[1:])
        self.assertEqual(total, self.arrangement.note_count)

    def test_conductor_track_carries_tempo(self):
        _tag, body = self.chunks[1]
        self.assertIn(b"\xff\x51\x03", body)

    def test_lyrics_are_written(self):
        data = midi_bytes(arrange(parse("[A]\nMelody: | C4 |\nLyrics: | hello |\n")))
        self.assertIn(b"hello", data)

    def test_writes_to_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            target = write_midi(self.arrangement, Path(directory) / "nested" / "out.mid")
            self.assertTrue(target.exists())
            self.assertEqual(target.read_bytes()[:4], b"MThd")


class TestSynthesis(unittest.TestCase):
    def test_frequencies(self):
        self.assertAlmostEqual(midi_to_hz(69), 440.0)
        self.assertAlmostEqual(midi_to_hz(81), 880.0)
        self.assertAlmostEqual(midi_to_hz(60), 261.6255653, places=5)

    def test_voice_selection_covers_every_program(self):
        for program in range(128):
            self.assertIsNotNone(voice_for_program(program))
        self.assertEqual(voice_for_program(0).name, "piano")
        self.assertEqual(voice_for_program(33).name, "bass")
        self.assertEqual(voice_for_program(40).name, "strings")
        self.assertEqual(voice_for_program(60, is_drum=True).name, "drum")

    def test_produces_audible_output(self):
        synth = Synthesiser(AudioOptions(sample_rate=8000, tail=0.1))
        with tempfile.TemporaryDirectory() as directory:
            target = synth.write(arrange(parse(PIECE)), Path(directory) / "out.wav")
            with wave.open(str(target), "rb") as handle:
                self.assertEqual(handle.getnchannels(), 1)
                self.assertEqual(handle.getsampwidth(), 2)
                self.assertEqual(handle.getframerate(), 8000)
                frames = handle.getnframes()
                raw = handle.readframes(frames)

        self.assertGreater(frames, 8000)
        peak = max(
            abs(int.from_bytes(raw[i : i + 2], "little", signed=True)) for i in range(0, len(raw) - 1, 2)
        )
        self.assertGreater(peak, 5000, "audio is too quiet to be real output")
        self.assertLessEqual(peak, 32767)

    def test_deterministic(self):
        arrangement = arrange(parse(PIECE))
        options = AudioOptions(sample_rate=8000, tail=0.1)
        self.assertEqual(
            Synthesiser(options).to_wav_bytes(arrangement),
            Synthesiser(options).to_wav_bytes(arrangement),
        )

    def test_silence_still_writes_a_file(self):
        synth = Synthesiser(AudioOptions(sample_rate=8000, tail=0.1))
        arrangement = arrange(parse("[A]\nMelody: | (rest) (rest) |\n"))
        with tempfile.TemporaryDirectory() as directory:
            target = synth.write(arrangement, Path(directory) / "quiet.wav")
            self.assertTrue(target.exists())


class TestPipeline(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")
        self.assertEqual(slugify("   "), "untitled")

    def test_compile_writes_both_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = compile_text(
                PIECE,
                midi=root / "song.mid",
                audio=root / "song.wav",
                config=load_config(),
            )
            self.assertTrue(result.ok)
            self.assertTrue(result.midi_path.exists())
            self.assertTrue(result.audio_path.exists())
            self.assertIn("parse", result.elapsed)
            self.assertIn("Render Test", result.describe())

    def test_compile_reports_errors_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "broken.mid"
            result = compile_text("", midi=target, config=load_config())
            self.assertFalse(result.ok)
            self.assertFalse(target.exists())

    def test_transpose_while_compiling(self):
        plain = compile_text(PIECE, config=load_config())
        moved = compile_text(PIECE, config=load_config(), arrange_overrides={"transpose": 2})
        first = plain.arrangement.tracks[0].notes[0].pitch
        second = moved.arrangement.tracks[0].notes[0].pitch
        self.assertEqual(second - first, 2)


if __name__ == "__main__":
    unittest.main()
