from __future__ import annotations

import gc
import importlib.util
import tempfile
import unittest
from pathlib import Path

# The chunked renderer needs NumPy by design, and this file used to import both
# numpy and pytest at module scope. CI's stdlib-only job has neither and runs
# `unittest discover`, which imports every test module -- so an absent
# dependency became a collection error that took the whole run down rather than
# a skip. `unittest.SkipTest` is understood by unittest and pytest alike and
# needs neither package installed.
# Nothing here calls NumPy directly -- `write_wav_chunked` does -- so this asks
# whether it is installed rather than binding a name it would not use.
if importlib.util.find_spec("numpy") is None:  # pragma: no cover
    raise unittest.SkipTest("the chunked renderer requires NumPy")

from plainsong.notation.ir import Arrangement, Metadata, Note, Track
from plainsong.render.audio import AudioOptions, write_wav
from plainsong.render.chunked import write_wav_chunked


def _make_arrangement(duration_beats: float = 4.0) -> Arrangement:
    """Minimal arrangement: one C4 quarter note per beat."""
    meta = Metadata(tempo=120.0)
    track = Track(name="piano", program=0)
    beat = 1.0
    for i in range(int(duration_beats)):
        track.notes.append(Note(start=i * beat, duration=beat, pitch=60, velocity=80))
    return Arrangement(meta=meta, tracks=[track])


def test_bit_identical():
    """Chunked output must be byte-identical to the full-buffer path."""
    arr = _make_arrangement(8)
    with tempfile.TemporaryDirectory() as tmp:
        ref = Path(tmp) / "ref.wav"
        chk = Path(tmp) / "chk.wav"
        write_wav(arr, ref)
        write_wav_chunked(arr, chk)
        assert ref.read_bytes() == chk.read_bytes(), "WAV files differ"
    print("PASS: byte-identical")


def test_bounded_memory():
    """60-second arrangement must not hold total_samples in memory at once."""
    arr = _make_arrangement(duration_beats=120.0)  # 120 beats @ 120bpm = 60s
    opts = AudioOptions(sample_rate=44100)
    total_samples = 60 * 44100

    gc.collect()
    import tracemalloc

    tracemalloc.start()
    with tempfile.TemporaryDirectory() as tmp:
        write_wav_chunked(arr, Path(tmp) / "out.wav", chunk_samples=4096, options=opts)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Peak should be well under total_samples * 8 bytes (f64)
    limit = total_samples * 8  # full-buffer cost
    assert peak < limit, f"Peak memory {peak} >= full-buffer cost {limit} (samples={total_samples})"
    print(f"PASS: bounded — peak {peak} bytes < {limit} (60s @ 44100Hz)")


def test_smoke_duration():
    """Quick smoke: confirm WAV duration matches expectation."""
    arr = _make_arrangement(4)  # 4 beats @ 120bpm = 2s + 1.2s tail
    opts = AudioOptions(sample_rate=44100, tail=1.2)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "smoke.wav"
        write_wav_chunked(arr, p, options=opts)
        import wave

        with wave.open(str(p)) as w:
            frames = w.getnframes()
            rate = w.getframerate()
            dur = frames / rate
    expected = 2.0 + 1.2  # duration_seconds + tail
    assert abs(dur - expected) < 0.01, f"duration {dur} != expected {expected}"
    print(f"PASS: duration {dur:.3f}s (expected ~{expected}s)")
