"""Notation in, notation out.

Transposition works by rewriting tokens and emitting the score again, so every
row moves -- including the chord row, which an earlier engine skipped, and
which is exactly the row a player reads first.

Lyrics and free-text directions are copied through untouched.
"""

from __future__ import annotations

from .notation import theory
from .notation.ir import (
    ROLE_CHORDS,
    ROLE_LYRICS,
    ROLE_MELODY,
    ROLE_NOTE,
    ROLE_PLAYER,
    Line,
    Score,
)
from .notation.parser import REST_TOKENS, SUSTAIN_TOKENS, parse, token_weight

ROLE_PREFIX = {
    ROLE_CHORDS: "Chords:",
    ROLE_MELODY: "Melody:",
    ROLE_LYRICS: "Lyrics:",
}


def _shift_pitch_token(token: str, semitones: int, prefer_flats: bool) -> str:
    """Move one pitch token, keeping stacks, sustains and letter case."""
    bare, _weight = token_weight(token)
    tail = token[len(bare) :]
    if bare.lower() in SUSTAIN_TOKENS or bare.lower() in REST_TOKENS:
        return token

    parts = bare.split("-")
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
    return "-".join(moved) + tail


def _shift_chord_token(token: str, semitones: int, prefer_flats: bool, key: theory.Key) -> str:
    bare, _weight = token_weight(token)
    tail = token[len(bare) :]
    if bare.lower() in SUSTAIN_TOKENS or bare.lower() in REST_TOKENS:
        return token
    if theory.is_roman(bare):
        return token  # roman numerals are already relative to the key
    try:
        chord = theory.parse_chord(bare)
    except theory.TheoryError:
        return token
    return chord.transpose(semitones).name(prefer_flats) + tail


def transpose_score(score: Score, semitones: int) -> Score:
    """Return a copy of *score* moved by *semitones*."""
    if semitones == 0:
        return score
    new_key = score.meta.key.transpose(semitones)
    prefer_flats = new_key.prefer_flats

    for section in score.sections:
        for line in section.lines:
            if line.role in (ROLE_LYRICS, ROLE_NOTE):
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
    """Transpose notation to a key, or by a number of semitones."""
    score = parse(text, dialect=dialect)
    if isinstance(target, int):
        semitones = target
    else:
        semitones = theory.transpose_interval(score.meta.key, theory.parse_key(str(target)))
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
            suffix = f" | vel: {line.options['velocity']}"
        return f"{prefix}{body}{suffix}"
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
    if not score.has_errors:
        summary["arrangement"] = arrange(score).summary()
    summary["diagnostics"] = [diag.as_dict() for diag in score.diagnostics]
    return summary
