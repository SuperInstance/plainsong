"""Optional rendering backends.

The built-in synthesiser always works. When the machine has better tools
installed, these wrappers use them: fluidsynth for soundfont-quality audio,
ffmpeg for compressed formats, whatever audio player is present for playback.

Every function degrades honestly -- it reports what it could not do instead of
failing silently or pretending a file was written.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..runtime.capabilities import CapabilityReport, probe

AUDIO_FORMATS = {
    "wav": [],
    "mp3": ["-codec:a", "libmp3lame", "-q:a", "2"],
    "ogg": ["-codec:a", "libvorbis", "-q:a", "5"],
    "flac": ["-codec:a", "flac"],
    "m4a": ["-codec:a", "aac", "-b:a", "192k"],
}


@dataclass
class BackendResult:
    """What a backend managed to do."""

    ok: bool
    backend: str
    path: Path | None = None
    message: str = ""

    def __bool__(self) -> bool:
        return self.ok


def _run(argv: list[str], timeout: int = 300) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return False, f"{argv[0]} is not installed"
    except subprocess.TimeoutExpired:
        return False, f"{argv[0]} timed out after {timeout}s"
    except OSError as exc:
        return False, f"{argv[0]} failed to start: {exc}"
    if completed.returncode != 0:
        tail = completed.stdout.decode("utf-8", "replace").strip().splitlines()
        return False, (tail[-1] if tail else f"{argv[0]} exited {completed.returncode}")
    return True, ""


def audio_backends(report: CapabilityReport | None = None) -> list[str]:
    """Audio backends usable on this machine, best first."""
    report = report or probe()
    backends = []
    if report.has("fluidsynth") and report.has("soundfont"):
        backends.append("fluidsynth")
    backends.append("builtin")
    return backends


def choose_audio_backend(preference: str = "auto", report: CapabilityReport | None = None) -> str:
    available = audio_backends(report)
    if preference in ("auto", "", None):
        return available[0]
    if preference in available:
        return preference
    return "builtin"


def render_with_fluidsynth(
    midi_path: str | Path,
    wav_path: str | Path,
    soundfont: str | None = None,
    sample_rate: int = 44100,
    report: CapabilityReport | None = None,
) -> BackendResult:
    """Render a MIDI file to WAV through fluidsynth."""
    report = report or probe()
    if not report.has("fluidsynth"):
        return BackendResult(False, "fluidsynth", message="fluidsynth is not installed")
    font = soundfont or report.detail("soundfont")
    if not font:
        return BackendResult(False, "fluidsynth", message="no soundfont found")

    target = Path(wav_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ok, message = _run(
        [
            "fluidsynth",
            "-ni",
            "-g",
            "0.8",
            "-r",
            str(sample_rate),
            "-F",
            str(target),
            str(font),
            str(midi_path),
        ]
    )
    if not ok:
        return BackendResult(False, "fluidsynth", message=message)
    if not target.exists() or target.stat().st_size == 0:
        return BackendResult(False, "fluidsynth", message="fluidsynth produced no audio")
    return BackendResult(True, "fluidsynth", path=target)


def convert_audio(source: str | Path, target: str | Path) -> BackendResult:
    """Convert audio between formats with ffmpeg."""
    target_path = Path(target)
    suffix = target_path.suffix.lstrip(".").lower()
    if suffix not in AUDIO_FORMATS:
        return BackendResult(False, "ffmpeg", message=f"unsupported format: .{suffix}")
    if suffix == "wav":
        shutil.copyfile(source, target_path)
        return BackendResult(True, "copy", path=target_path)
    if not shutil.which("ffmpeg"):
        return BackendResult(
            False, "ffmpeg", message="ffmpeg is not installed, so only .wav can be written"
        )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    ok, message = _run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), *AUDIO_FORMATS[suffix], str(target_path)]
    )
    if not ok:
        return BackendResult(False, "ffmpeg", message=message)
    return BackendResult(True, "ffmpeg", path=target_path)


def play_audio(path: str | Path, report: CapabilityReport | None = None) -> BackendResult:
    """Play an audio file through whatever this machine has."""
    report = report or probe()
    capability = report.get("audio_playback")
    if not capability or not capability.present:
        return BackendResult(
            False,
            "none",
            message="no audio player found (install ffmpeg, sox, or an ALSA/PulseAudio client)",
        )
    argv = [part.format(path=str(path)) for part in capability.data.get("command", [])]
    if not argv:
        return BackendResult(False, "none", message="no playback command available")
    if "{path}" not in " ".join(capability.data.get("command", [])):
        argv = argv + [str(path)]
    ok, message = _run(argv, timeout=900)
    return BackendResult(ok, capability.detail or "player", path=Path(path), message=message)


def send_to_midi_port(midi_path: str | Path, port: str | None = None) -> BackendResult:
    """Stream a MIDI file to a hardware or virtual port via mido, if present."""
    try:
        import mido  # type: ignore
    except ImportError:
        return BackendResult(False, "mido", message="pip install mido python-rtmidi to play to a MIDI port")
    try:
        names = mido.get_output_names()
        if not names:
            return BackendResult(False, "mido", message="no MIDI output ports are open")
        chosen = port or names[0]
        midi_file = mido.MidiFile(str(midi_path))
        with mido.open_output(chosen) as output:
            for message in midi_file.play():
                output.send(message)
        return BackendResult(True, "mido", path=Path(midi_path), message=f"played to {chosen}")
    except Exception as exc:  # hardware paths fail in many ways
        return BackendResult(False, "mido", message=str(exc))
