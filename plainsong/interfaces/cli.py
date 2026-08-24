"""The command line.

``plainsong --help`` is the map. Commands are grouped by what you came to do:
work with notation, look at the machine, connect a model, or run an interface.
"""

from __future__ import annotations

import argparse
import json
import os
import re
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


# Every agent observed driving this CLI cold ran `--help` first, and the ones
# that could not reach `plainsong new` -- writing a file into an existing
# project rather than scaffolding one -- had to guess the shape of the notation.
# They guessed `Title:`, which is not it, and got a dropped title and a phantom
# section for it. Six lines here cost nothing and remove the guess.
NOTATION_AT_A_GLANCE = """\
The notation, in one section:

  **TRACK: Title**            <- the title. `Title:` is not it.
  [MetaData]
  key: Am | tempo: 96 | time: 4/4

  [V1] (Verse - 2 Bars)       <- a section
  Chords: | Am . . . | F . . . |
  Melody: | A4 . C5 E5 | F4 . A4 C5 |

A bar is one bar long and its tokens divide it, so three tokens are triplets and
you never write durations. Rows of different kinds sound together.

Start with: plainsong new, then plainsong compile <file> --play
Flags (--json, -v, -q) work before or after the subcommand."""


# --------------------------------------------------------------------------
# output helpers
# --------------------------------------------------------------------------


def _colour_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("PLAINSONG_COLOR", "").lower() in {"0", "false", "never"}:
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


def _diagnostics(
    out: Out, diagnostics: list, path: str = "", limit: int = 20, verbose: bool = False
) -> None:
    """Show the diagnostics. `verbose` adds the info-level ones.

    Info-level diagnostics used to be produced and then displayed by nothing at
    all -- not by `compile`, not by `check`, and not by `info --verbose`, which
    documents itself as showing every diagnostic available. An entire severity
    was write-only.

    That is not a cosmetic gap. `Title: My Song` is the most natural way to name
    a piece and is not the notation; the parser says so at info level, so the
    title was silently dropped, the stray row silently became a section, and the
    only visible trace was `(untitled)` and a section count one too high. A
    small model driving this cold hit exactly that.
    """
    levels = ("error", "warning", "info") if verbose else ("error", "warning")
    shown = [diag for diag in diagnostics if diag.severity in levels]
    if not shown:
        return
    out.say()
    painters = {"error": out.fail, "warning": out.warn}
    for diag in shown[:limit]:
        # Info keeps its own voice: painting it "warn" would say the file has a
        # problem when what it has is a remark.
        painters.get(diag.severity, out.dim)(diag.format(path))
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
        _diagnostics(
            out,
            result.diagnostics,
            str(source),
            limit=8 if not args.verbose else 100,
            verbose=args.verbose,
        )

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

    # `describe` reports the parser's diagnostics and the arranger's together.
    # Re-parsing here to fetch them would get only the parser's back, which is
    # how `--verbose` came to promise every diagnostic and omit half of them.
    from ..notation.ir import Diagnostic

    reported = [
        Diagnostic(
            severity=d.get("severity", "warning"),
            message=d.get("message", ""),
            line=d.get("line", 0),
            column=d.get("column", 0),
            hint=d.get("hint", ""),
            source=d.get("source", ""),
        )
        for d in summary.get("diagnostics", [])
    ]
    _diagnostics(out, reported, str(source), limit=100 if args.verbose else 10, verbose=args.verbose)
    return 0


NOTATION_FENCE = re.compile(r"^```(plainsong|tap)[ \t]*$(.*?)^```", re.S | re.M)
"""A fenced block claiming to be notation. Only these two tags are checked, so a
proposal for syntax that does not exist yet can use ```plainsong-proposed and be
left alone."""


