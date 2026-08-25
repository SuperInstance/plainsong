"""The ``[Perf]`` block: performance channels over the piece's own voices.

A row can name one velocity for a whole bar and an inline mark can name one
note, but nothing in the notation could say what a *take* does inside a bar.
``[Perf]`` is the minimal core of the performance layer
(``docs/perf-spec-draft.md``, first ship-step, seminar-gated to literals):

.. code-block:: none

    [Perf]
    @piano.vel | 88 58 . . | 64 . . . |

One row is one *channel* of one *voice*. The voice is a player name
(``@piano``) or a row kind (``melody``, ``chords``); the channel is the
dimension being written (``vel``, or anything the writer wants measured).
The cells are bar-aligned: the k-th token of a cell holds the k-th token of
that voice's bar, ``.`` holds its column, and the rows of a voice that runs
across several sections are marked in order, bar after bar.

That is the same positional contract every ``Vel:`` row and named annotation
layer already lives under, so the walk is the same one --
:func:`~plainsong.notation.annotations.walk_bars` -- and a perf value and a
``Vel:`` mark over the same column cannot disagree about which event they
mean. This module owns the grammar and the voice matching; the arranger owns
what a channel *does*, dispatched through :data:`CHANNEL_SEMANTICS` exactly
the way :data:`~plainsong.notation.annotations.ANNOTATION_SEMANTICS` governs
row layers.

v1 values are literals, numbers only. Expressions, recursion and cross-voice
reads are v2, behind the seminar's demonstrated-need door (seminar response
A1): a terminating table today, a language when a real file demands it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .ir import ROLE_CHORDS, ROLE_MELODY, ROLE_PLAYER, ROLE_PERF, Cell, Line

if TYPE_CHECKING:  # imported for typing only
    from .parser import Parser

__all__ = [
    "CHANNEL_SEMANTICS",
    "CHANNEL_ROW_RE",
    "NUMBER_RE",
    "PERF_SECTIONS",
    "parse_channel_row",
    "segment",
    "semantic_for_channel",
    "targets_for",
    "voice_key",
]

#: Section headers that switch the parser into perf mode. Like ``[Stage]``,
#: a ``[Perf]`` section is read, not played: its rows never join a Section
#: and never reach the arranger as music.
PERF_SECTIONS = frozenset({"perf"})

#: Channel name -> registered semantic. A channel with no entry is pure data:
#: preserved, addressed, queryable, with no effect on the compile. Registering
#: a name here is how a channel gains one; ``"velocity"`` is the built-in
#: instance. Mirrors ``ANNOTATION_SEMANTICS`` for row layers on purpose: one
#: extension point per grammar, and the same rule -- a new semantic needs a
#: consumer.
CHANNEL_SEMANTICS: dict[str, str] = {
    "vel": "velocity",
    "velocity": "velocity",
}

# ``@piano.vel | 88 58 . . |`` or ``melody.vel | 64 . |`` -- an optional @,
# a voice name (letters, digits, spaces, ``_`` and ``-``; no dots, so the
# first dot is always the channel separator), a channel word, then the barred
# cells. A row without pipes is not bar-aligned and is not perf.
CHANNEL_ROW_RE = re.compile(
    r"^@?\s*([A-Za-z][A-Za-z0-9 _-]*?)\s*\.\s*([A-Za-z][A-Za-z0-9_-]*)\s*(\|.+)$"
)

#: A literal value: an integer or a decimal, optionally signed. v1's whole
#: expression language.
NUMBER_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")

#: Row kinds a bare voice word may name, without their role constants so the
#: table reads as documentation.
_ROW_KINDS = {
    "melody": ROLE_MELODY,
    "lead": ROLE_MELODY,
    "tune": ROLE_MELODY,
    "chords": ROLE_CHORDS,
    "chord": ROLE_CHORDS,
    "harmony": ROLE_CHORDS,
}


def semantic_for_channel(name: str) -> str:
    """The registered semantic of a channel name, or ``""`` (pure data)."""
    return CHANNEL_SEMANTICS.get(name.strip().lower(), "")


def voice_key(voice: str) -> str:
    """The canonical key of a written voice selector, for conflict reports."""
    return voice.strip().lstrip("@").lower()


def parse_channel_row(line: str, parser: "Parser | None" = None) -> Line | None:
    """Read one ``[Perf]`` row into a :class:`~plainsong.notation.ir.Line`.

    The returned line is a channel row, not music: ``role`` is
    ``ROLE_PERF``, ``name`` is the channel and ``options["voice"]`` the voice
    selector as written. Returns ``None`` for anything that is not a barred
    channel row -- the parser decides how loudly to complain about that.
    """
    match = CHANNEL_ROW_RE.match(line)
    if not match:
        return None
    voice, channel, payload = match.group(1).strip(), match.group(2).strip(), match.group(3)
    cells = [
        Cell(tokens=parser._tokenise(text, ROLE_PERF) if parser else text.split(), line=0)
        for text in _split_cells(payload)
    ]
    if not cells:
        return None
    return Line(
        role=ROLE_PERF,
        name=channel,
        cells=cells,
        options={"voice": voice},
        line_number=0,
        raw=line,
        barred=True,
    )


def _split_cells(payload: str) -> list[str]:
    """Split the row's barred payload into per-bar cell texts.

    Delegates to the parser's own splitter when one is at hand; the local
    copy exists only so the module can be imported without a parser.
    """
    text = payload.strip()
    parts = [part.strip() for part in text.split("|")]
    while parts and not parts[0]:
        parts.pop(0)
    while parts and not parts[-1]:
        parts.pop()
    return parts


def matches_voice(voice: str, line: Line) -> bool:
    """Whether a playable row answers to a written voice selector.

    ``@piano`` matches a player named piano; ``melody`` and its aliases match
    melody rows; ``chords``/``harmony`` match chord rows. Case-insensitive,
    the way every name in the notation is.
    """
    candidate = voice_key(voice)
    if not candidate:
        return False
    if candidate in _ROW_KINDS:
        return line.role == _ROW_KINDS[candidate]
    if line.role == ROLE_PLAYER:
        return line.name.strip().lower() == candidate
    return False


def targets_for(score, voice: str) -> list[Line]:
    """Every playable row of *score* that answers to *voice*, in written order.

    A voice that runs across sections -- the usual case for a lead row or a
    player with several rows -- is one stream, marked bar after bar in the
    order the rows were written, the same order the arranger places them.
    """
    return [
        line
        for section in score.sections
        for line in section.lines
        if line.cells and matches_voice(voice, line)
    ]


def segment(row: Line, offset: int, target: Line) -> tuple[Line, int]:
    """Cut the channel cells that pair with *target*, and the next offset.

    The perf row is one long bar-aligned table; each target row of the voice
    consumes the next ``n`` cells, where ``n`` is how many bars that row
    owns. The cut is returned as a lightweight :class:`Line` carrying the
    same role, channel and voice, so the shared positional walk
    (:func:`~plainsong.notation.annotations.walk_bars`) pairs it with the
    target exactly as it would pair a ``Vel:`` row written above it.

    An unbarred target owns no cells to align against, so its whole remaining
    token run is flattened and paired positionally -- the same flattening
    ``walk_bars`` applies to the target itself.
    """
    if target.barred:
        count = len(target.cells)
        cells = row.cells[offset : offset + count]
        return (
            Line(
                role=ROLE_PERF,
                name=row.name,
                cells=list(cells),
                options=dict(row.options),
                line_number=row.line_number,
                raw=row.raw,
                barred=True,
            ),
            offset + count,
        )
    tokens = [token for cell in row.cells[offset:] for token in cell.tokens]
    return (
        Line(
            role=ROLE_PERF,
            name=row.name,
            cells=[Cell(tokens=list(tokens))],
            options=dict(row.options),
            line_number=row.line_number,
            raw=row.raw,
            barred=False,
        ),
        len(row.cells),
    )
