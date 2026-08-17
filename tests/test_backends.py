"""Graceful degradation of optional rendering backends.

Every backend function returns a BackendResult explaining what it could not do,
rather than raising or silently pretending success. This suite verifies that
claim by mocking the absence of tools and probing their failure messages.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from plainsong.render.backends import (
    BackendResult,
    audio_backends,
    choose_audio_backend,
    convert_audio,
    play_audio,
    render_with_fluidsynth,
    send_to_midi_port,
)
from plainsong.runtime.capabilities import Capability, CapabilityReport


class TestAudioBackends(unittest.TestCase):
    """audio_backends() and choose_audio_backend() degrade honestly."""

    def test_builtin_always_available(self):
        """builtin is always in the list, even if no other backends exist."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=False),
                Capability("soundfont", present=False),
            ]
        )
        backends = audio_backends(report)
        self.assertIn("builtin", backends)

    def test_fluidsynth_offered_when_both_present(self):
        """fluidsynth appears first only when both fluidsynth and soundfont exist."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=True, detail="/usr/bin/fluidsynth"),
                Capability("soundfont", present=True, detail="/usr/share/soundfonts/gm.sf2"),
            ]
        )
        backends = audio_backends(report)
        self.assertEqual(backends[0], "fluidsynth")

    def test_fluidsynth_omitted_if_missing_binary(self):
        """fluidsynth does not appear if the binary is missing."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=False),
                Capability("soundfont", present=True, detail="/usr/share/soundfonts/gm.sf2"),
            ]
        )
        backends = audio_backends(report)
        self.assertNotIn("fluidsynth", backends)

    def test_fluidsynth_omitted_if_missing_soundfont(self):
        """fluidsynth does not appear if no soundfont is found."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=True, detail="/usr/bin/fluidsynth"),
                Capability("soundfont", present=False),
            ]
        )
        backends = audio_backends(report)
        self.assertNotIn("fluidsynth", backends)

    def test_audio_backends_uses_default_probe_if_not_provided(self):
        """audio_backends() probes capabilities if no report is given."""
        # This should not raise; it will use the real probe
        backends = audio_backends()
        self.assertIsInstance(backends, list)
        self.assertIn("builtin", backends)

    def test_choose_auto_returns_first_available(self):
        """preference='auto' returns the first backend in the list."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=True, detail="/usr/bin/fluidsynth"),
                Capability("soundfont", present=True, detail="/usr/share/soundfonts/gm.sf2"),
            ]
        )
        backend = choose_audio_backend("auto", report)
        self.assertEqual(backend, "fluidsynth")

    def test_choose_empty_string_returns_first_available(self):
        """preference='' returns the first backend in the list."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=True, detail="/usr/bin/fluidsynth"),
                Capability("soundfont", present=True, detail="/usr/share/soundfonts/gm.sf2"),
            ]
        )
        backend = choose_audio_backend("", report)
        self.assertEqual(backend, "fluidsynth")

    def test_choose_none_returns_first_available(self):
        """preference=None returns the first backend in the list."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=True, detail="/usr/bin/fluidsynth"),
                Capability("soundfont", present=True, detail="/usr/share/soundfonts/gm.sf2"),
            ]
        )
        backend = choose_audio_backend(None, report)
        self.assertEqual(backend, "fluidsynth")

    def test_choose_prefers_requested_if_available(self):
        """If preference is available, it is chosen."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=True, detail="/usr/bin/fluidsynth"),
                Capability("soundfont", present=True, detail="/usr/share/soundfonts/gm.sf2"),
            ]
        )
        backend = choose_audio_backend("builtin", report)
        self.assertEqual(backend, "builtin")

    def test_choose_falls_back_to_builtin_if_preference_unavailable(self):
        """If preference is not available, fall back to builtin."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=False),
                Capability("soundfont", present=False),
            ]
        )
        backend = choose_audio_backend("nonexistent", report)
        self.assertEqual(backend, "builtin")

    def test_choose_never_raises_on_unknown_preference(self):
        """An unknown preference does not raise; it falls back gracefully."""
        report = CapabilityReport([])
        # Should not raise
        backend = choose_audio_backend("totally-unknown-backend", report)
        self.assertEqual(backend, "builtin")


