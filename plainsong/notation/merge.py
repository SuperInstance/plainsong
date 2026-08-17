"""Merging two edits to one score, by the axis the notation already has.

Several agents writing one piece is the normal case for this system, and the
usual answer — take a lock, serialise everything — is stricter than the music
requires. Two agents rewriting `@bass` and `Melody:` are not in conflict in any
sense a musician would recognise. Neither are two agents rewriting bars 1–4 and
bars 5–8 of the same melody.

What makes that checkable rather than hopeful is that every token already has a
coordinate: **row, bar, and position within the bar**. A row is a voice and a
bar is a bar, so an edit occupies a set of `(row, bar)` cells, and two edits
conflict exactly when those sets intersect. That is a decision procedure, not a
heuristic: if the sets are disjoint the merge is defined, and no amount of
locking would have made it more correct.

Cells are compared as written tokens rather than as arranged notes, so a merge
never changes anybody's music by rounding. Whether the merged result *sounds*
right is a separate question the merge does not pretend to answer — two agents
can write compatible bars that make poor harmony together, and that is a
musical judgement rather than a merge conflict.

The base matters. This is a three-way merge: without knowing what both sides
started from, "this row differs" cannot distinguish a change from an absence,
and one agent's untouched copy of an old row would silently revert the other's
work.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ir import Score
from .parser import parse

__all__ = ["Cell", "Edit", "MergeResult", "cells_of", "touched", "merge"]


@dataclass(frozen=True, order=True)
class Cell:
    """One bar of one row, in one section. The unit a merge reasons about."""

    section: int
    row: str        # "chords" | "melody" | "lyrics" | "player:bass"
    bar: int

    def __str__(self) -> str:
        return f"section {self.section + 1}, {self.row}, bar {self.bar + 1}"


@dataclass
class Edit:
    """What one side changed, relative to the base."""

    cells: set[Cell] = field(default_factory=set)
    rows: set[str] = field(default_factory=set)

    def __bool__(self) -> bool:
        return bool(self.cells)


@dataclass
class MergeResult:
    """The outcome, including why it failed when it did."""

    ok: bool
    cells: dict[Cell, list[str]] = field(default_factory=dict)
    conflicts: list[Cell] = field(default_factory=list)
    mine: Edit = field(default_factory=Edit)
    theirs: Edit = field(default_factory=Edit)

    def explain(self) -> str:
        if self.ok:
            return (
                f"{len(self.mine.cells)} cell(s) from one side and "
                f"{len(self.theirs.cells)} from the other, disjoint"
            )
        listed = ", ".join(str(cell) for cell in self.conflicts[:4])
        more = len(self.conflicts) - 4
        return f"both sides changed {listed}{f' and {more} more' if more > 0 else ''}"


def _row_key(line) -> str:
    return f"player:{line.name}" if line.role == "player" else line.role


def cells_of(score: Score) -> dict[Cell, list[str]]:
    """Every written bar of every row, keyed by coordinate.

    A row repeated within a section continues it, so the second `Melody:` row
    carries on where the first stopped. Bars are therefore numbered across the
    whole section rather than restarting per row -- the same rule the arranger
    applies, and getting it wrong here would make two agents appear to edit one
    bar when they edited two.
    """
    out: dict[Cell, list[str]] = {}
    for index, section in enumerate(score.sections):
        offsets: dict[str, int] = {}
        for line in section.lines:
            if not line.cells:
                continue
            key = _row_key(line)
            start = offsets.get(key, 0)
            for bar, cell in enumerate(line.cells):
                out[Cell(index, key, start + bar)] = list(cell.tokens)
            offsets[key] = start + len(line.cells)
    return out


def touched(base: dict[Cell, list[str]], other: dict[Cell, list[str]]) -> Edit:
    """Cells where `other` differs from `base`, in either direction.

    A removed bar counts as touched. Otherwise deleting a row would look like
    no change at all, and the other side's edit to it would be resurrected by a
    merge that believed nobody had objected.
    """
    edit = Edit()
    for cell in set(base) | set(other):
        if base.get(cell) != other.get(cell):
            edit.cells.add(cell)
            edit.rows.add(cell.row)
    return edit


def merge(base: str, mine: str, theirs: str, dialect: str = "auto") -> MergeResult:
    """Three-way merge two edits of one score.

    Returns the merged cells when the two edits are disjoint, and the exact
    coordinates of the disagreement when they are not. Nothing is written and
    nothing is guessed: a cell both sides changed is a conflict even when their
    changes happen to be identical in sound, because the merge reasons about
    what was written.
    """
    base_cells = cells_of(parse(base, dialect=dialect))
    mine_cells = cells_of(parse(mine, dialect=dialect))
    their_cells = cells_of(parse(theirs, dialect=dialect))

    my_edit = touched(base_cells, mine_cells)
    their_edit = touched(base_cells, their_cells)

    overlap = my_edit.cells & their_edit.cells
    # Both sides writing a cell the same way is agreement, not collision.
    conflicts = sorted(
        cell for cell in overlap if mine_cells.get(cell) != their_cells.get(cell)
    )
    if conflicts:
        return MergeResult(
            ok=False, conflicts=conflicts, mine=my_edit, theirs=their_edit
        )

    merged = dict(base_cells)
    for cell in my_edit.cells:
        if cell in mine_cells:
            merged[cell] = mine_cells[cell]
        else:
            merged.pop(cell, None)
    for cell in their_edit.cells:
        if cell in their_cells:
            merged[cell] = their_cells[cell]
        else:
            merged.pop(cell, None)

    return MergeResult(ok=True, cells=merged, mine=my_edit, theirs=their_edit)
