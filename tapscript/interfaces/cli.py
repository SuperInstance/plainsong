"""The command line.

``tapscript --help`` is the map. Commands are grouped by what you came to do:
work with notation, look at the machine, connect a model, or run an interface.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from ..runtime.config import Config, load_config
from ..version import __version__

STARTER = """**TRACK: {title}**
[MetaData]
key: Am | tempo: 96 | swing: 0% | subdivision: 8th
time: 4/4 | mood: Open

[V1] (Verse - 4 Bars)
Chords: | Am . . . | F . . . | C . . . | G . . . |
Melody: | A4 . C5 E5 | F4 . A4 C5 | E4 . G4 C5 | D4 . F4 B4 |
Lyrics: | write the words | one bar at a time | the bar divides | itself |
@bass   | a1 . e2 . | f1 . c2 . | c1 . g1 . | g1 . d2 . | vel: 70

[CH] (Chorus - 4 Bars)
Chords: | F . . . | G . . . | Am . . . | Am . . . |
Melody: | F4 . A4 C5 | G4 . B4 D5 | A4 . C5 E5 | A4 . . . |
@bass   | f1 . c2 . | g1 . d2 . | a1 . e2 . | a1 . . . | vel: 74
"""


# --------------------------------------------------------------------------
# output helpers
# --------------------------------------------------------------------------


def _colour_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TAPSCRIPT_COLOR", "").lower() in {"0", "false", "never"}:
        return False
    return sys.stdout.isatty()


class Out:
    """Terminal output with a consistent shape."""

    def __init__(self, quiet: bool = False, json_mode: bool = False) -> None:
        self.quiet = quiet
        self.json_mode = json_mode
        self.colour = _colour_enabled() and not json_mode

    def _paint(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.colour else text

    def say(self, text: str = "") -> None:
        if not self.quiet and not self.json_mode:
            print(text)

    def head(self, text: str) -> None:
        self.say(self._paint(text, "1"))

    def dim(self, text: str) -> None:
        self.say(self._paint(text, "2"))

    def ok(self, text: str) -> None:
        self.say(f"{self._paint('ok', '32')}  {text}")

    def warn(self, text: str) -> None:
        self.say(f"{self._paint('warn', '33')}  {text}")

    def fail(self, text: str) -> None:
        print(f"{self._paint('error', '31')}  {text}", file=sys.stderr)

    def data(self, payload: Any) -> None:
        if self.json_mode:
            print(json.dumps(payload, indent=2, default=str))

    def table(self, rows: list[tuple[str, ...]], gap: str = "  ") -> None:
        if not rows or self.json_mode:
            return
        widths = [max(len(str(row[i])) for row in rows) for i in range(len(rows[0]))]
        for row in rows:
            line = gap.join(str(cell).ljust(widths[index]) for index, cell in enumerate(row))
            self.say("  " + line.rstrip())


def _diagnostics(out: Out, diagnostics: list, path: str = "", limit: int = 20) -> None:
    shown = [diag for diag in diagnostics if diag.severity in ("error", "warning")]
    if not shown:
        return
    out.say()
    for diag in shown[:limit]:
        painter = out.fail if diag.severity == "error" else out.warn
        painter(diag.format(path))
    if len(shown) > limit:
        out.dim(f"  ... and {len(shown) - limit} more")


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_compile(args: argparse.Namespace, config: Config, out: Out) -> int:
    from ..pipeline import compile_file, default_output_path

    source = Path(args.file)
    if not source.exists():
        out.fail(f"no such file: {source}")
        return 2

    from ..notation import parse

    score = parse(source.read_text(encoding="utf-8"), path=str(source))
    midi_path = Path(args.midi) if args.midi else default_output_path(score, ".mid", config)
    audio_path: Path | None = None
    if args.audio or args.play:
        audio_path = Path(args.audio) if args.audio else default_output_path(score, ".wav", config)

    result = compile_file(
        source,
        midi=None if args.no_midi else midi_path,
        audio=audio_path,
        config=config,
        dialect=args.dialect,
        audio_backend=args.backend,
        soundfont=args.soundfont,
        arrange_overrides={"transpose": args.semitones} if args.semitones else None,
        frame=args.frame,
        compensate=False if args.no_compensate else None,
    )

    if not result.ok:
        _diagnostics(out, result.diagnostics, str(source))
        out.fail("compilation failed")
        return 1

    out.data(result.summary())
    out.say(result.describe())
    for message in result.messages:
        out.warn(message)
    if not args.quiet:
        _diagnostics(out, result.diagnostics, str(source), limit=8 if not args.verbose else 100)

    if args.play and result.audio_path:
        from ..render.backends import play_audio

        out.say()
        out.dim(f"playing {result.audio_path.name} ...")
        outcome = play_audio(result.audio_path)
        if not outcome.ok:
            out.warn(outcome.message)
    return 0


def cmd_play(args: argparse.Namespace, config: Config, out: Out) -> int:
    from ..pipeline import compile_file, default_output_path
    from ..render.backends import play_audio, send_to_midi_port

    source = _resolve_notation(args.file, config, out)
    if source is None:
        return 2

    if args.port is not None:
        midi_path = config.paths.output_dir / f"{source.stem}.mid"
        compile_file(source, midi=midi_path, config=config)
        outcome = send_to_midi_port(midi_path, args.port or None)
        (out.ok if outcome.ok else out.fail)(outcome.message or str(midi_path))
        return 0 if outcome.ok else 1

    from ..notation import parse

    score = parse(source.read_text(encoding="utf-8"), path=str(source))
    audio_path = default_output_path(score, ".wav", config)
    result = compile_file(source, audio=audio_path, config=config, audio_backend=args.backend)
    if not result.ok:
        _diagnostics(out, result.diagnostics, str(source))
        return 1
    out.say(result.describe())
    outcome = play_audio(result.audio_path)
    if not outcome.ok:
        out.fail(outcome.message)
        return 1
    return 0


def cmd_info(args: argparse.Namespace, config: Config, out: Out) -> int:
    from ..transform import describe

    source = _resolve_notation(args.file, config, out)
    if source is None:
        return 2
    summary = describe(source.read_text(encoding="utf-8"), dialect=args.dialect)
    out.data(summary)

    out.head(summary["title"])
    rows = [
        ("key", summary["key"]),
        ("tempo", f"{summary['tempo']:g} bpm"),
        ("metre", summary["meter"]),
        ("dialect", summary["dialect"]),
        ("sections", str(summary["sections"])),
        ("bars", str(summary["bars"])),
    ]
    if "arrangement" in summary:
        arrangement = summary["arrangement"]
        rows.append(("length", f"{arrangement['seconds']:g}s"))
        rows.append(("notes", str(arrangement["notes"])))
        rows.append(
            ("voices", ", ".join(f"{t['name']} ({t['instrument']})" for t in arrangement["tracks"]))
        )
    out.table(rows)

    from ..notation import parse

    score = parse(source.read_text(encoding="utf-8"), dialect=args.dialect)
    _diagnostics(out, score.diagnostics, str(source), limit=100 if args.verbose else 10)
    return 0


def cmd_check(args: argparse.Namespace, config: Config, out: Out) -> int:
    from ..notation import arrange, parse

    targets: list[Path] = []
    for name in args.files:
        path = Path(name)
        targets.extend(sorted(path.rglob("*.tap")) if path.is_dir() else [path])
    if not targets:
        out.fail("nothing to check")
        return 2

    failures = warnings = 0
    for target in targets:
        try:
            score = parse(target.read_text(encoding="utf-8"), path=str(target))
        except OSError as exc:
            out.fail(f"{target}: {exc}")
            failures += 1
            continue
        if score.has_errors:
            failures += 1
            _diagnostics(out, score.errors(), str(target))
        else:
            arrangement = arrange(score)
            if arrangement.note_count == 0:
                warnings += 1
                out.warn(f"{target}: parses, but produces no notes")
            elif args.verbose:
                out.ok(f"{target}: {arrangement.note_count} notes")
        warnings += len(score.warnings())
        if args.strict:
            _diagnostics(out, score.warnings(), str(target), limit=5)

    out.say()
    checked = len(targets)
    if failures:
        out.fail(f"{failures} of {checked} files have errors ({warnings} warnings)")
        return 1
    out.ok(f"{checked} file(s) checked, {warnings} warning(s)")
    return 0


def cmd_ensemble(args: argparse.Namespace, config: Config, out: Out) -> int:
    from ..notation import parse
    from ..notation.arrange import ArrangeOptions, arrange
    from ..perform.solve import analyse, format_report

    source = _resolve_notation(args.file, config, out)
    if source is None:
        return 2

    score = parse(source.read_text(encoding="utf-8"), dialect=args.dialect, path=str(source))
    if score.has_errors:
        _diagnostics(out, score.errors(), str(source))
        return 1
    if score.meta.stage is None:
        out.data({"stage": False})
        out.warn(f"{source} declares no [Stage] block, so every voice is heard where it is written")
        out.dim("add one to say where the players are -- see docs/performance.md")
        return 0

    options = ArrangeOptions(frame=args.frame, compensate=False if args.no_compensate else None)
    report = analyse(arrange(score, options), frame=args.frame)
    out.data(report)
    out.say(format_report(report))
    return 0


def cmd_transpose(args: argparse.Namespace, config: Config, out: Out) -> int:
    from ..transform import transpose

    source = _resolve_notation(args.file, config, out)
    if source is None:
        return 2
    target_key: str | int = args.key
    if args.key.lstrip("+-").isdigit():
        target_key = int(args.key)
    moved = transpose(source.read_text(encoding="utf-8"), target_key)

    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(moved, encoding="utf-8")
        out.ok(f"wrote {target}")
    elif args.in_place:
        source.write_text(moved, encoding="utf-8")
        out.ok(f"rewrote {source}")
    else:
        print(moved)
    return 0


def cmd_new(args: argparse.Namespace, config: Config, out: Out) -> int:
    title = args.title or "New Piece"
    target = Path(args.output) if args.output else Path(f"{title.lower().replace(' ', '-')}.tap")
    if target.exists() and not args.force:
        out.fail(f"{target} already exists (use --force to overwrite)")
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(STARTER.format(title=title), encoding="utf-8")
    out.ok(f"wrote {target}")
    out.dim(f"next: tapscript compile {target} --audio out.wav")
    return 0


def cmd_library(args: argparse.Namespace, config: Config, out: Out) -> int:
    from ..library import Library

    library = Library(paths=config.paths)
    if args.refresh:
        library.refresh()

    if args.collections:
        rows = [(name, str(count)) for name, count in library.collections().items()]
        out.data(library.collections())
        out.table(rows or [("(none)", "")])
        return 0

    entries = library.search(args.query, limit=args.limit) if args.query else library.entries(limit=args.limit)
    out.data([entry.as_dict() for entry in entries])
    if not entries:
        out.say("nothing found")
        return 0
    out.table(
        [
            (entry.name, entry.title[:40], entry.key or "-", f"{entry.tempo or '-'}", entry.collection)
            for entry in entries
        ]
    )
    out.say()
    out.dim(f"{len(entries)} shown of {len(library)} in the library")
    return 0


def cmd_doctor(args: argparse.Namespace, config: Config, out: Out) -> int:
    from ..runtime.capabilities import probe

    report = probe(refresh=True)
    out.head("host")
    rows = []
    for capability in report:
        mark = "yes" if capability.present else "no"
        rows.append((capability.name, mark, capability.detail[:60]))
    out.table(rows)

    missing = report.missing()
    if missing:
        out.say()
        out.head("not available")
        for capability in missing:
            out.say(f"  {capability.name}: {capability.unlocks}")
            if capability.remedy:
                out.dim(f"    {capability.remedy}")

    out.say()
    out.head("paths")
    out.table(list(config.paths.describe().items()))

    from ..llm.registry import auto_select, provider_status

    out.say()
    out.head("model providers")
    ready = [status for status in provider_status(config.paths) if status.configured]
    out.table(
        [(status.info.id, status.info.label[:30], status.source or "") for status in ready]
        or [("(none configured)", "", "")]
    )
    out.dim(f"  auto-select would use: {auto_select(config.paths, report)}")

    exit_code = 0
    if args.specs:
        from ..specs import format_results, verify_all

        out.say()
        out.head("specs")
        results = verify_all(paths=config.paths, report=report)
        out.say(format_results(results, verbose=args.verbose))
        exit_code = 1 if any(result.status == "FAIL" for result in results) else 0

    out.data(
        {
            "capabilities": report.as_dict(),
            "paths": config.paths.describe(),
            "providers": [status.as_dict() for status in provider_status(config.paths)],
        }
    )
    return exit_code


def cmd_spec(args: argparse.Namespace, config: Config, out: Out) -> int:
    from ..specs import format_results, load_specs, verify_all

    if args.list:
        specs = load_specs(config.paths, tag=args.tag)
        out.data([{"id": spec.id, "title": spec.title, "checks": len(spec.checks)} for spec in specs])
        out.table([(spec.id, spec.title[:50], f"{len(spec.checks)} checks") for spec in specs])
        return 0

    results = verify_all(paths=config.paths, tag=args.tag)
    out.data([result.as_dict() for result in results])
    if not results:
        out.warn("no specs found")
        return 0
    out.say(format_results(results, verbose=args.verbose))
    return 1 if any(result.status == "FAIL" for result in results) else 0


def cmd_providers(args: argparse.Namespace, config: Config, out: Out) -> int:
    from ..llm.registry import build_provider, provider_status

    statuses = provider_status(config.paths, probe_local=True)
    out.data([status.as_dict() for status in statuses])

    if args.check:
        from ..llm.types import ProviderError

        target = args.check if isinstance(args.check, str) else config.get("llm", "provider", "")
        try:
            provider = build_provider(target or "echo", paths=config.paths)
        except ProviderError as exc:
            out.fail(str(exc))
            return 1
        out.say(f"checking {provider.describe()} ...")
        ok, detail = provider.check()
        (out.ok if ok else out.fail)(detail)
        return 0 if ok else 1

    out.head("providers")
    rows = []
    for status in statuses:
        state = "ready" if status.configured else "no key"
        if status.reachable is False:
            state = "not running"
        rows.append((status.info.id, status.info.label[:34], state, status.source or status.info.docs[:40]))
    out.table(rows)
    out.say()
    out.dim("connect one with: tapscript setup")
    return 0


def cmd_setup(args: argparse.Namespace, config: Config, out: Out) -> int:
    from .setup import run_setup

    return run_setup(config, out, provider_id=args.provider, non_interactive=args.yes)


def cmd_config(args: argparse.Namespace, config: Config, out: Out) -> int:
    if args.action == "path":
        out.say(str(config.paths.config_file))
        return 0

    if args.action == "list":
        out.data(config.data)
        for section, values in config.data.items():
            out.head(f"[{section}]")
            out.table([(key, str(value)) for key, value in values.items()])
            out.say()
        out.dim("sources: " + ", ".join(config.sources))
        return 0

    if args.action == "get":
        if not args.name:
            out.fail("usage: tapscript config get <section.key>")
            return 2
        section, _, key = args.name.partition(".")
        value = config.get(section, key)
        if value is None:
            out.fail(f"no such setting: {args.name}")
            return 1
        print(value)
        return 0

    if args.action == "set":
        if not args.name or args.value is None:
            out.fail("usage: tapscript config set <section.key> <value>")
            return 2
        section, _, key = args.name.partition(".")
        if not key:
            out.fail("settings are named section.key, for example llm.provider")
            return 2
        current = config.get(section, key)
        value: Any = args.value
        if isinstance(current, bool):
            value = args.value.lower() in {"1", "true", "yes", "on"}
        elif isinstance(current, int) and not isinstance(current, bool):
            try:
                value = int(args.value)
            except ValueError:
                out.fail(f"{args.name} expects a number")
                return 2
        elif isinstance(current, float):
            value = float(args.value)
        config.set(section, key, value)
        target = config.save()
        out.ok(f"{args.name} = {value}")
        out.dim(f"saved to {target}")
        return 0

    out.fail(f"unknown action: {args.action}")
    return 2


def cmd_agent(args: argparse.Namespace, config: Config, out: Out) -> int:
    from ..agent.kernel import Agent
    from ..agent.tools import Sandbox, ToolRegistry
    from ..llm.registry import get_provider
    from ..llm.types import ProviderError

    try:
        provider = get_provider(config, provider_id=args.provider, model=args.model)
    except ProviderError as exc:
        out.fail(str(exc))
        return 1

    workspace = Path(args.workspace) if args.workspace else config.paths.workspace
    sandbox = Sandbox(
        root=workspace,
        extra_readable=[p for p in [config.paths.project_root] if p],
    )
    tools = ToolRegistry(sandbox=sandbox, config=config)

    verbose = args.verbose or not out.quiet

    def on_event(event) -> None:
        if not verbose or out.json_mode:
            return
        if event.kind == "tool_call":
            out.dim(f"  . {event.text}")
        elif event.kind == "tool_result" and args.verbose:
            first = event.text.splitlines()[0] if event.text else ""
            out.dim(f"    {first[:100]}")
        elif event.kind == "error":
            out.fail(event.text)

    agent = Agent(
        provider=provider,
        tools=tools,
        config=config,
        role=args.role,
        max_steps=args.max_steps,
        on_event=on_event,
    )

    prompt = args.prompt or (sys.stdin.read().strip() if not sys.stdin.isatty() else "")
    if not prompt:
        return _agent_repl(agent, out, config)

    out.dim(f"{provider.describe()}  .  working in {workspace}")
    out.say()
    result = agent.run(prompt)
    out.data(result.summary())

    if result.error:
        out.fail(result.error)
        return 1
    if result.reply:
        out.say(result.reply)
    if config.get("agent", "transcript", True):
        agent.save()
    return 0


def _agent_repl(agent, out: Out, config: Config) -> int:
    """Interactive chat when no prompt is given."""
    out.head("tapscript agent")
    out.dim(f"{agent.provider.describe()}  .  working in {agent.tools.sandbox.root}")
    out.dim("type a request, or /exit to leave")
    out.say()
    while True:
        try:
            prompt = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            out.say()
            break
        if not prompt:
            continue
        if prompt in {"/exit", "/quit", "/q"}:
            break
        if prompt == "/reset":
            agent.reset()
            out.dim("conversation cleared")
            continue
        result = agent.run(prompt)
        if result.error:
            out.fail(result.error)
        elif result.reply:
            out.say(result.reply)
        out.say()
    if config.get("agent", "transcript", True) and agent.messages:
        out.dim(f"transcript saved to {agent.save()}")
    return 0


def cmd_build(args: argparse.Namespace, config: Config, out: Out) -> int:
    args.role = "builder"
    args.prompt = args.goal or (
        "Set this installation up for me. Probe the host first, ask me at most two questions "
        "about what I want to build, then write PLAN.md and carry it out."
    )
    return cmd_agent(args, config, out)


def cmd_serve(args: argparse.Namespace, config: Config, out: Out) -> int:
    from .web.server import serve

    host = args.host or config.get("web", "host", "127.0.0.1")
    port = args.port or int(config.get("web", "port", 8765))
    return serve(config, host=host, port=port, open_browser=args.open, out=out)


def cmd_tui(args: argparse.Namespace, config: Config, out: Out) -> int:
    from .tui import run_tui

    return run_tui(config, path=args.file)


def cmd_bridge(args: argparse.Namespace, config: Config, out: Out) -> int:
    from .bridge import run_bridge

    return run_bridge(args, config, out)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _resolve_notation(reference: str, config: Config, out: Out) -> Path | None:
    """Accept a path, or the name of something in the library."""
    path = Path(reference)
    if path.exists():
        return path
    from ..library import Library

    entry = Library(paths=config.paths).find(reference)
    if entry is not None:
        return entry.path
    out.fail(f"no such file or library entry: {reference}")
    return None


# --------------------------------------------------------------------------
# argument parser
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tapscript",
        description="Plain-text music notation that compiles to MIDI and audio.",
        epilog="Start with: tapscript new, then tapscript compile <file> --play",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"tapscript {__version__}")
    parser.add_argument("-q", "--quiet", action="store_true", help="only print what was asked for")
    parser.add_argument("-v", "--verbose", action="store_true", help="show more detail")
    parser.add_argument("--json", action="store_true", dest="json_mode", help="machine-readable output")
    parser.add_argument("--config", metavar="FILE", help="use this configuration file")

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # -- notation ----------------------------------------------------------
    compile_parser = subparsers.add_parser("compile", help="compile notation to MIDI and audio")
    compile_parser.add_argument("file", help="a .tap file")
    compile_parser.add_argument("-o", "--midi", metavar="PATH", help="MIDI output path")
    compile_parser.add_argument("-a", "--audio", metavar="PATH", nargs="?", const="", help="audio output path")
    compile_parser.add_argument("--no-midi", action="store_true", help="skip the MIDI file")
    compile_parser.add_argument("--play", action="store_true", help="play the audio when it is ready")
    compile_parser.add_argument("--backend", default="auto", help="audio backend: auto, builtin, fluidsynth")
    compile_parser.add_argument("--soundfont", metavar="PATH", help="soundfont for the fluidsynth backend")
    compile_parser.add_argument("--dialect", default="auto", choices=["auto", "absolute", "relative"])
    compile_parser.add_argument("--semitones", type=int, default=0, help="transpose while compiling")
    compile_parser.add_argument(
        "--frame",
        default="",
        metavar="LISTENER",
        help="whose ears to render for: conductor, audience, player:<name>, or score",
    )
    compile_parser.add_argument(
        "--no-compensate",
        action="store_true",
        help="leave the stage uncorrected, so the render smears the way an uncued ensemble does",
    )
    compile_parser.set_defaults(func=cmd_compile)

    ensemble_parser = subparsers.add_parser(
        "ensemble", help="report what each listener on the stage actually hears"
    )
    ensemble_parser.add_argument("file", help="a .tap file with a [Stage] block")
    ensemble_parser.add_argument(
        "--frame", default="", metavar="LISTENER", help="conductor, audience, player:<name>, score"
    )
    ensemble_parser.add_argument("--no-compensate", action="store_true", help="report the raw errors")
    ensemble_parser.add_argument("--dialect", default="auto", choices=["auto", "absolute", "relative"])
    ensemble_parser.set_defaults(func=cmd_ensemble)

    play_parser = subparsers.add_parser("play", help="compile and play")
    play_parser.add_argument("file", help="a .tap file or a library entry")
    play_parser.add_argument("--backend", default="auto")
    play_parser.add_argument("--port", nargs="?", const="", metavar="NAME", help="play to a MIDI port instead")
    play_parser.set_defaults(func=cmd_play)

    info_parser = subparsers.add_parser("info", help="summarise a piece")
    info_parser.add_argument("file")
    info_parser.add_argument("--dialect", default="auto", choices=["auto", "absolute", "relative"])
    info_parser.set_defaults(func=cmd_info)

    check_parser = subparsers.add_parser("check", help="check notation for problems")
    check_parser.add_argument("files", nargs="+", help="files or directories")
    check_parser.add_argument("--strict", action="store_true", help="report warnings too")
    check_parser.set_defaults(func=cmd_check)

    transpose_parser = subparsers.add_parser("transpose", help="move a piece to another key")
    transpose_parser.add_argument("file")
    transpose_parser.add_argument("key", help="target key (Dm) or semitones (+3)")
    transpose_parser.add_argument("-o", "--output", metavar="PATH")
    transpose_parser.add_argument("-i", "--in-place", action="store_true")
    transpose_parser.set_defaults(func=cmd_transpose)

    new_parser = subparsers.add_parser("new", help="start a new piece from a template")
    new_parser.add_argument("title", nargs="?", help="what to call it")
    new_parser.add_argument("-o", "--output", metavar="PATH")
    new_parser.add_argument("--force", action="store_true")
    new_parser.set_defaults(func=cmd_new)

    library_parser = subparsers.add_parser("library", help="browse the bundled notation library")
    library_parser.add_argument("query", nargs="?", default="", help="search terms")
    library_parser.add_argument("-n", "--limit", type=int, default=25)
    library_parser.add_argument("--collections", action="store_true", help="list collections instead")
    library_parser.add_argument("--refresh", action="store_true", help="rebuild the index")
    library_parser.set_defaults(func=cmd_library)

    # -- machine and configuration ------------------------------------------
    doctor_parser = subparsers.add_parser("doctor", help="report what this machine can do")
    doctor_parser.add_argument("--specs", action="store_true", help="also verify the specs")
    doctor_parser.set_defaults(func=cmd_doctor)

    spec_parser = subparsers.add_parser("spec", help="verify the system against its specs")
    spec_parser.add_argument("--list", action="store_true", help="list specs instead of running them")
    spec_parser.add_argument("--tag", default="", help="only specs with this tag")
    spec_parser.set_defaults(func=cmd_spec)

    providers_parser = subparsers.add_parser("providers", help="list model providers")
    providers_parser.add_argument(
        "--check", nargs="?", const=True, metavar="ID", help="make a test call"
    )
    providers_parser.set_defaults(func=cmd_providers)

    setup_parser = subparsers.add_parser("setup", help="connect a model provider")
    setup_parser.add_argument("provider", nargs="?", default="", help="provider id, if you know it")
    setup_parser.add_argument("-y", "--yes", action="store_true", help="accept detected settings")
    setup_parser.set_defaults(func=cmd_setup)

    config_parser = subparsers.add_parser("config", help="read and write settings")
    config_parser.add_argument("action", choices=["get", "set", "list", "path"])
    config_parser.add_argument("name", nargs="?", help="section.key")
    config_parser.add_argument("value", nargs="?")
    config_parser.set_defaults(func=cmd_config)

    # -- agent and interfaces ------------------------------------------------
    agent_parser = subparsers.add_parser("agent", help="ask the built-in agent to make something")
    agent_parser.add_argument("prompt", nargs="?", default="", help="what you want")
    agent_parser.add_argument("--role", default="composer", help="composer or builder")
    agent_parser.add_argument("--provider", default="", help="override the provider")
    agent_parser.add_argument("--model", default="", help="override the model")
    agent_parser.add_argument("--workspace", metavar="DIR", help="where the agent may write")
    agent_parser.add_argument("--max-steps", type=int, default=0)
    agent_parser.set_defaults(func=cmd_agent)

    build_parser = subparsers.add_parser(
        "build", help="have the agent tailor this install to your machine"
    )
    build_parser.add_argument("goal", nargs="?", default="", help="what you want to build")
    build_parser.add_argument("--provider", default="")
    build_parser.add_argument("--model", default="")
    build_parser.add_argument("--workspace", metavar="DIR")
    build_parser.add_argument("--max-steps", type=int, default=0)
    build_parser.set_defaults(func=cmd_build)

    serve_parser = subparsers.add_parser("serve", help="start the web interface")
    serve_parser.add_argument("--host", default="")
    serve_parser.add_argument("--port", type=int, default=0)
    serve_parser.add_argument("--open", action="store_true", help="open a browser")
    serve_parser.set_defaults(func=cmd_serve)

    tui_parser = subparsers.add_parser("tui", help="start the terminal interface")
    tui_parser.add_argument("file", nargs="?", default="", help="open this file")
    tui_parser.set_defaults(func=cmd_tui)

    bridge_parser = subparsers.add_parser(
        "bridge", help="answer model requests on behalf of a host agent"
    )
    bridge_parser.add_argument(
        "action", nargs="?", default="status", choices=["status", "list", "answer", "watch"]
    )
    bridge_parser.add_argument("request_id", nargs="?", default="")
    bridge_parser.add_argument("--text", default="", help="the reply, for `answer`")
    bridge_parser.set_defaults(func=cmd_bridge)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    if args.config:
        os.environ["TAPSCRIPT_CONFIG"] = args.config

    config = load_config()
    out = Out(quiet=args.quiet, json_mode=args.json_mode)

    try:
        return int(args.func(args, config, out) or 0)
    except KeyboardInterrupt:
        out.say()
        out.dim("interrupted")
        return 130
    except BrokenPipeError:
        return 0
    except Exception as exc:
        if args.verbose:
            raise
        out.fail(f"{type(exc).__name__}: {exc}")
        out.dim("run again with --verbose for the full traceback")
        return 1


if __name__ == "__main__":
    sys.exit(main())