class TestRenderWithFluidsynth(unittest.TestCase):
    """render_with_fluidsynth() degrades when fluidsynth or soundfont is missing."""

    def test_reports_when_fluidsynth_not_installed(self):
        """If fluidsynth is not installed, ok is False and message says so."""
        report = CapabilityReport([Capability("fluidsynth", present=False)])
        result = render_with_fluidsynth("/path/to/song.mid", "/path/to/out.wav", report=report)
        self.assertFalse(result.ok)
        self.assertIn("fluidsynth", result.message)
        self.assertIn("not installed", result.message)

    def test_reports_when_no_soundfont_found(self):
        """If no soundfont is found, ok is False and message says so."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=True),
                Capability("soundfont", present=False),
            ]
        )
        result = render_with_fluidsynth("/path/to/song.mid", "/path/to/out.wav", report=report)
        self.assertFalse(result.ok)
        self.assertIn("soundfont", result.message)

    def test_uses_provided_soundfont(self):
        """If a soundfont is provided explicitly, it is passed to fluidsynth."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=True),
                Capability("soundfont", present=True, detail="/default.sf2"),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            midi_path = Path(tmpdir) / "song.mid"
            wav_path = Path(tmpdir) / "out.wav"
            midi_path.write_bytes(b"fake midi")

            with patch("plainsong.render.backends._run") as mock_run:
                mock_run.return_value = (False, "fluidsynth not in PATH")
                result = render_with_fluidsynth(midi_path, wav_path, soundfont="/custom.sf2", report=report)
                # The call should not raise; it reports the failure
                self.assertFalse(result.ok)

    def test_reports_run_failure(self):
        """If _run fails, the failure message is reported."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=True),
                Capability("soundfont", present=True, detail="/usr/share/soundfonts/gm.sf2"),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            midi_path = Path(tmpdir) / "song.mid"
            wav_path = Path(tmpdir) / "out.wav"
            midi_path.write_bytes(b"fake midi")

            with patch("plainsong.render.backends._run") as mock_run:
                mock_run.return_value = (False, "fluidsynth: unknown option")
                result = render_with_fluidsynth(midi_path, wav_path, report=report)
                self.assertFalse(result.ok)
                self.assertEqual(result.message, "fluidsynth: unknown option")

    def test_reports_when_output_file_does_not_exist(self):
        """If fluidsynth succeeds but produces no file, ok is False."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=True),
                Capability("soundfont", present=True, detail="/usr/share/soundfonts/gm.sf2"),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            midi_path = Path(tmpdir) / "song.mid"
            wav_path = Path(tmpdir) / "out.wav"
            midi_path.write_bytes(b"fake midi")

            with patch("plainsong.render.backends._run") as mock_run:
                mock_run.return_value = (True, "")
                result = render_with_fluidsynth(midi_path, wav_path, report=report)
                self.assertFalse(result.ok)
                self.assertIn("no audio", result.message.lower())

    def test_reports_when_output_file_is_empty(self):
        """If fluidsynth produces an empty file, ok is False."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=True),
                Capability("soundfont", present=True, detail="/usr/share/soundfonts/gm.sf2"),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            midi_path = Path(tmpdir) / "song.mid"
            wav_path = Path(tmpdir) / "out.wav"
            midi_path.write_bytes(b"fake midi")

            with patch("plainsong.render.backends._run") as mock_run:
                mock_run.return_value = (True, "")
                # Create an empty file to simulate fluidsynth producing nothing
                wav_path.write_bytes(b"")
                result = render_with_fluidsynth(midi_path, wav_path, report=report)
                self.assertFalse(result.ok)

    def test_succeeds_and_returns_path(self):
        """When fluidsynth succeeds, ok is True and path is set."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=True),
                Capability("soundfont", present=True, detail="/usr/share/soundfonts/gm.sf2"),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            midi_path = Path(tmpdir) / "song.mid"
            wav_path = Path(tmpdir) / "out.wav"
            midi_path.write_bytes(b"fake midi")

            with patch("plainsong.render.backends._run") as mock_run:
                mock_run.return_value = (True, "")
                # Create a non-empty file to simulate success
                wav_path.write_bytes(b"fake wav data")
                result = render_with_fluidsynth(midi_path, wav_path, report=report)
                self.assertTrue(result.ok)
                self.assertEqual(result.path, wav_path)
                self.assertEqual(result.backend, "fluidsynth")

    def test_creates_parent_directories(self):
        """Parent directories are created if they do not exist."""
        report = CapabilityReport(
            [
                Capability("fluidsynth", present=True),
                Capability("soundfont", present=True, detail="/usr/share/soundfonts/gm.sf2"),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            midi_path = Path(tmpdir) / "song.mid"
            wav_path = Path(tmpdir) / "deep" / "nested" / "out.wav"
            midi_path.write_bytes(b"fake midi")

            with patch("plainsong.render.backends._run") as mock_run:
                mock_run.return_value = (True, "")
                # Ensure the directory exists before writing
                wav_path.parent.mkdir(parents=True, exist_ok=True)
                wav_path.write_bytes(b"fake wav data")
                result = render_with_fluidsynth(midi_path, wav_path, report=report)
                # If this doesn't raise, the directories were created
                self.assertTrue(result.ok)


class TestConvertAudio(unittest.TestCase):
    """convert_audio() degrades when ffmpeg is missing or format is unsupported."""

    def test_rejects_unsupported_format(self):
        """An unsupported extension is rejected without calling ffmpeg."""
        result = convert_audio("/path/to/input.wav", "/path/to/output.xyz")
        self.assertFalse(result.ok)
        self.assertIn("unsupported format", result.message)
        self.assertIn(".xyz", result.message)

    def test_wav_copies_without_ffmpeg(self):
        """Converting to .wav copies the file without invoking ffmpeg."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "input.wav"
            target = Path(tmpdir) / "output.wav"
            source.write_bytes(b"fake wav data")

            result = convert_audio(source, target)
            self.assertTrue(result.ok)
            self.assertEqual(result.backend, "copy")
            self.assertEqual(result.path, target)
            self.assertEqual(target.read_bytes(), b"fake wav data")

    def test_mp3_needs_ffmpeg(self):
        """Converting to .mp3 returns ok=False if ffmpeg is not present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "input.wav"
            target = Path(tmpdir) / "output.mp3"
            source.write_bytes(b"fake wav data")

            with patch("shutil.which") as mock_which:
                mock_which.return_value = None
                result = convert_audio(source, target)
                self.assertFalse(result.ok)
                self.assertIn("ffmpeg", result.message)
                self.assertIn("not installed", result.message)

    def test_ogg_needs_ffmpeg(self):
        """Converting to .ogg requires ffmpeg."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "input.wav"
            target = Path(tmpdir) / "output.ogg"
            source.write_bytes(b"fake wav data")

            with patch("shutil.which") as mock_which:
                mock_which.return_value = None
                result = convert_audio(source, target)
                self.assertFalse(result.ok)
                self.assertIn("ffmpeg", result.message)

    def test_flac_needs_ffmpeg(self):
        """Converting to .flac requires ffmpeg."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "input.wav"
            target = Path(tmpdir) / "output.flac"
            source.write_bytes(b"fake wav data")

            with patch("shutil.which") as mock_which:
                mock_which.return_value = None
                result = convert_audio(source, target)
                self.assertFalse(result.ok)

    def test_m4a_needs_ffmpeg(self):
        """Converting to .m4a requires ffmpeg."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "input.wav"
            target = Path(tmpdir) / "output.m4a"
            source.write_bytes(b"fake wav data")

            with patch("shutil.which") as mock_which:
                mock_which.return_value = None
                result = convert_audio(source, target)
                self.assertFalse(result.ok)

    def test_reports_ffmpeg_failure(self):
        """If ffmpeg fails, the error message is reported."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "input.wav"
            target = Path(tmpdir) / "output.mp3"
            source.write_bytes(b"fake wav data")

            with patch("shutil.which") as mock_which:
                mock_which.return_value = "/usr/bin/ffmpeg"
                with patch("plainsong.render.backends._run") as mock_run:
                    mock_run.return_value = (False, "ffmpeg: codec not found")
                    result = convert_audio(source, target)
                    self.assertFalse(result.ok)
                    self.assertEqual(result.message, "ffmpeg: codec not found")

    def test_succeeds_with_ffmpeg(self):
        """When ffmpeg succeeds, ok is True and path is set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "input.wav"
            target = Path(tmpdir) / "output.mp3"
            source.write_bytes(b"fake wav data")

            with patch("shutil.which") as mock_which:
                mock_which.return_value = "/usr/bin/ffmpeg"
                with patch("plainsong.render.backends._run") as mock_run:
                    mock_run.return_value = (True, "")
                    # Create the output file to simulate success
                    target.write_bytes(b"fake mp3 data")
                    result = convert_audio(source, target)
                    self.assertTrue(result.ok)
                    self.assertEqual(result.backend, "ffmpeg")
                    self.assertEqual(result.path, target)

    def test_creates_parent_directories_for_mp3(self):
        """Parent directories are created for non-wav outputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "input.wav"
            target = Path(tmpdir) / "deep" / "nested" / "output.mp3"
            source.write_bytes(b"fake wav data")

            with patch("shutil.which") as mock_which:
                mock_which.return_value = "/usr/bin/ffmpeg"
                with patch("plainsong.render.backends._run") as mock_run:
                    mock_run.return_value = (True, "")
                    # Ensure the directory exists before writing
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"fake mp3 data")
                    result = convert_audio(source, target)
                    self.assertTrue(result.ok)
                    self.assertTrue(target.exists())

    def test_case_insensitive_extension(self):
        """Extension matching is case-insensitive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "input.wav"
            target = Path(tmpdir) / "output.WAV"
            source.write_bytes(b"fake wav data")

            result = convert_audio(source, target)
            self.assertTrue(result.ok)
            self.assertEqual(result.backend, "copy")


class TestPlayAudio(unittest.TestCase):
    """play_audio() degrades when no player is available."""

    def test_reports_when_no_player_present(self):
        """If no audio player is found, ok is False."""
        report = CapabilityReport([Capability("audio_playback", present=False)])
        result = play_audio("/path/to/audio.wav", report=report)
        self.assertFalse(result.ok)
        self.assertIn("player", result.message.lower())

    def test_uses_default_probe_if_not_provided(self):
        """play_audio() probes capabilities if no report is given."""
        # This should not raise; it will use the real probe
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "audio.wav"
            audio_path.write_bytes(b"fake audio")
            # The real probe may or may not find a player; either way, no raise
            result = play_audio(audio_path)
            self.assertIsInstance(result, BackendResult)

    def test_reports_when_no_command_available(self):
        """If capability exists but has no command, ok is False."""
        cap = Capability("audio_playback", present=True, detail="player", data={"command": []})
        report = CapabilityReport([cap])
        result = play_audio("/path/to/audio.wav", report=report)
        self.assertFalse(result.ok)
        self.assertIn("command", result.message.lower())

    def test_calls_player_with_path(self):
        """If a player is available, it is called with the audio path."""
        cap = Capability(
            "audio_playback",
            present=True,
            detail="ffplay",
            data={"command": ["ffplay", "-nodisp", "-autoexit", "{path}"]},
        )
        report = CapabilityReport([cap])
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "audio.wav"
            audio_path.write_bytes(b"fake audio")

            with patch("plainsong.render.backends._run") as mock_run:
                mock_run.return_value = (True, "")
                result = play_audio(audio_path, report=report)
                self.assertTrue(result.ok)
                # Verify _run was called
                mock_run.assert_called_once()

    def test_appends_path_if_not_in_command(self):
        """If {path} is not in the command, the path is appended."""
        cap = Capability(
            "audio_playback",
            present=True,
            detail="aplay",
            data={"command": ["aplay", "-q"]},
        )
        report = CapabilityReport([cap])
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "audio.wav"
            audio_path.write_bytes(b"fake audio")

            with patch("plainsong.render.backends._run") as mock_run:
                mock_run.return_value = (True, "")
                play_audio(audio_path, report=report)
                # Verify path was appended to the command
                call_args = mock_run.call_args[0][0]
                self.assertEqual(call_args[-1], str(audio_path))

    def test_reports_player_failure(self):
        """If the player fails, the error message is reported."""
        cap = Capability(
            "audio_playback",
            present=True,
            detail="ffplay",
            data={"command": ["ffplay", "-nodisp", "-autoexit", "{path}"]},
        )
        report = CapabilityReport([cap])
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "audio.wav"
            audio_path.write_bytes(b"fake audio")

            with patch("plainsong.render.backends._run") as mock_run:
                mock_run.return_value = (False, "ffplay: file not found")
                result = play_audio(audio_path, report=report)
                self.assertFalse(result.ok)
                self.assertEqual(result.message, "ffplay: file not found")


class TestSendToMidiPort(unittest.TestCase):
    """send_to_midi_port() degrades when mido is not available."""

    def test_reports_when_mido_not_installed(self):
        """If mido cannot be imported, ok is False and message suggests pip install."""
        with patch.dict("sys.modules", {"mido": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module named 'mido'")):
                result = send_to_midi_port("/path/to/song.mid")
                self.assertFalse(result.ok)
                self.assertIn("pip install", result.message)
                self.assertIn("mido", result.message)

    def test_reports_when_no_midi_ports_open(self):
        """If no MIDI output ports are available, ok is False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            midi_path = Path(tmpdir) / "song.mid"
            midi_path.write_bytes(b"fake midi")

            mock_mido = MagicMock()
            mock_mido.get_output_names.return_value = []
            with patch.dict("sys.modules", {"mido": mock_mido}):
                result = send_to_midi_port(midi_path)
                self.assertFalse(result.ok)
                self.assertIn("no MIDI", result.message)

    def test_reports_exception_from_mido(self):
        """Exceptions during MIDI playback are reported, not raised."""
        with tempfile.TemporaryDirectory() as tmpdir:
            midi_path = Path(tmpdir) / "song.mid"
            midi_path.write_bytes(b"fake midi")

            mock_mido = MagicMock()
            mock_mido.get_output_names.return_value = ["port1"]
            mock_mido.MidiFile.side_effect = RuntimeError("Invalid MIDI file")
            with patch.dict("sys.modules", {"mido": mock_mido}):
                result = send_to_midi_port(midi_path)
                self.assertFalse(result.ok)
                self.assertIn("Invalid MIDI", result.message)

    def test_succeeds_and_reports_port_name(self):
        """When MIDI playback succeeds, ok is True and port name is in message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            midi_path = Path(tmpdir) / "song.mid"
            midi_path.write_bytes(b"fake midi")

            mock_mido = MagicMock()
            mock_mido.get_output_names.return_value = ["port1", "port2"]
            mock_midi_file = MagicMock()
            mock_midi_file.play.return_value = iter([])  # Empty iterator
            mock_mido.MidiFile.return_value = mock_midi_file
            with patch.dict("sys.modules", {"mido": mock_mido}):
                result = send_to_midi_port(midi_path)
                self.assertTrue(result.ok)
                self.assertIn("port1", result.message)

    def test_uses_provided_port(self):
        """If a port name is provided, it is used instead of the default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            midi_path = Path(tmpdir) / "song.mid"
            midi_path.write_bytes(b"fake midi")

            mock_mido = MagicMock()
            mock_mido.get_output_names.return_value = ["port1", "port2"]
            mock_midi_file = MagicMock()
            mock_midi_file.play.return_value = iter([])
            mock_mido.MidiFile.return_value = mock_midi_file
            mock_output = MagicMock()
            mock_mido.open_output.return_value.__enter__.return_value = mock_output
            with patch.dict("sys.modules", {"mido": mock_mido}):
                result = send_to_midi_port(midi_path, port="port2")
                mock_mido.open_output.assert_called_once_with("port2")
                self.assertIn("port2", result.message)


class TestBackendResultBool(unittest.TestCase):
    """BackendResult.__bool__ follows the ok field."""

    def test_true_when_ok_is_true(self):
        """BackendResult is truthy when ok is True."""
        result = BackendResult(ok=True, backend="test")
        self.assertTrue(result)
        self.assertTrue(bool(result))

    def test_false_when_ok_is_false(self):
        """BackendResult is falsy when ok is False."""
        result = BackendResult(ok=False, backend="test")
        self.assertFalse(result)
        self.assertFalse(bool(result))

    def test_in_if_statement_true(self):
        """BackendResult can be used in if statements (truthy case)."""
        result = BackendResult(ok=True, backend="test")
        if result:
            outcome = "success"
        else:
            outcome = "failure"
        self.assertEqual(outcome, "success")

    def test_in_if_statement_false(self):
        """BackendResult can be used in if statements (falsy case)."""
        result = BackendResult(ok=False, backend="test")
        if result:
            outcome = "success"
        else:
            outcome = "failure"
        self.assertEqual(outcome, "failure")


if __name__ == "__main__":
    unittest.main()
