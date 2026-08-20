"""Bounded-memory chunked WAV renderer.

Streams synthesis in fixed-size chunks so peak memory is O(chunk + longest_note),
not O(total_samples). Produces byte-identical output to ``write_wav``.
Requires NumPy.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from ..notation.ir import Arrangement, Note, Track
from .audio import AudioOptions, Synthesiser, midi_to_hz
from .voices import Voice, voice_for_program


def _note_info(
    track: Track, note: Note, voice: Voice, rate: int, bps: float, total_samples: int
) -> tuple[int, int, float] | None:
    """Return (start_sample, num_samples, gain) or None if note is past end."""
    start = int((note.arrival_time / bps) * rate)
    if start >= total_samples:
        return None
    dur_s = note.duration / bps
    samples = int(dur_s * rate) + int(voice.release * rate)
    samples = max(2, min(samples, total_samples - start))
    gain = (note.velocity / 127.0) * voice.gain * 0.32
    return start, samples, gain


def _add_note_to_chunk(
    buf: np.ndarray,
    note_start: int,
    block: np.ndarray,
    gain: float,
    chunk_start: int,
    chunk_end: int,
) -> None:
    note_end = note_start + block.shape[0]
    ov_s = max(note_start, chunk_start)
    ov_e = min(note_end, chunk_end)
    if ov_s >= ov_e:
        return
    buf[ov_s - chunk_start : ov_e - chunk_start] += (
        block[ov_s - note_start : ov_e - note_start] * gain
    )


def write_wav_chunked(
    arrangement: Arrangement,
    path: str | Path,
    *,
    chunk_samples: int = 4096,
    options: AudioOptions | None = None,
) -> None:
    """Render *arrangement* to a WAV file using bounded memory.

    Two-pass: first pass finds global peak after lowpass (needed for
    normalisation), second pass writes. Peak memory is O(chunk_samples + longest_note).
    """
    opts = options or AudioOptions()
    synth = Synthesiser(opts)
    if synth.backend != "numpy":
        synth.backend = "numpy"

    rate = opts.sample_rate
    bps = max(arrangement.meta.tempo, 1e-6) / 60.0
    total_seconds = arrangement.duration_seconds + opts.tail
    total_samples = max(1, int(total_seconds * rate))
    do_lp = opts.lowpass
    alpha = 0.72

    # Pre-compute note metadata (tiny) but NOT the audio blocks.
    # We synthesize each note's audio on-demand when it overlaps a chunk.
    note_meta: list[tuple[int, int, float, Voice, int]] = []
    for track in arrangement.tracks:
        voice = voice_for_program(track.program, track.is_drum)
        for note in track.notes:
            info = _note_info(track, note, voice, rate, bps, total_samples)
            if info is None:
                continue
            note_meta.append((*info, voice, note.pitch))

    # Sort by start so we can skip notes that haven't begun
    note_meta.sort(key=lambda x: x[0])
    # (start, samples, gain, voice, pitch)

    def _process_chunk(s: int, e: int, acc: float) -> tuple[np.ndarray, float]:
        length = e - s
        buf = np.zeros(length, dtype=np.float64)
        for ns, nsamples, gain, voice, pitch in note_meta:
            ne = ns + nsamples
            if ns >= e:
                break  # sorted, rest are even later
            if ne <= s:
                continue  # note ended before this chunk
            block = np.asarray(
                synth._note_samples(voice, pitch, nsamples), dtype=np.float64
            )
            _add_note_to_chunk(buf, ns, block, gain, s, e)
        if do_lp:
            filtered = np.empty_like(buf)
            for i in range(length):
                acc = alpha * acc + (1.0 - alpha) * buf[i]
                filtered[i] = acc
            buf = buf * 0.55 + filtered * 0.45
        return buf, acc

    # Pass 1: find global peak
    peak = 0.0
    acc = 0.0
    for s in range(0, total_samples, chunk_samples):
        e = min(s + chunk_samples, total_samples)
        chunk, acc = _process_chunk(s, e, acc)
        p = float(np.max(np.abs(chunk)))
        if p > peak:
            peak = p
    scale = (opts.normalize / peak) if peak > 0 else 1.0

    # Pass 2: write
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        acc = 0.0
        for s in range(0, total_samples, chunk_samples):
            e = min(s + chunk_samples, total_samples)
            chunk, acc = _process_chunk(s, e, acc)
            chunk *= scale
            clipped = np.clip(chunk, -1.0, 1.0)
            pcm = (clipped * 32767.0).astype("<i2").tobytes()
            writer.writeframes(pcm)