def _notation_blocks(path: Path) -> list[tuple[str, str]]:
    """Every ```plainsong block in a markdown file, labelled with its line."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    blocks = []
    for match in NOTATION_FENCE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        blocks.append((f"{path}:{line}", match.group(2)))
    return blocks


def _check_targets(names: list[str]) -> list[tuple[str, str]]:
    """Everything to check, as (label, notation) pairs.

    Markdown is included because it is where the teaching material lives, and an
    example that does not compile teaches a language nobody can use. Checking
    only `.song` files meant `check academy` passed while every lesson in it was
    wrong, which is worse than not checking at all.
    """
    sources: list[tuple[str, str]] = []
    for name in names:
        path = Path(name)
        if path.is_dir():
            paths = sorted(path.rglob("*.song")) + sorted(path.rglob("*.md"))
        else:
            paths = [path]
        for item in paths:
            if item.suffix == ".md":
                sources.extend(_notation_blocks(item))
            else:
                try:
                    sources.append((str(item), item.read_text(encoding="utf-8")))
                except OSError as exc:
                    sources.append((str(item), f"\x00unreadable: {exc}"))
    return sources


def cmd_check(args: argparse.Namespace, config: Config, out: Out) -> int:
    from ..notation import arrange, parse

    targets = _check_targets(args.files)
    if not targets:
        out.fail("nothing to check")
        return 2

    failures = warnings = 0
    reports: list[dict[str, Any]] = []
    for label, text in targets:
        if text.startswith("\x00"):
            out.fail(f"{label}: {text[1:]}")
            failures += 1
            reports.append({"source": label, "status": "unreadable", "detail": text[1:]})
            continue
        target = label
        score = parse(text, path=label)
        notes = 0
        # Arranging produces diagnostics of its own -- an unreadable chord
        # becoming silence is found here, not by the parser -- and reporting
        # only the parser's meant those never reached anybody.
        row_warnings = list(score.warnings())
        if score.has_errors:
            failures += 1
            status = "error"
            _diagnostics(out, score.errors(), str(target))
        else:
            arrangement = arrange(score)
            notes = arrangement.note_count
            row_warnings = [
                diagnostic for diagnostic in arrangement.diagnostics if diagnostic.severity == "warning"
            ]
            if notes == 0:
                warnings += 1
                status = "silent"
                out.warn(f"{target}: parses, but produces no notes")
            else:
                status = "ok"
                if args.verbose:
                    out.ok(f"{target}: {notes} notes")
        warnings += len(row_warnings)
        if args.strict:
            _diagnostics(out, row_warnings, str(target), limit=5)
        reports.append(
            {
                "source": label,
                "status": status,
                "notes": notes,
                "errors": [diagnostic.format() for diagnostic in score.errors()],
                "warnings": [diagnostic.format() for diagnostic in row_warnings],
            }
        )

    checked = len(targets)
    out.data(
        {
            "checked": checked,
            "failures": failures,
            "warnings": warnings,
            "ok": failures == 0,
            "sources": reports,
        }
    )

    out.say()
    if failures:
        out.fail(f"{failures} of {checked} files have errors ({warnings} warnings)")
        return 1
    out.ok(f"{checked} file(s) checked, {warnings} warning(s)")
    return 0


def cmd_stage(args: argparse.Namespace, config: Config, out: Out) -> int:
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
    from ..notation.theory import TheoryError
    from ..transform import transpose

    source = _resolve_notation(args.file, config, out)
    if source is None:
        return 2
    target_key: str | int = args.key
    if args.key.lstrip("+-").isdigit():
        target_key = int(args.key)
    try:
        moved = transpose(source.read_text(encoding="utf-8"), target_key)
    except TheoryError as exc:
        out.fail(str(exc))
        out.dim("give a key such as Dm, F#, Bb or 'A minor', or semitones such as -3")
        return 2

    written: str | None = None
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(moved, encoding="utf-8")
        written = str(target)
        out.ok(f"wrote {target}")
    elif args.in_place:
        source.write_text(moved, encoding="utf-8")
        written = str(source)
        out.ok(f"rewrote {source}")
    elif not out.json_mode:
        # The notation itself is the output here, so it goes to stdout raw --
        # except under --json, where raw notation on stdout is what made
        # `plainsong --json transpose` emit something no parser could read.
        print(moved)

    out.data({"source": str(source), "target": args.key, "written": written, "content": moved})
    return 0


def cmd_chord(args: argparse.Namespace, config: Config, out: Out) -> int:
    """Read a chord symbol out loud.

    This exists so nobody has to guess. A chord symbol names an intent, and the
    rules that turn it into notes are the sort of thing you either know cold or
    cannot check at all -- which is how `EbMaj7` came to compile to silence for
    months without anyone noticing. Asking is now cheaper than being sure.
    """
    from ..notation.chordsymbol import ChordSymbolError, parse_symbol
    from ..notation.theory import NOTE_NAMES_FLAT, NOTE_NAMES_SHARP, pitch_name

    #: Which degree is which, in words, so the explanation reads like a
    #: musician talking rather than like a table dump.
    labels = {
        1: "root",
        3: "third",
        5: "fifth",
        6: "sixth",
        7: "seventh",
        9: "ninth",
        11: "eleventh",
        13: "thirteenth",
        2: "second",
        4: "fourth",
    }
    natural = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11, 9: 14, 11: 17, 13: 21}

    results = []
    failed = False
    for symbol in args.symbol:
        try:
            parsed = parse_symbol(symbol)
        except ChordSymbolError as exc:
            out.fail(f"{symbol}: {exc}")
            failed = True
            continue

        names = NOTE_NAMES_FLAT if args.flats else NOTE_NAMES_SHARP
        offsets = sorted(set(parsed.degrees.values()))
        spelling = [names[(parsed.root_pc + offset) % 12] for offset in offsets]
        midi = [(args.octave + 1) * 12 + parsed.root_pc + offset for offset in offsets]

        record = {
            "symbol": symbol,
            "root": names[parsed.root_pc],
            "core": parsed.core,
            "notes": spelling,
            "midi": midi,
            "intervals": list(offsets),
            "bass": names[parsed.bass_pc] if parsed.bass_pc is not None else None,
        }
        if args.explain:
            steps = []
            for degree in sorted(parsed.degrees):
                offset = parsed.degrees[degree]
                shift = offset - natural.get(degree, offset)
                mark = "" if shift == 0 else (" flattened" if shift < 0 else " raised")
                if abs(shift) == 2:
                    mark += " twice"
                steps.append(
                    f"{labels.get(degree, degree)}{mark}: "
                    f"{names[(parsed.root_pc + offset) % 12]} ({offset:+d} semitones)"
                )
            record["explain"] = steps
            missing = [labels[d] for d in (3, 5, 7) if d in labels and d not in parsed.degrees]
            record["absent"] = missing
        results.append(record)

        if not out.json_mode:
            head = f"{symbol}  --  {' '.join(spelling)}"
            if parsed.bass_pc is not None:
                head += f"   over {names[parsed.bass_pc]}"
            out.ok(head)
            if args.explain:
                for step in record["explain"]:
                    out.dim(f"    {step}")
                if record["absent"]:
                    # Saying what is *not* there matters more than it sounds.
                    # `C7alt` has no fifth and no natural ninth, and that
                    # absence is most of what makes it sound the way it does.
                    out.dim(f"    no {', no '.join(record['absent'])}")
                out.dim(f"    midi at octave {args.octave}: {midi}")
                out.dim(f"    lowest note {pitch_name(midi[0])}")

    out.data({"chords": results})
    return 2 if failed else 0


def cmd_voicing(args: argparse.Namespace, config: Config, out: Out) -> int:
    """Show, or compare, how a chord's notes are chosen.

    The comparison is here rather than in a one-off script because the default
    was picked on its numbers, and a claim like that should be re-runnable by
    whoever doubts it.
    """
    from ..notation.theory import NOTE_NAMES_FLAT, NOTE_NAMES_SHARP, TheoryError, parse_chord
    from ..notation.voicing import NATURAL, STRATEGIES, voice

    names = NOTE_NAMES_FLAT if args.flats else NOTE_NAMES_SHARP

    if args.compare:
        from ..library import Library

        chords = []
        for entry in Library().all():
            try:
                text = entry.read()
            except OSError:
                continue
            for line in text.splitlines():
                if not line.lower().startswith(("chords", "@")):
                    continue
                body = line.split(":", 1)[1] if ":" in line else ""
                for token in body.replace("|", " ").split():
                    try:
                        chord = parse_chord(token)
                    except TheoryError:
                        continue
                    if len(set(chord.degrees.values())) > args.limit:
                        chords.append(chord)
        if not chords:
            out.fail("no chords found to compare")
            return 2

        out.ok(f"{len(chords)} chord occurrences where the {args.limit}-note cap bites")
        rows = []
        for name in STRATEGIES:
            kept = total = guides = guide_total = muddy = 0
            for chord in chords:
                notes = list(voice(chord, args.octave, args.limit, name))
                classes = {note % 12 for note in notes}
                promised = {d for d, o in chord.degrees.items() if d in NATURAL and o != NATURAL[d]}
                extensions = [d for d in chord.degrees if d > 7]
                if extensions:
                    promised.add(max(extensions))
                for degree in promised:
                    total += 1
                    kept += (chord.root_pc + chord.degrees[degree]) % 12 in classes
                for degree in (3, 7):
                    if degree in chord.degrees:
                        guide_total += 1
                        guides += (chord.root_pc + chord.degrees[degree]) % 12 in classes
                ordered = sorted(notes)
                # Adjacent pairs, so the tail is one shorter on purpose.
                pairs = zip(ordered, ordered[1:], strict=False)
                muddy += sum(1 for a, b in pairs if b - a < 3 and a < 48)
            rows.append(
                {
                    "strategy": name,
                    "named_kept": round(100 * kept / max(total, 1), 1),
                    "guide_kept": round(100 * guides / max(guide_total, 1), 1),
                    "muddy": muddy,
                }
            )
        if not out.json_mode:
            out.say(f"{'strategy':<9} {'symbol kept':>12} {'guide tones':>12} {'muddy':>7}")
            for row in rows:
                out.say(
                    f"{row['strategy']:<9} {row['named_kept']:>11}% "
                    f"{row['guide_kept']:>11}% {row['muddy']:>7}"
                )
        out.data({"comparison": rows, "sample": len(chords)})
        return 0

    if not args.symbol:
        out.fail("give a chord symbol, or --compare")
        return 2

    results = []
    for symbol in args.symbol:
        try:
            chord = parse_chord(symbol)
        except TheoryError as exc:
            out.fail(f"{symbol}: {exc}")
            return 2
        written = [names[(chord.root_pc + o) % 12] for o in sorted(set(chord.degrees.values()))]
        row = {"symbol": symbol, "written": written, "played": {}}
        for name in STRATEGIES:
            row["played"][name] = [names[n % 12] for n in voice(chord, args.octave, args.limit, name)]
        results.append(row)
        if not out.json_mode:
            out.ok(f"{symbol}  written: {' '.join(written)}")
            for name, notes in row["played"].items():
                marker = "  <- default" if name == "guide" else ""
                out.dim(f"    {name:<8} {' '.join(notes)}{marker}")
    out.data({"chords": results})
    return 0


def cmd_chart(args: argparse.Namespace, config: Config, out: Out) -> int:
    """Draw a chord chart as SVG.

    The output is a standalone file so it can be committed and embedded with
    `<img src="chart.svg">`, which is the only way a chart appears in a markdown
    document on a platform we do not control: GitHub strips a raw `<svg>` and
    renders an `<img>`.
    """
    from ..pipeline import compile_text
    from ..render.chart import ChartOptions, render, unrenderable

    source = _resolve_notation(args.file, config, out)
    if source is None:
        return 2

    result = compile_text(source.read_text(encoding="utf-8"), config=config, path=str(source))
    if not result.ok:
        for diagnostic in result.diagnostics:
            out.fail(diagnostic.format())
        return 1

    svg = render(
        result.arrangement,
        ChartOptions(
            staff_space=args.scale,
            bars_per_line=args.bars,
            show_lyrics=not args.no_lyrics,
        ),
    )

    target = Path(args.output) if args.output else source.with_suffix(".svg")
    target.write_text(svg, encoding="utf-8")

    # Nothing should reach the page that the reference font cannot draw. This
    # is cheap and it is the failure that would otherwise be discovered by
    # someone looking at a blank rectangle where a flat sign belongs.
    lost = sorted({c for chunk in svg.split(">") for c in unrenderable(chunk)})
    if lost:
        out.warn("characters the font cannot draw reached the chart: " + " ".join(lost))

    out.ok(f"chart {target}")
    out.data({"chart": str(target), "bytes": len(svg)})
    return 0


def cmd_lyrics(args: argparse.Namespace, config: Config, out: Out) -> int:
    """Show which note each syllable is sung on.

    Vertical alignment is a convention for human eyes: rows divide their bars
    independently, so a word written directly beneath a note need not sound with
    it. That is invisible in the source and was invisible in the output too.
    This answers it directly, and shows both readings side by side so the
    difference is a fact rather than a claim.
    """
    from ..notation import arrange, parse
    from ..notation.arrange import ArrangeOptions
    from ..notation.lyrics import is_padding

    try:
        text = Path(args.file).read_text(encoding="utf-8")
    except OSError as exc:
        out.fail(str(exc))
        return 2

    score = parse(text)
    loose = arrange(score, ArrangeOptions(humanize=False, lyrics="independent"))
    bound = arrange(score, ArrangeOptions(humanize=False, lyrics="bound"))

    if not loose.lyrics:
        out.warn("no lyric rows in this file")
        return 0

    written = {(round(e.start, 6), e.text) for e in loose.lyrics}
    moved = [e for e in bound.lyrics if (round(e.start, 6), e.text) not in written]

    # Pair by position, not by matching text or nearby times: a word that
    # appears twice in a song would otherwise be paired with the wrong one of
    # itself. Both lists are in written order once padding is dropped, and
    # padding is dropped from both so the two stay in step.
    sung = [e for e in bound.lyrics if not is_padding(e.text)]
    as_written = [e for e in loose.lyrics if not is_padding(e.text)]
    rows = []
    for index, event in enumerate(sung):
        was = as_written[index] if index < len(as_written) else None
        rows.append(
            {
                "syllable": event.text,
                "bound": round(event.start, 4),
                "written": None if was is None else round(was.start, 4),
                "held": round(event.duration, 4),
            }
        )

    if not out.json_mode:
        out.ok(f"{len(rows)} syllable(s); {len(moved)} move when bound to their notes")
        out.dim(f"    {'syllable':<14}{'written at':>12}{'sung at':>10}{'held':>8}")
        for row in rows:
            written_at = "--" if row["written"] is None else f"{row['written']:g}"
            marker = "" if row["written"] == row["bound"] else "   <- moves"
            out.dim(
                f"    {row['syllable']:<14}{written_at:>12}{row['bound']:>10g}{row['held']:>8g}{marker}"
            )
        for diagnostic in bound.diagnostics:
            if diagnostic not in loose.diagnostics:
                out.warn(diagnostic.message)
        if not config.get("core", "lyrics", "independent") == "bound":
            out.dim('    set core.lyrics = "bound" to compile this way')

    out.data({"syllables": rows, "moved": len(moved)})
    return 0


def cmd_fingerprint(args: argparse.Namespace, config: Config, out: Out) -> int:
    """Print a stable hash of what each file compiles to.

    Answers the one question a compiler otherwise cannot answer for you: did
    upgrading change my music? Fingerprint before, fingerprint after, diff.
    """
    from ..fingerprint import fingerprint_paths, format_report

    entries = fingerprint_paths(args.paths)
    if not entries:
        out.fail("no .song files found")
        return 2

    if args.check:
        baseline = Path(args.check)
        if not baseline.is_file():
            out.fail(f"no baseline at {baseline}")
            return 2
        expected = baseline.read_text(encoding="utf-8").splitlines()
        actual = format_report(entries).splitlines()
        # Length first. Pairing the lines of two differently sized lists
        # silently truncates the longer one, so computing the diff before this
        # check would report a confident and wrong set of moved files.
        if len(expected) != len(actual):
            out.fail(f"the corpus changed size: {len(expected) - 1} files recorded, {len(entries)} found")
            out.dim("re-record with --write if files were added or removed on purpose")
            return 1
        moved = [
            (was, now)
            for was, now in zip(expected, actual, strict=True)
            if was != now and not was.startswith("#")
        ]
        if moved:
            out.fail(f"{len(moved)} file(s) compile differently than recorded")
            for was, now in moved[:20]:
                out.dim(f"    was  {was.strip()}")
                out.dim(f"    now  {now.strip()}")
            if len(moved) > 20:
                out.dim(f"    ... and {len(moved) - 20} more")
            out.dim("if the change is intended, re-record with --write")
            out.data({"changed": len(moved), "files": len(entries)})
            return 1
        out.ok(f"{len(entries)} file(s) compile exactly as recorded")
        out.data({"changed": 0, "files": len(entries)})
        return 0

    report = format_report(entries)
    if args.write:
        Path(args.write).write_text(report, encoding="utf-8")
        out.ok(f"wrote {args.write}")
    elif not out.json_mode:
        print(report, end="")
    out.data({"files": len(entries), "notes": sum(e.notes for e in entries)})
    return 0


def cmd_new(args: argparse.Namespace, config: Config, out: Out) -> int:
    title = args.title or "New Piece"
    target = Path(args.output) if args.output else Path(f"{title.lower().replace(' ', '-')}.song")
    if target.exists() and not args.force:
        out.fail(f"{target} already exists (use --force to overwrite)")
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(STARTER.format(title=title), encoding="utf-8")
    out.ok(f"wrote {target}")
    out.dim(f"next: plainsong compile {target} --audio out.wav")
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

    entries = (
        library.search(args.query, limit=args.limit) if args.query else library.entries(limit=args.limit)
    )
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
        # Finding nothing to verify is not success. The specs once shipped
        # outside the package, so every pip install answered "no specs found"
        # and exited 0 -- the self-verification the whole design leans on,
        # quietly doing nothing, with every caller reading that zero as a pass.
        # A packaging regression has to be loud here or it is invisible.
        if args.tag:
            out.warn(f"no specs are tagged {args.tag!r}")
        else:
            out.warn("no specs found -- this install is missing its spec files")
        return 1
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
    out.dim("connect one with: plainsong setup")
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
            out.fail("usage: plainsong config get <section.key>")
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
            out.fail("usage: plainsong config set <section.key> <value>")
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
    out.head("plainsong agent")
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


MCP_DEPRECATION = (
    "warning: `plainsong mcp` is deprecated and will be removed in 2.0.\n"
    "         Use the dedicated package instead:  pip install plainsong-mcp\n"
    "         It is the same server, maintained in one place rather than two.\n"
    "         Set PLAINSONG_NO_DEPRECATION=1 to silence this."
)


def _warn_mcp_deprecated() -> None:
    """Say it on stderr, never stdout, and never through `out`.

    In stdio mode stdout *is* the protocol: one stray line desynchronises the
    client, which is why `cmd_mcp` prints nothing there. stderr is the only
    channel safe in all three modes, and MCP clients treat it as a log.

    `plainsong/mcp/` duplicates `SuperInstance/plainsong-mcp`, and that
    duplication has already cost twice -- a DNS-rebinding fix that existed in
    one copy and not the other for months, then the same eight lines getting
    the same two things wrong in both. The sibling is on PyPI now, so for the
    first time there is somewhere to send people.
    """
    if os.environ.get("PLAINSONG_NO_DEPRECATION"):
        return
    print(MCP_DEPRECATION, file=sys.stderr)


def cmd_mcp(args: argparse.Namespace, config: Config, out: Out) -> int:
    from ..mcp.server import Server, serve_http, serve_stdio

    _warn_mcp_deprecated()
    server = Server(config=config)
    if args.list_tools:
        for spec in sorted(server.registry.specs(), key=lambda spec: spec.name):
            out.say(f"{spec.name:<22} {spec.description.splitlines()[0]}")
        return 0
    if args.http:
        return serve_http(server, config=config, host=args.host, port=args.port, out=out)
    # Stdout carries the protocol from here on, so nothing is printed: one
    # stray line would desynchronise the client.
    try:
        return serve_stdio(server)
    finally:
        _detach_stdout_if_broken()


def _detach_stdout_if_broken() -> None:
    """Keep interpreter shutdown from re-raising on a pipe we know is closed.

    Python flushes stdout on the way out; if the client is gone that raises
    again and prints `Exception ignored in: <_io.TextIOWrapper name='<stdout>'>`
    after `serve_stdio` has already decided the disconnect was clean.

    This belongs here and not in `serve_stdio`, which is a library function that
    also runs inside other people's processes -- a test runner, an embedding
    host. Reassigning file descriptor 1 out from under one of those breaks
    everything downstream of it, which is exactly what happened when this lived
    there: every later test in the file failed with `Bad file descriptor`. Only
    the entry point owns the process.
    """
    import os
    import sys

    try:
        sys.stdout.flush()
    except (BrokenPipeError, ValueError):
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except (OSError, ValueError, AttributeError):
            pass


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
        prog="plainsong",
        description="Plain-text music notation that compiles to MIDI and audio.",
        epilog=NOTATION_AT_A_GLANCE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"plainsong {__version__}")
    parser.add_argument("-q", "--quiet", action="store_true", help="only print what was asked for")
    parser.add_argument("-v", "--verbose", action="store_true", help="show more detail")
    parser.add_argument("--json", action="store_true", dest="json_mode", help="machine-readable output")
    parser.add_argument("--config", metavar="FILE", help="use this configuration file")

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # -- notation ----------------------------------------------------------
    compile_parser = subparsers.add_parser("compile", help="compile notation to MIDI and audio")
    compile_parser.add_argument("file", help="a .song file")
    compile_parser.add_argument("-o", "--midi", metavar="PATH", help="MIDI output path")
    compile_parser.add_argument(
        "-a", "--audio", metavar="PATH", nargs="?", const="", help="audio output path"
    )
    compile_parser.add_argument("--no-midi", action="store_true", help="skip the MIDI file")
    compile_parser.add_argument("--play", action="store_true", help="play the audio when it is ready")
    compile_parser.add_argument(
        "--backend", default="auto", help="audio backend: auto, builtin, fluidsynth"
    )
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

    stage_parser = subparsers.add_parser(
        "stage", help="report what each listener on the stage actually hears"
    )
    stage_parser.add_argument("file", help="a .song file with a [Stage] block")
    stage_parser.add_argument(
        "--frame", default="", metavar="LISTENER", help="conductor, audience, player:<name>, score"
    )
    stage_parser.add_argument("--no-compensate", action="store_true", help="report the raw errors")
    stage_parser.add_argument("--dialect", default="auto", choices=["auto", "absolute", "relative"])
    stage_parser.set_defaults(func=cmd_stage)

    play_parser = subparsers.add_parser("play", help="compile and play")
    play_parser.add_argument("file", help="a .song file or a library entry")
    play_parser.add_argument("--backend", default="auto")
    play_parser.add_argument(
        "--port", nargs="?", const="", metavar="NAME", help="play to a MIDI port instead"
    )
    play_parser.set_defaults(func=cmd_play)

    info_parser = subparsers.add_parser("info", help="summarise a piece")
    info_parser.add_argument("file")
    info_parser.add_argument("--dialect", default="auto", choices=["auto", "absolute", "relative"])
    info_parser.add_argument(
        "--verbose", action="store_true", help="show every diagnostic, not the first ten"
    )
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

    chord_parser = subparsers.add_parser("chord", help="read a chord symbol and say what is in it")
    chord_parser.add_argument("symbol", nargs="+", help="one or more chord symbols")
    chord_parser.add_argument(
        "--explain",
        action="store_true",
        help="show every degree, what bent it, and what is deliberately absent",
    )
    chord_parser.add_argument("--octave", type=int, default=3, help="octave for MIDI numbers")
    chord_parser.add_argument("--flats", action="store_true", help="spell with flats")
    chord_parser.set_defaults(func=cmd_chord)

    voicing_parser = subparsers.add_parser("voicing", help="show which notes a chord sounds, and why those")
    voicing_parser.add_argument("symbol", nargs="*", help="chord symbols")
    voicing_parser.add_argument(
        "--compare",
        action="store_true",
        help="score every strategy over the library, on the chords where the cap bites",
    )
    voicing_parser.add_argument("--limit", type=int, default=4, help="how many voices")
    voicing_parser.add_argument("--octave", type=int, default=3)
    voicing_parser.add_argument("--flats", action="store_true")
    voicing_parser.set_defaults(func=cmd_voicing)

    chart_parser = subparsers.add_parser(
        "chart", help="draw a chord chart as SVG, for embedding in a document"
    )
    chart_parser.add_argument("file", help="a .song file")
    chart_parser.add_argument("-o", "--output", help="where to write the SVG")
    chart_parser.add_argument("--bars", type=int, default=4, help="bars per line")
    chart_parser.add_argument(
        "--scale", type=float, default=7.0, help="staff space in px; the chart scales from this"
    )
    chart_parser.add_argument("--no-lyrics", action="store_true", help="chords only")
    chart_parser.set_defaults(func=cmd_chart)

    lyrics_parser = subparsers.add_parser("lyrics", help="show which note each syllable is sung on")
    lyrics_parser.add_argument("file", help="a .song file")
    lyrics_parser.set_defaults(func=cmd_lyrics)

    fingerprint_parser = subparsers.add_parser(
        "fingerprint", help="hash what notation compiles to, so a change in the sound is visible"
    )
    fingerprint_parser.add_argument("paths", nargs="+", help="files or directories")
    fingerprint_parser.add_argument(
        "--check", metavar="FILE", help="compare against a recorded fingerprint and fail on a difference"
    )
    fingerprint_parser.add_argument("--write", metavar="FILE", help="record the fingerprint to a file")
    fingerprint_parser.set_defaults(func=cmd_fingerprint)

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
    providers_parser.add_argument("--check", nargs="?", const=True, metavar="ID", help="make a test call")
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

    build_parser = subparsers.add_parser("build", help="have the agent tailor this install to your machine")
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

    mcp_parser = subparsers.add_parser("mcp", help="serve over the Model Context Protocol, for agents")
    mcp_parser.add_argument("--http", action="store_true", help="serve over HTTP instead of stdio")
    mcp_parser.add_argument("--host", default="127.0.0.1", help="HTTP bind address (loopback)")
    mcp_parser.add_argument("--port", type=int, default=8766, help="HTTP port")
    mcp_parser.add_argument("--list-tools", action="store_true", help="print the tools and exit")
    mcp_parser.set_defaults(func=cmd_mcp)

    tui_parser = subparsers.add_parser("tui", help="start the terminal interface")
    tui_parser.add_argument("file", nargs="?", default="", help="open this file")
    tui_parser.set_defaults(func=cmd_tui)

    bridge_parser = subparsers.add_parser("bridge", help="answer model requests on behalf of a host agent")
    bridge_parser.add_argument(
        "action", nargs="?", default="status", choices=["status", "list", "answer", "watch"]
    )
    bridge_parser.add_argument("request_id", nargs="?", default="")
    bridge_parser.add_argument("--text", default="", help="the reply, for `answer`")
    bridge_parser.set_defaults(func=cmd_bridge)

    _accept_global_flags_after_the_subcommand(subparsers)
    return parser


# `plainsong info song.song --json` is what almost everyone types, because that
# is where flags go in nearly every other CLI. argparse hangs global options off
# the top-level parser only, so that invocation was refused outright --
# `unrecognized arguments: --json` -- and the refusal is total: the command does
# not run, it errors. This is not hypothetical. tools/verify_release.py in this
# repository was written against it and reported two false failures, and a small
# model driving this CLI cold hit it three times in one session, on --json, on
# -v and on --quiet, then named flag position as the single thing it most wished
# the tool had told it.
#
# Documenting the constraint was the old fix and it does not work: the sentence
# "Every command takes --json" was in AGENTS.md, and following it literally is
# what produced the bug above. So the trap is removed rather than described.
#
# argparse.SUPPRESS is the load-bearing detail. Without it the subparser's own
# default overwrites whatever the global flag set, so `plainsong --json info x`
# would parse and then silently lose its --json -- trading a loud failure for a
# quiet one, which is the worse trade.
GLOBAL_FLAGS_AFTER_SUBCOMMAND = (
    (("-q", "--quiet"), "quiet", "only print what was asked for"),
    (("-v", "--verbose"), "verbose", "show more detail"),
    (("--json",), "json_mode", "machine-readable output"),
)


def _accept_global_flags_after_the_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Let every subcommand take the global flags in the natural position too."""
    for sub in subparsers.choices.values():
        for options, dest, help_text in GLOBAL_FLAGS_AFTER_SUBCOMMAND:
            # A subcommand that already defines one of these keeps its own --
            # `info` has its own `--verbose`, and overriding it here would be a
            # behaviour change rather than an addition.
            free = [o for o in options if o not in sub._option_string_actions]
            if not free:
                continue
            sub.add_argument(
                *free,
                dest=dest,
                action="store_true",
                default=argparse.SUPPRESS,
                help=help_text,
            )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    if args.config:
        os.environ["PLAINSONG_CONFIG"] = args.config

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
