"""Rendering: MIDI files, audio synthesis and optional external backends."""

from .audio import AudioOptions, Synthesiser, write_wav
from .chunked import write_wav_chunked
from .backends import BackendResult, choose_audio_backend, convert_audio, play_audio, render_with_fluidsynth
from .midi import MidiWriter, midi_bytes, write_midi
from .voices import Voice, voice_for_program

__all__ = [
    "AudioOptions",
    "BackendResult",
    "MidiWriter",
    "Synthesiser",
    "Voice",
    "choose_audio_backend",
    "convert_audio",
    "midi_bytes",
    "play_audio",
    "render_with_fluidsynth",
    "voice_for_program",
    "write_midi",
    "write_wav",
    "write_wav_chunked",
]
