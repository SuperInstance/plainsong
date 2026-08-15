"""Machine probing.

The compiler runs on stdlib alone. Everything else -- faster synthesis,
soundfont rendering, hardware MIDI, audio playback, format conversion -- is an
optional accelerator that may or may not exist on the machine in front of us.

This module finds out what is actually here, once, and reports it as data. The
CLI prints it (``tapscript doctor``), the renderer picks backends from it, and
the build agent reads it to decide what it can wire up for this user.

Nothing here raises. A probe that fails is a capability that is absent.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Where soundfonts tend to live, per platform. Checked in order.
SOUNDFONT_HINTS = (
    "/usr/share/soundfonts",
    "/usr/share/sounds/sf2",
    "/usr/local/share/soundfonts",
    "/usr/local/share/generaluser-gs",
    "~/.local/share/soundfonts",
    "~/soundfonts",
    "~/Library/Audio/Sounds/Banks",
    "C:/soundfonts",
)

PLAYBACK_COMMANDS = (
    ("ffplay", ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]),
    ("paplay", ["paplay"]),
    ("aplay", ["aplay", "-q"]),
    ("afplay", ["afplay"]),
    ("play", ["play", "-q"]),
)


@dataclass
class Capability:
    """One probed fact about the host."""

    name: str
    present: bool
    detail: str = ""
    kind: str = "optional"  # required | optional | informational
    unlocks: str = ""
    remedy: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "present": self.present,
            "detail": self.detail,
            "kind": self.kind,
            "unlocks": self.unlocks,
            "remedy": self.remedy,
            "data": self.data,
        }


def _module(name: str) -> tuple[bool, str]:
    spec = importlib.util.find_spec(name)
    if spec is None:
        return False, ""
    try:
        module = importlib.import_module(name)
        return True, str(getattr(module, "__version__", "")) or "installed"
    except Exception:  # a broken install is not a usable capability
        return False, ""


def _binary(name: str) -> tuple[bool, str]:
    path = shutil.which(name)
    return (bool(path), path or "")


def probe_python() -> Capability:
    return Capability(
        name="python",
        present=sys.version_info >= (3, 10),
        detail=f"{platform.python_implementation()} {platform.python_version()}",
        kind="required",
        unlocks="the compiler, the CLI, the TUI and the web interface",
        remedy="install Python 3.10 or newer",
        data={
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
    )


def probe_platform() -> Capability:
    return Capability(
        name="platform",
        present=True,
        kind="informational",
        detail=f"{platform.system()} {platform.machine()}",
        data={
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "cpus": os.cpu_count() or 1,
        },
    )


def probe_numpy() -> Capability:
    present, version = _module("numpy")
    return Capability(
        name="numpy",
        present=present,
        detail=version,
        unlocks="vectorised audio synthesis (roughly 20x faster than the pure-Python path)",
        remedy="pip install numpy",
    )


def probe_soundfonts() -> Capability:
    found: list[str] = []
    env_hint = os.environ.get("TAPSCRIPT_SOUNDFONT")
    hints = ([env_hint] if env_hint else []) + list(SOUNDFONT_HINTS)
    for hint in hints:
        directory = Path(hint).expanduser()
        try:
            if directory.is_file() and directory.suffix.lower() in {".sf2", ".sf3"}:
                found.append(str(directory))
                continue
            if not directory.is_dir():
                continue
            for entry in sorted(directory.iterdir()):
                if entry.suffix.lower() in {".sf2", ".sf3"}:
                    found.append(str(entry))
        except OSError:
            continue
    return Capability(
        name="soundfont",
        present=bool(found),
        detail=found[0] if found else "",
        unlocks="instrument-accurate audio via the fluidsynth backend",
        remedy="install a General MIDI soundfont, or set TAPSCRIPT_SOUNDFONT to one",
        data={"found": found[:8]},
    )


def probe_fluidsynth() -> Capability:
    present, path = _binary("fluidsynth")
    return Capability(
        name="fluidsynth",
        present=present,
        detail=path,
        unlocks="high quality audio rendering from a soundfont",
        remedy="install fluidsynth from your package manager",
    )


def probe_ffmpeg() -> Capability:
    present, path = _binary("ffmpeg")
    return Capability(
        name="ffmpeg",
        present=present,
        detail=path,
        unlocks="export to mp3, ogg, flac and m4a",
        remedy="install ffmpeg from your package manager",
    )


def probe_midi_ports() -> Capability:
    present, _ = _module("mido")
    ports: list[str] = []
    if present:
        try:
            import mido  # type: ignore

            ports = list(mido.get_output_names())
        except Exception:
            ports = []
    return Capability(
        name="midi_ports",
        present=bool(ports),
        detail=", ".join(ports[:3]) if ports else "",
        unlocks="playing straight out to a hardware or virtual instrument",
        remedy="pip install mido python-rtmidi, then connect a MIDI device",
        data={"ports": ports},
    )


def probe_playback() -> Capability:
    for name, argv in PLAYBACK_COMMANDS:
        path = shutil.which(name)
        if path:
            return Capability(
                name="audio_playback",
                present=True,
                detail=path,
                unlocks="`tapscript play` straight from the terminal",
                data={"command": argv},
            )
    if sys.platform == "win32":
        return Capability(
            name="audio_playback",
            present=True,
            detail="powershell",
            unlocks="`tapscript play` straight from the terminal",
            data={"command": ["powershell", "-c", "(New-Object Media.SoundPlayer '{path}').PlaySync()"]},
        )
    return Capability(
        name="audio_playback",
        present=False,
        unlocks="`tapscript play` straight from the terminal",
        remedy="install ffmpeg (ffplay), sox (play), or an ALSA/PulseAudio client",
    )


def probe_terminal() -> Capability:
    is_tty = sys.stdout.isatty()
    curses_ok, _ = _module("curses")
    try:
        columns = os.get_terminal_size().columns
    except OSError:
        columns = 80
    return Capability(
        name="terminal",
        present=is_tty,
        kind="informational",
        detail=f"{'interactive' if is_tty else 'non-interactive'}, {columns} columns",
        unlocks="the full-screen TUI",
        remedy="run from an interactive terminal",
        data={
            "tty": is_tty,
            "columns": columns,
            "curses": curses_ok,
            "color": is_tty and os.environ.get("TERM", "") not in {"", "dumb"},
        },
    )


def probe_network() -> Capability:
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
    offline = os.environ.get("TAPSCRIPT_OFFLINE", "").lower() in {"1", "true", "yes"}
    return Capability(
        name="network",
        present=not offline,
        kind="informational",
        detail="offline mode" if offline else (f"proxy {proxy}" if proxy else "direct"),
        unlocks="hosted model providers",
        remedy="unset TAPSCRIPT_OFFLINE to allow outbound calls",
        data={"proxy": proxy, "offline": offline},
    )


def probe_host_agent() -> Capability:
    """Detect that we are running inside someone else's agent session.

    When true, the model can be reached by delegating to the host rather than by
    holding an API key of our own.
    """
    markers = {
        "claude-code": ("CLAUDECODE", "CLAUDE_CODE_SESSION", "CLAUDE_SESSION_ID"),
        "openclaw": ("OPENCLAW_SESSION", "OPENCLAW_WORKSPACE", "OPENCLAW_AGENT"),
        "cursor": ("CURSOR_SESSION_ID",),
        "aider": ("AIDER_CHAT",),
        "generic": ("TAPSCRIPT_HOST_AGENT",),
    }
    for host, env_names in markers.items():
        for env_name in env_names:
            if os.environ.get(env_name):
                return Capability(
                    name="host_agent",
                    present=True,
                    detail=os.environ.get("TAPSCRIPT_HOST_AGENT") or host,
                    unlocks="the `host` provider -- model access borrowed from the surrounding agent, no API key needed",
                    data={"host": host, "via": env_name},
                )
    return Capability(
        name="host_agent",
        present=False,
        kind="informational",
        detail="",
        unlocks="the `host` provider",
        remedy="set TAPSCRIPT_HOST_AGENT when driving this from another agent",
    )


PROBES: tuple[Callable[[], Capability], ...] = (
    probe_python,
    probe_platform,
    probe_terminal,
    probe_network,
    probe_host_agent,
    probe_numpy,
    probe_fluidsynth,
    probe_soundfonts,
    probe_ffmpeg,
    probe_midi_ports,
    probe_playback,
)


class CapabilityReport:
    """The full picture of what this machine can do."""

    def __init__(self, capabilities: list[Capability]) -> None:
        self.capabilities = capabilities
        self._by_name = {cap.name: cap for cap in capabilities}

    def __iter__(self):
        return iter(self.capabilities)

    def __getitem__(self, name: str) -> Capability:
        return self._by_name[name]

    def has(self, name: str) -> bool:
        cap = self._by_name.get(name)
        return bool(cap and cap.present)

    def detail(self, name: str) -> str:
        cap = self._by_name.get(name)
        return cap.detail if cap else ""

    def get(self, name: str) -> Capability | None:
        return self._by_name.get(name)

    def missing(self, kind: str | None = None) -> list[Capability]:
        return [
            cap
            for cap in self.capabilities
            if not cap.present and cap.kind != "informational" and (kind is None or cap.kind == kind)
        ]

    def as_dict(self) -> dict[str, Any]:
        return {cap.name: cap.as_dict() for cap in self.capabilities}

    def summary(self) -> str:
        available = sum(1 for cap in self.capabilities if cap.present)
        return f"{available}/{len(self.capabilities)} capabilities available"


_cached: CapabilityReport | None = None


def probe(refresh: bool = False) -> CapabilityReport:
    """Probe the host. Cached for the life of the process unless *refresh*."""
    global _cached
    if _cached is not None and not refresh:
        return _cached
    results: list[Capability] = []
    for probe_fn in PROBES:
        try:
            results.append(probe_fn())
        except Exception as exc:  # a probe must never break the program
            results.append(
                Capability(
                    name=getattr(probe_fn, "__name__", "unknown").replace("probe_", ""),
                    present=False,
                    detail=f"probe failed: {exc}",
                )
            )
    _cached = CapabilityReport(results)
    return _cached
