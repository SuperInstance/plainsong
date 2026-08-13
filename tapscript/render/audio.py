"""Audio synthesis.

Renders an :class:`~tapscript.notation.ir.Arrangement` to a mono 16-bit WAV
using nothing but the standard library. If NumPy is installed it is used
automatically and the same code path produces the same audio, roughly twenty
times faster.

The pure-Python path avoids per-sample Python loops. Waveforms are built once
per (voice, pitch) as a short block of whole cycles and repeated; envelopes are
cached per (voice, length); mixing and enveloping run through ``map`` with
``operator`` callables so the inner loop stays in C.

Notes are placed at their *arrival* times, because a render is a recording of
what one listener hears. That is the opposite of the MIDI writer, which uses
emission times; the two differ only on a piece that declares a stage. See
``docs/performance.md``.
"""

from __future__ import annotations

import math
import wave
from array import array
from dataclasses import dataclass
from operator import add, mul
from pathlib import Path
from typing import Sequence

from ..notation.ir import Arrangement
from .voices import Voice, voice_for_program

try:  # optional accelerator
    import numpy as _np
except Exception:  # pragma: no cover - exercised only where numpy is absent
    _np = None

TWO_PI = 2.0 * math.pi


@dataclass
class AudioOptions:
    """Synthesis settings."""

    sample_rate: int = 44100
    normalize: float = 0.89
    tail: float = 1.2            # seconds of room left after the last note
    max_voices: int = 64         # simultaneous notes before gain protection
    use_numpy: bool = True
    lowpass: bool = True         # gentle one-pole smoothing on the master mix


def midi_to_hz(pitch: int) -> float:
    return 440.0 * (2.0 ** ((pitch - 69) / 12.0))


def _cycle_length(sample_rate: int, frequency: float) -> tuple[int, float]:
    """Length of a whole-cycle block, and the exact frequency it represents.

    A single rounded period detunes high notes audibly, so several periods are
    tried and the one whose rounded length is closest to a whole number of
    samples wins. The result is a block that loops seamlessly and stays within
    a couple of cents of the intended pitch.
    """
    period = sample_rate / max(frequency, 1e-6)
    best_cycles, best_error = 1, abs(round(period) - period) / period
    for cycles in range(2, 9):
        span = period * cycles
        error = abs(round(span) - span) / span
        if error < best_error:
            best_cycles, best_error = cycles, error
        if error < 1e-4:
            break
    length = max(2, int(round(period * best_cycles)))
    return length, sample_rate * best_cycles / length


