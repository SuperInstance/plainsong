"""The connectors that ship with the system.

Four, covering what most setups need: write files, play audio, play to a MIDI
instrument, post somewhere over HTTP. Generated connectors sit alongside these
and are treated no differently.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

from ..notation.ir import Arrangement
from ..render.audio import AudioOptions, Synthesiser
from ..render.midi import write_midi
from .base import Connector, ConnectorResult, registry


@registry.register
class FileConnector(Connector):
    """Write MIDI and audio to a directory."""

    name = "file"
    summary = "Write MIDI and audio files to a directory"

    def send(self, arrangement: Arrangement, **options: Any) -> ConnectorResult:
        directory = Path(options.get("directory") or self.config.paths.output_dir)
        stem = str(options.get("name") or arrangement.meta.title or "tapscript").strip() or "tapscript"
        stem = stem.lower().replace(" ", "-")
        directory.mkdir(parents=True, exist_ok=True)

        outputs = [str(write_midi(arrangement, directory / f"{stem}.mid"))]
        if options.get("audio", True):
            synth = Synthesiser(
                AudioOptions(sample_rate=int(self.config.get("render", "sample_rate", 44100)))
            )
            outputs.append(str(synth.write(arrangement, directory / f"{stem}.wav")))
        return ConnectorResult(True, detail=f"wrote {len(outputs)} file(s)", outputs=outputs)


@registry.register
class PlaybackConnector(Connector):
    """Render and play through the machine's audio output."""

    name = "playback"
    summary = "Play the piece through this machine's speakers"
    requires = ("audio_playback",)

    def send(self, arrangement: Arrangement, **options: Any) -> ConnectorResult:
        from ..render.backends import play_audio

        target = Path(options.get("path") or self.config.paths.output_dir / "playback.wav")
        synth = Synthesiser(
            AudioOptions(sample_rate=int(self.config.get("render", "sample_rate", 44100)))
        )
        synth.write(arrangement, target)
        outcome = play_audio(target)
        return ConnectorResult(outcome.ok, detail=outcome.message or "played", outputs=[str(target)])


@registry.register
class MidiPortConnector(Connector):
    """Stream to a hardware or virtual MIDI instrument."""

    name = "midi-port"
    summary = "Play to a connected MIDI instrument"
    requires = ("midi_ports",)

    def send(self, arrangement: Arrangement, **options: Any) -> ConnectorResult:
        from ..render.backends import send_to_midi_port

        target = Path(options.get("path") or self.config.paths.output_dir / "port.mid")
        write_midi(arrangement, target)
        outcome = send_to_midi_port(target, options.get("port"))
        return ConnectorResult(outcome.ok, detail=outcome.message, outputs=[str(target)])


@registry.register
class WebhookConnector(Connector):
    """POST a summary, and optionally the MIDI, to an HTTP endpoint."""

    name = "webhook"
    summary = "POST the arrangement to a URL"
    requires = ("network",)

    def send(self, arrangement: Arrangement, **options: Any) -> ConnectorResult:
        url = str(options.get("url") or "").strip()
        if not url:
            return ConnectorResult(False, detail="no url given")

        payload: dict[str, Any] = {
            "title": arrangement.meta.title,
            "key": arrangement.meta.key.name(),
            "tempo": arrangement.meta.tempo,
            "summary": arrangement.summary(),
        }
        if options.get("include_midi"):
            import base64

            from ..render.midi import midi_bytes

            payload["midi_base64"] = base64.b64encode(midi_bytes(arrangement)).decode("ascii")

        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", **dict(options.get("headers") or {})}
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=int(options.get("timeout", 30))) as response:
                status = response.status
        except Exception as exc:
            return ConnectorResult(False, detail=f"{type(exc).__name__}: {exc}")
        return ConnectorResult(200 <= status < 300, detail=f"HTTP {status}", data={"status": status})
