"""The one call that turns notation into files.

Every interface -- CLI, TUI, web, agent tools -- goes through here, so they
cannot drift apart in what "compile" means.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .notation import parse
from .notation.arrange import ArrangeOptions, arrange
from .notation.ir import Arrangement, Diagnostic, Score
from .render import backends
from .render.audio import AudioOptions, Synthesiser
from .render.midi import write_midi
from .runtime.capabilities import CapabilityReport, probe
from .runtime.config import Config, load_config

SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, fallback: str = "untitled") -> str:
    slug = SLUG_RE.sub("-", text.strip().lower()).strip("-")
    return slug[:60] or fallback


@dataclass
class CompileResult:
    """Everything a caller might want to know about one compilation."""

    score: Score
    arrangement: Arrangement | None = None
    midi_path: Path | None = None
    audio_path: Path | None = None
    audio_backend: str = ""
    elapsed: dict[str, float] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)

    @property
    def diagnostics(self) -> list[Diagnostic]:
        source = self.arrangement.diagnostics if self.arrangement else self.score.diagnostics
        return list(source)

    @property
    def ok(self) -> bool:
        return not self.score.has_errors

    def summary(self) -> dict[str, Any]:
        data: dict[str, Any] = {"score": self.score.summary()}
        if self.arrangement:
            data["arrangement"] = self.arrangement.summary()
        if self.midi_path:
            data["midi"] = str(self.midi_path)
        if self.audio_path:
            data["audio"] = str(self.audio_path)
            data["audio_backend"] = self.audio_backend
        if self.arrangement is not None and self.arrangement.stage is not None:
            data["stage"] = self.arrangement.stage.as_dict()
            data["frame"] = self.arrangement.frame
        data["elapsed"] = {key: round(value, 3) for key, value in self.elapsed.items()}
        data["diagnostics"] = [diag.as_dict() for diag in self.diagnostics]
        return data

    def describe(self) -> str:
        score = self.score.summary()
        lines = [
            f"{score['title']}  --  {score['key']}, {score['tempo']:g} bpm, {score['meter']}",
            f"{score['sections']} sections, dialect: {score['dialect']}",
        ]
        if self.arrangement:
            arrangement = self.arrangement.summary()
            voices = ", ".join(f"{t['name']} ({t['notes']})" for t in arrangement["tracks"]) or "none"
            lines.append(f"{arrangement['notes']} notes across {voices}")
            lines.append(f"length {arrangement['seconds']:g}s")
        if self.arrangement is not None and self.arrangement.stage is not None:
            stage = self.arrangement.stage
            state = "compensated" if stage.compensate else "uncompensated"
            lines.append(
                f"stage: {len(stage.placements)} placed, heard at "
                f"{self.arrangement.frame or stage.listener} ({state})"
            )
        if self.midi_path:
            lines.append(f"midi  {self.midi_path}")
        if self.audio_path:
            lines.append(f"audio {self.audio_path}  [{self.audio_backend}]")
        return "\n".join(lines)


def _arrange_options(config: Config, overrides: dict[str, Any] | None = None) -> ArrangeOptions:
    render = config.section("render")
    core = config.section("core")
    options = ArrangeOptions(
        bar_fill=core.get("bar_fill", "rescale"),
        humanize=bool(render.get("humanize", True)),
        humanize_seed=int(render.get("humanize_seed", 42)),
        humanize_velocity=int(render.get("humanize_velocity", 6)),
        swing=None,
    )
    for key, value in (overrides or {}).items():
        if value is not None and hasattr(options, key):
            setattr(options, key, value)
    return options


def default_output_path(score: Score, suffix: str, config: Config) -> Path:
    """Pick a stable output name: the title if there is one, else a digest."""
    title = score.meta.title or Path(score.path).stem if score.path else score.meta.title
    if title:
        stem = slugify(title)
    else:
        stem = "plainsong-" + hashlib.sha256(score.source.encode("utf-8")).hexdigest()[:8]
    return config.paths.output_dir / f"{stem}{suffix}"


def compile_text(
    text: str,
    *,
    midi: str | Path | None = None,
    audio: str | Path | None = None,
    config: Config | None = None,
    dialect: str = "auto",
    path: str = "",
    arrange_overrides: dict[str, Any] | None = None,
    audio_backend: str = "auto",
    soundfont: str | None = None,
    report: CapabilityReport | None = None,
    frame: str = "",
    compensate: bool | None = None,
) -> CompileResult:
    """Parse, arrange and optionally write MIDI and audio.

    Passing ``midi=True``-like sentinel paths is not supported on purpose: pass
    a real path, or ``None`` to skip that output.

    *frame* and *compensate* only matter for a piece that declares a ``[Stage]``
    block: the first chooses whose ears the arrival times are solved for, the
    second can turn the correction off so the render smears the way an
    uncorrected ensemble does. See ``docs/performance.md``.
    """
    config = config or load_config()
    if frame or compensate is not None:
        arrange_overrides = dict(arrange_overrides or {})
        arrange_overrides.setdefault("frame", frame)
        if compensate is not None:
            arrange_overrides.setdefault("compensate", compensate)
    report = report or probe()
    elapsed: dict[str, float] = {}

    started = time.perf_counter()
    score = parse(text, dialect=dialect or config.get("core", "dialect", "auto"), path=path)
    elapsed["parse"] = time.perf_counter() - started

    result = CompileResult(score=score, elapsed=elapsed)
    if score.has_errors:
        return result

    started = time.perf_counter()
    arrangement = arrange(score, _arrange_options(config, arrange_overrides))
    elapsed["arrange"] = time.perf_counter() - started
    result.arrangement = arrangement

    if arrangement.note_count == 0:
        result.messages.append("nothing to render: the arrangement contains no notes")

    if midi is not None:
        started = time.perf_counter()
        result.midi_path = write_midi(
            arrangement, midi, ticks_per_beat=int(config.get("render", "ticks_per_beat", 480))
        )
        elapsed["midi"] = time.perf_counter() - started

    if audio is not None:
        started = time.perf_counter()
        result.audio_path, result.audio_backend, message = _render_audio(
            arrangement=arrangement,
            audio=Path(audio),
            config=config,
            preference=audio_backend,
            soundfont=soundfont,
            report=report,
            midi_path=result.midi_path,
        )
        elapsed["audio"] = time.perf_counter() - started
        if message:
            result.messages.append(message)

    return result


def _render_audio(
    arrangement: Arrangement,
    audio: Path,
    config: Config,
    preference: str,
    soundfont: str | None,
    report: CapabilityReport,
    midi_path: Path | None,
) -> tuple[Path | None, str, str]:
    """Render audio with the best available backend, falling back in order."""
    requested_format = audio.suffix.lstrip(".").lower() or "wav"
    wav_target = audio if requested_format == "wav" else audio.with_suffix(".wav")
    chosen = backends.choose_audio_backend(
        preference or config.get("render", "audio_backend", "auto"), report
    )
    message = ""

    if chosen == "fluidsynth":
        source_midi = midi_path
        temporary: Path | None = None
        if source_midi is None:
            temporary = wav_target.with_suffix(".render.mid")
            source_midi = write_midi(arrangement, temporary)
        outcome = backends.render_with_fluidsynth(
            source_midi,
            wav_target,
            soundfont=soundfont,
            sample_rate=int(config.get("render", "sample_rate", 44100)),
            report=report,
        )
        if temporary and temporary.exists():
            temporary.unlink(missing_ok=True)
        if outcome.ok:
            return _finish_audio(wav_target, audio, requested_format, "fluidsynth")
        message = f"fluidsynth unavailable ({outcome.message}); used the built-in synthesiser"
        chosen = "builtin"

    options = AudioOptions(
        sample_rate=int(config.get("render", "sample_rate", 44100)),
        normalize=float(config.get("render", "normalize", 0.89)),
    )
    synth = Synthesiser(options)
    synth.write(arrangement, wav_target)
    path, backend, convert_message = _finish_audio(
        wav_target, audio, requested_format, f"builtin/{synth.backend}"
    )
    return path, backend, message or convert_message


def _finish_audio(
    wav_target: Path, audio: Path, requested_format: str, backend: str
) -> tuple[Path | None, str, str]:
    if requested_format == "wav":
        return wav_target, backend, ""
    outcome = backends.convert_audio(wav_target, audio)
    if outcome.ok:
        wav_target.unlink(missing_ok=True)
        return outcome.path, backend, ""
    return wav_target, backend, f"kept .wav ({outcome.message})"


def compile_file(
    source: str | Path,
    *,
    midi: str | Path | None = None,
    audio: str | Path | None = None,
    config: Config | None = None,
    **kwargs: Any,
) -> CompileResult:
    """Compile a notation file from disk."""
    source_path = Path(source)
    text = source_path.read_text(encoding="utf-8")
    return compile_text(text, midi=midi, audio=audio, config=config, path=str(source_path), **kwargs)