class Synthesiser:
    """Turns arrangements into samples."""

    def __init__(self, options: AudioOptions | None = None) -> None:
        self.options = options or AudioOptions()
        self._wave_cache: dict[tuple[str, int], Sequence[float]] = {}
        self._env_cache: dict[tuple[str, int], Sequence[float]] = {}
        self._noise_cache: dict[int, Sequence[float]] = {}
        self.backend = "numpy" if (_np is not None and self.options.use_numpy) else "python"

    # -- waveform construction ----------------------------------------------

    def _noise_block(self, length: int):
        """Deterministic pseudo-noise. Same input, same audio, every run."""
        cached = self._noise_cache.get(length)
        if cached is not None:
            return cached
        state = 0x2545F491
        values = []
        for _ in range(length):
            state = (1103515245 * state + 12345) & 0x7FFFFFFF
            values.append((state / 0x3FFFFFFF) - 1.0)
        block = _np.asarray(values, dtype=_np.float64) if self.backend == "numpy" else values
        self._noise_cache[length] = block
        return block

    def _wavetable(self, voice: Voice, pitch: int):
        key = (voice.name, pitch)
        cached = self._wave_cache.get(key)
        if cached is not None:
            return cached

        rate = self.options.sample_rate
        frequency = midi_to_hz(pitch)
        length, true_frequency = _cycle_length(rate, frequency)
        harmonics = [amp for amp in voice.harmonics if amp]
        nyquist = rate * 0.5
        total = sum(harmonics) or 1.0

        if self.backend == "numpy":
            phase = _np.arange(length, dtype=_np.float64) * (TWO_PI * true_frequency / rate)
            table = _np.zeros(length, dtype=_np.float64)
            for index, amplitude in enumerate(harmonics, start=1):
                if true_frequency * index >= nyquist:
                    break
                table += amplitude * _np.sin(phase * index)
            table /= total
            if voice.noise:
                table = table * (1.0 - voice.noise) + self._noise_block(length) * voice.noise
        else:
            step = TWO_PI * true_frequency / rate
            table = [0.0] * length
            for index, amplitude in enumerate(harmonics, start=1):
                if true_frequency * index >= nyquist:
                    break
                partial = step * index
                for sample in range(length):
                    table[sample] += amplitude * math.sin(partial * sample)
            table = [value / total for value in table]
            if voice.noise:
                noise = self._noise_block(length)
                blend = voice.noise
                table = [value * (1.0 - blend) + noise[i] * blend for i, value in enumerate(table)]

        self._wave_cache[key] = table
        return table

    def _envelope(self, voice: Voice, samples: int):
        key = (voice.name, samples)
        cached = self._env_cache.get(key)
        if cached is not None:
            return cached

        rate = self.options.sample_rate
        duration = samples / rate
        attack, decay, sustain, release = voice.envelope_points(duration)
        attack_n = max(1, int(attack * rate))
        decay_n = max(1, int(decay * rate))
        release_n = max(1, int(release * rate))
        sustain_n = max(0, samples - attack_n - decay_n - release_n)

        if self.backend == "numpy":
            parts = [_np.linspace(0.0, 1.0, attack_n, endpoint=False)]
            if voice.percussive:
                # Percussive voices ignore the sustain shelf and decay away.
                falloff = _np.exp(-_np.linspace(0.0, 4.5, max(1, samples - attack_n)))
                envelope = _np.concatenate([parts[0], falloff])[:samples]
            else:
                parts.append(_np.linspace(1.0, sustain, decay_n, endpoint=False))
                parts.append(_np.full(sustain_n, sustain))
                parts.append(_np.linspace(sustain, 0.0, release_n))
                envelope = _np.concatenate(parts)[:samples]
            if envelope.size < samples:
                envelope = _np.pad(envelope, (0, samples - envelope.size))
        else:
            envelope = [0.0] * samples
            for i in range(min(attack_n, samples)):
                envelope[i] = i / attack_n
            if voice.percussive:
                span = max(1, samples - attack_n)
                for i in range(attack_n, samples):
                    envelope[i] = math.exp(-4.5 * (i - attack_n) / span)
            else:
                index = attack_n
                for i in range(decay_n):
                    if index >= samples:
                        break
                    envelope[index] = 1.0 + (sustain - 1.0) * (i / decay_n)
                    index += 1
                for _ in range(sustain_n):
                    if index >= samples:
                        break
                    envelope[index] = sustain
                    index += 1
                for i in range(release_n):
                    if index >= samples:
                        break
                    envelope[index] = sustain * (1.0 - i / release_n)
                    index += 1

        self._env_cache[key] = envelope
        return envelope

    def _note_samples(self, voice: Voice, pitch: int, samples: int):
        table = self._wavetable(voice, pitch)
        envelope = self._envelope(voice, samples)
        length = len(table)
        repeats = samples // length + 1

        if self.backend == "numpy":
            body = _np.tile(table, repeats)[:samples]
            return body * envelope
        body = (list(table) * repeats)[:samples]
        return list(map(mul, body, envelope))

    # -- mixing --------------------------------------------------------------

    def render(self, arrangement: Arrangement):
        """Render to a float buffer in the range roughly -1..1."""
        options = self.options
        rate = options.sample_rate
        beats_per_second = max(arrangement.meta.tempo, 1e-6) / 60.0
        total_seconds = arrangement.duration_seconds + options.tail
        total_samples = max(1, int(total_seconds * rate))

        mix = _np.zeros(total_samples, dtype=_np.float64) if self.backend == "numpy" else [0.0] * total_samples

        for track in arrangement.tracks:
            voice = voice_for_program(track.program, track.is_drum)
            for note in track.notes:
                # Arrival, not emission: a render is what the listener hears,
                # so a note goes where its sound gets to them. On a piece with
                # no stage this is the written time, unchanged.
                start = int((note.arrival_time / beats_per_second) * rate)
                if start >= total_samples:
                    continue
                duration_seconds = note.duration / beats_per_second
                samples = int(duration_seconds * rate) + int(voice.release * rate)
                samples = max(2, min(samples, total_samples - start))
                gain = (note.velocity / 127.0) * voice.gain * 0.32
                block = self._note_samples(voice, note.pitch, samples)

                if self.backend == "numpy":
                    mix[start : start + samples] += block * gain
                else:
                    end = start + samples
                    window = mix[start:end]
                    scaled = [value * gain for value in block]
                    mix[start:end] = list(map(add, window, scaled))

        return self._finish(mix)

    def _finish(self, mix):
        options = self.options
        if self.backend == "numpy":
            if options.lowpass:
                # One-pole smoothing knocks the edge off the additive harmonics.
                alpha = 0.72
                filtered = _np.empty_like(mix)
                accumulator = 0.0
                for index, value in enumerate(mix):
                    accumulator = alpha * accumulator + (1.0 - alpha) * value
                    filtered[index] = accumulator
                mix = mix * 0.55 + filtered * 0.45
            peak = float(_np.max(_np.abs(mix))) if mix.size else 0.0
            if peak > 0:
                mix = mix * (options.normalize / peak)
            return mix

        if options.lowpass:
            alpha = 0.72
            inverse = 1.0 - alpha
            accumulator = 0.0
            filtered = [0.0] * len(mix)
            for index, value in enumerate(mix):
                accumulator = alpha * accumulator + inverse * value
                filtered[index] = accumulator
            mix = [raw * 0.55 + smooth * 0.45 for raw, smooth in zip(mix, filtered)]
        peak = max((abs(value) for value in mix), default=0.0)
        if peak > 0:
            scale = options.normalize / peak
            mix = [value * scale for value in mix]
        return mix

    # -- output --------------------------------------------------------------

    def to_wav_bytes(self, arrangement: Arrangement) -> bytes:
        import io

        buffer = io.BytesIO()
        self._write_wave(self.render(arrangement), buffer)
        return buffer.getvalue()

    def write(self, arrangement: Arrangement, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as handle:
            self._write_wave(self.render(arrangement), handle)
        return target

    def _write_wave(self, mix, handle) -> None:
        if self.backend == "numpy":
            clipped = _np.clip(mix, -1.0, 1.0)
            samples = (clipped * 32767.0).astype("<i2").tobytes()
        else:
            pcm = array("h", (max(-32767, min(32767, int(value * 32767.0))) for value in mix))
            if array("h", [1]).tobytes() != b"\x01\x00":  # normalise to little endian
                pcm.byteswap()
            samples = pcm.tobytes()

        with wave.open(handle, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(self.options.sample_rate)
            writer.writeframes(samples)


def write_wav(
    arrangement: Arrangement,
    path: str | Path,
    options: AudioOptions | None = None,
) -> Path:
    """Synthesise *arrangement* to a WAV file and return the path."""
    return Synthesiser(options).write(arrangement, path)
