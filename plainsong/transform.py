"""Notation in, notation out.

Transposition works by rewriting tokens and emitting the score again, so every
row moves -- including the chord row, which an earlier engine skipped, and
which is exactly the row a player reads first.

Lyrics and free-text directions are copied through untouched.
"""

from __future__ import annotations

from .notation import theory
from .notation.ir import (
    ROLE_ANNOTATION,
    ROLE_CHORDS,
    ROLE_LYRICS,
    ROLE_MELODY,
    ROLE_NOTE,
    ROLE_PLAYER,
    ROLE_VELOCITY,
    Line,
    Score,
)
from .notation.parser import REST_TOKENS, SUSTAIN_TOKENS, parse, split_dynamics, token_weight

ROLE_PREFIX = {
    ROLE_CHORDS: "Chords:",
    ROLE_MELODY: "Melody:",
    ROLE_LYRICS: "Lyrics:",
    ROLE_VELOCITY: "Vel:",
}


def _shift_pitch_token(token: str, semitones: int, prefer_flats: bool) -> str:
    """Move one pitch token, keeping stacks, sustains, dynamics and letter case."""
    bare, _weight = token_weight(token)
    tail = token[len(bare) :]
    core, _absolute, _delta = split_dynamics(bare)
    mark = bare[len(core) :]
    if core.lower() in SUSTAIN_TOKENS or core.lower() in REST_TOKENS:
        return token

    parts = core.split("-")
    moved: list[str] = []
    for part in parts:
        if not theory.is_pitch(part):
            return token  # not a pitch stack; leave it exactly as written
        try:
            midi = theory.parse_pitch(part)
        except theory.TheoryError:
            return token
        name = theory.pitch_name(max(0, min(127, midi + semitones)), prefer_flats)
        moved.append(name.lower() if part[0].islower() else name)
    return "-".join(moved) + mark + tail


def _shift_chord_token(token: str, semitones: int, prefer_flats: bool, key: theory.Key) -> str:
    bare, _weight = token_weight(token)
    tail = token[len(bare) :]
    core, _absolute, _delta = split_dynamics(bare)
    mark = bare[len(core) :]
    if core.lower() in SUSTAIN_TOKENS or core.lower() in REST_TOKENS:
        return token
    if theory.is_roman(core):
        return token  # roman numerals are already relative to the key
    try:
        chord = theory.parse_chord(core)
    except theory.TheoryError:
        return token
    return chord.transpose(semitones).name(prefer_flats) + mark + tail


def transpose_score(score: Score, semitones: int) -> Score:
    """Return a copy of *score* moved by *semitones*."""
    if semitones == 0:
        return score
    new_key = score.meta.key.transpose(semitones)
    prefer_flats = new_key.prefer_flats

    for section in score.sections:
        for line in section.lines:
            # A Vel: row and a named annotation layer carry marks and data,
            # not music; they pass through untouched, still aligned to the
            # tokens they were written under.
            if line.role in (ROLE_LYRICS, ROLE_NOTE, ROLE_VELOCITY, ROLE_ANNOTATION):
                continue
            for cell in line.cells:
                if line.role == ROLE_CHORDS:
                    cell.tokens = [
                        _shift_chord_token(token, semitones, prefer_flats, score.meta.key)
                        for token in cell.tokens
                    ]
                else:
                    cell.tokens = [
                        _shift_pitch_token(token, semitones, prefer_flats) for token in cell.tokens
                    ]
    score.meta.key = new_key
    return score


def transpose(text: str, target: str | int, dialect: str = "auto") -> str:
    """Transpose notation to a key, or by a number of semitones.

    An unreadable target raises rather than being guessed at. ``parse_key`` is
    forgiving by design -- a ``Key:`` header must not stop a file loading -- but
    that forgiveness reads ``"banana"`` as B major, and silently transposing
    somebody's score by a semitone because they mistyped a key is worse than
    refusing to.
    """
    score = parse(text, dialect=dialect)
    if isinstance(target, int):
        semitones = target
    else:
        name = str(target)
        if not theory.names_a_key(name):
            raise theory.TheoryError(f"not a key: {name!r}")
        semitones = theory.transpose_interval(score.meta.key, theory.parse_key(name))
    return to_text(transpose_score(score, semitones))


