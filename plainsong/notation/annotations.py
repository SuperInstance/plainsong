"""Named annotation rows, and the alignment they share with ``Vel:``.

Any labelled row the compiler does not otherwise claim -- ``Breath:``,
``Gaze:``, ``Emotion:`` -- is an annotation layer: first-class semantic data
over the playable row above it. The rule the Vel: row established generalises
unchanged:

* the layer marks the nearest playable row (``Chords:``, ``Melody:``,
  ``@player``) above it, and owns no time of its own;
* the k-th token of a layer's cell holds the k-th token of that bar, so a
  value sits under the event it describes and ``.`` holds its column;
* each written value is resolved to an address -- voice, bar, beat window,
  target event -- so consumers join on it rather than hoping a column means
  what it looks like.

The alignment lives here, once, and both kinds of row walk it: ``Vel:`` is
the built-in layer whose values have MIDI velocity semantics, and a generic
layer has no compilation effect unless a semantic is registered for it in
:data:`ANNOTATION_SEMANTICS`.

The timestamps an address carries are not computed here. They are read off
the time grid placements the arranger already recorded for the target row --
``bar`` and ``unit`` are derived in ``TimeGrid.add`` and nowhere else, which
is what keeps a mark and its note from drifting apart by being computed in
two places.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from .ir import (
    ROLE_ANNOTATION,
    ROLE_CHORDS,
    ROLE_MELODY,
    ROLE_PLAYER,
    ROLE_VELOCITY,
    Annotation,
)
from .parser import REST_TOKENS, SUSTAIN_TOKENS, token_weight

if TYPE_CHECKING:  # imported for typing only
    from .ir import Line
    from .timegrid import Placement

__all__ = [
    "ANNOTATION_ROLES",
    "ANNOTATION_SEMANTICS",
    "PLAYABLE_ROLES",
    "is_spacer",
    "pair_annotation_rows",
    "resolve",
    "semantic_for",
    "target_key",
    "walk_bars",
]

#: The rows an annotation layer can mark. Lyrics own no attacks, so a layer
#: above a lyric row keeps marking the playable row above *that*.
PLAYABLE_ROLES = frozenset({ROLE_CHORDS, ROLE_MELODY, ROLE_PLAYER})

#: Rows that annotate rather than play.
ANNOTATION_ROLES = frozenset({ROLE_VELOCITY, ROLE_ANNOTATION})

#: The extension table: annotation row name -> semantic.
#: A name with no entry is pure data -- preserved, addressable, round-tripped,
#: with no effect on the compile. Registering a name here is how a row gains
#: one; ``"velocity"`` is the built-in instance, which is why the vel family
#: below is also claimed by the parser's ROLE_LABELS and compiles to per-note
#: velocities. A new semantic needs a consumer; the table is the single place
#: a writer or a fork registers it.
ANNOTATION_SEMANTICS: dict[str, str] = {
    "vel": "velocity",
    "vels": "velocity",
    "velocity": "velocity",
    "dynamics": "velocity",
}


def semantic_for(name: str) -> str:
    """The registered semantic of an annotation row name, or ``""``."""
    return ANNOTATION_SEMANTICS.get(name.strip().lower(), "")


def is_spacer(token: str) -> bool:
    """Whether an annotation token holds its column and says nothing.

    The same sustain and rest spellings a playable row uses, read the same
    way -- one vocabulary, so a layer and the row it marks agree about what a
    ``.`` is.
    """
    bare, _weight = token_weight(token)
    lowered = bare.lower()
    return lowered in SUSTAIN_TOKENS or lowered in REST_TOKENS


def target_key(line: "Line") -> str:
    """The key a playable row is known by: its role, or ``player:name``."""
    return f"{line.role}:{line.name}" if line.role == ROLE_PLAYER else line.role


def _matches_hint(hint: str, line: "Line") -> bool:
    candidate = hint.strip().lower().lstrip("@")
    if candidate.startswith("player:"):
        candidate = candidate[len("player:") :]
    aliases = {line.role.lower()}
    if line.role == ROLE_PLAYER:
        aliases.add(line.name.lower())
    return candidate in aliases


def pair_annotation_rows(lines: Sequence["Line"]) -> list[tuple["Line", "Line"]]:
    """Pair every annotation row with the playable row it marks.

    A layer marks the nearest playable row above it, the rule ``Vel:``
    established -- unless it names its target explicitly with a trailing
    ``on:`` cell, in which case it marks the last playable row in the section
    that answers to that name, wherever it was written. Two layers may mark
    the same row (``Breath:`` and ``Gaze:`` are different dimensions over one
    melody); only claiming *the same dimension twice* is a conflict, and that
    rule belongs to the consumer -- velocity resolves it with a warning, data
    layers have nothing to fight over. A layer with no target is simply
    preserved.
    """
    pairs: list[tuple[Line, Line]] = []
    target: Line | None = None
    playable = [line for line in lines if line.cells and line.role in PLAYABLE_ROLES]
    for line in lines:
        if line.role in ANNOTATION_ROLES:
            if not line.cells:
                continue
            hint = str(line.options.get("on") or "").strip()
            if hint:
                matches = [row for row in playable if _matches_hint(hint, row)]
                if matches:
                    pairs.append((matches[-1], line))
                continue
            if target is not None and target.cells:
                pairs.append((target, line))
            continue
        if line.cells and line.role in PLAYABLE_ROLES:
            target = line
    return pairs


def walk_bars(target: "Line", annotation: "Line") -> Iterator[tuple[int, list[str], list[str]]]:
    """Yield ``(bar_index, target_tokens, annotation_tokens)`` for the pair.

    The shared positional walk. A barred row is one bar per cell; an unbarred
    row is flattened to a single run, exactly as the arranger flattens it --
    so a barred layer over an unbarred target (or the reverse) still pairs by
    position over whatever both sides wrote. ``Vel:`` marks and generic
    annotation values go through this one function, which is the guarantee
    that they land on the same events.
    """
    target_bars = (
        [cell.tokens for cell in target.cells]
        if target.barred
        else [[token for cell in target.cells for token in cell.tokens]]
    )
    annotation_bars = (
        [cell.tokens for cell in annotation.cells]
        if annotation.barred
        else [[token for cell in annotation.cells for token in cell.tokens]]
    )
    width = max(len(target_bars), len(annotation_bars))
    for bar in range(width):
        tokens = target_bars[bar] if bar < len(target_bars) else []
        written = annotation_bars[bar] if bar < len(annotation_bars) else []
        yield bar, tokens, written


def resolve(
    layer: "Line",
    target: "Line",
    *,
    voice: str,
    target_role: str,
    placements: Sequence["Placement"],
) -> list[Annotation]:
    """Address one annotation layer against its target's grid placements.

    *placements* is the target row's tokens in walk order -- the arranger's
    slice of the time grid for that line, which is the same arithmetic that
    timed the notes. Every written value that is not a spacer and that stands
    over a token of the target becomes an :class:`~plainsong.notation.ir.Annotation`
    carrying its resolved address: which voice, which bar, which beat window,
    and the target token it marks. A value over a sustain or a rest is still
    data -- the address records the target's kind, so a consumer can ask for
    marks over attacks the way velocity does.
    """
    out: list[Annotation] = []
    index = 0
    for _bar, tokens, written in walk_bars(target, layer):
        for position, _token in enumerate(tokens):
            mark = written[position] if position < len(written) else None
            if mark is None or is_spacer(mark):
                continue
            if index + position >= len(placements):
                break
            placement = placements[index + position]
            out.append(
                Annotation(
                    name=layer.name,
                    token=mark,
                    voice=voice,
                    role=target_role,
                    bar=placement.bar,
                    unit=placement.unit,
                    onset=placement.onset,
                    width=placement.width,
                    target=placement.token,
                    target_kind=placement.kind,
                    line_number=layer.line_number,
                )
            )
        index += len(tokens)
    return out