def _format_row(line: Line) -> str:
    cells = [cell.text for cell in line.cells]
    if not line.barred:
        body = " ".join(cells)
    else:
        body = "| " + " | ".join(cells) + " |"

    if line.role == ROLE_PLAYER:
        prefix = f"@{line.name} "
        suffix = ""
        if "velocity" in line.options:
            # `body` already ends in the closing `|`, and that same bar line is
            # what separates the last cell from the options. Adding another
            # produced `... | | vel: 70`, an empty cell the parser then read as
            # a real bar -- so every transpose grew each player row by one bar,
            # and the row drifted further from the rest of the section each time.
            separator = "" if body.rstrip().endswith("|") else " |"
            suffix = f"{separator} vel: {line.options['velocity']}"
        return f"{prefix}{body}{suffix}"
    if line.role == ROLE_ANNOTATION:
        # The dimension's own name, as written: `Breath:` round-trips as
        # `Breath:`, not as something the compiler renamed it to. An explicit
        # target rides after the last bar, the way `vel: 70` does on a player
        # row -- and for the same reason: the same bar line separates the last
        # cell from the option, so no empty cell is invented.
        suffix = f" on: {line.options['on']}" if line.options.get("on") else ""
        return f"{(line.name or 'Annotation').strip()}: {body}{suffix}"
    return f"{ROLE_PREFIX.get(line.role, line.role.title() + ':')} {body}"


def to_text(score: Score) -> str:
    """Emit notation for a score. Parsing the result gives the same music."""
    lines: list[str] = []
    meta = score.meta
    if meta.title:
        lines.append(f"**TRACK: {meta.title}**")
    lines.append("[MetaData]")

    header = [f"key: {meta.key.name()}", f"tempo: {meta.tempo:g}"]
    if meta.swing:
        header.append(f"swing: {meta.swing * 100:g}%")
    header.append(f"subdivision: {meta.subdivision}")
    lines.append(" | ".join(header))

    second = [f"time: {meta.meter}"]
    for key, value in meta.extra.items():
        if key != "note":
            second.append(f"{key}: {value}")
    lines.append(" | ".join(second))

    for section in score.sections:
        lines.append("")
        heading = f"[{section.name}]"
        if section.description:
            heading += f" ({section.description})"
        lines.append(heading)
        for line in section.lines:
            if line.role == ROLE_NOTE:
                if line.name and line.options.get("direction"):
                    lines.append(f"@{line.name}: {line.options['direction']}")
                elif line.raw.strip():
                    lines.append(line.raw.strip())
                continue
            if not line.cells:
                continue
            lines.append(_format_row(line))

    # The [Perf] block, if the piece wrote one: channel tables over the
    # piece's own voices. Emitted at the end so the grid reads first, and
    # re-parsed to the same rows, so transposing a take keeps its channels.
    if score.perf:
        lines.append("")
        lines.append("[Perf]")
        for row in score.perf:
            voice = str(row.options.get("voice") or "").strip()
            body = "| " + " | ".join(cell.text for cell in row.cells) + " |"
            lines.append(f"@{voice}.{row.name} {body}")

    return "\n".join(lines).rstrip() + "\n"


def retempo(text: str, tempo: float, dialect: str = "auto") -> str:
    """Rewrite the tempo without touching anything else."""
    score = parse(text, dialect=dialect)
    score.meta.tempo = max(20.0, min(400.0, float(tempo)))
    return to_text(score)


def describe(text: str, dialect: str = "auto") -> dict:
    """A structural summary, for tools and interfaces that want facts."""
    from .notation import arrange

    score = parse(text, dialect=dialect)
    summary = score.summary()
    diagnostics = score.diagnostics
    if not score.has_errors:
        arrangement = arrange(score)
        summary["arrangement"] = arrangement.summary()
        if arrangement.annotations:
            # Named layers, if any: what dimensions the writer used and how
            # many values resolved to an address. Absent for a file with none,
            # which is the common case and stays exactly as it was.
            layers: dict[str, dict[str, object]] = {}
            for annotation in arrangement.annotations:
                entry = layers.setdefault(annotation.name, {"values": 0, "voices": set()})
                entry["values"] = int(entry["values"]) + 1
                entry["voices"].add(annotation.voice)  # type: ignore[union-attr]
            summary["annotations"] = {
                name: {"values": entry["values"], "voices": sorted(entry["voices"])}  # type: ignore[arg-type]
                for name, entry in layers.items()
            }
        if arrangement.perf:
            # Perf channels, if any: same shape as the annotation layers,
            # over the [Perf] block's channel tables instead of named rows.
            channels: dict[str, dict[str, object]] = {}
            for mark in arrangement.perf:
                entry = channels.setdefault(mark.name, {"values": 0, "voices": set()})
                entry["values"] = int(entry["values"]) + 1
                entry["voices"].add(mark.voice)  # type: ignore[union-attr]
            summary["perf"] = {
                channel: {"values": entry["values"], "voices": sorted(entry["voices"])}  # type: ignore[arg-type]
                for channel, entry in channels.items()
            }
        # Diagnostics come from two places and the arranger's are the ones a
        # reader most needs: an unreadable chord becomes silence while
        # arranging, not while parsing. This arranged and then reported only
        # the parser's, so `Xm9` produced a bar of nothing and said why
        # nowhere. `Arrangement.diagnostics` is already the union.
        diagnostics = arrangement.diagnostics
    summary["diagnostics"] = [diag.as_dict() for diag in diagnostics]
    return summary
