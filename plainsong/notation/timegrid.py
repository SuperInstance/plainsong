"""A common time matrix for every token, whether or not it makes a sound.

Rows subdivide their bars independently. That is the whole point of the
notation -- three tokens in a bar are triplets no matter what the row above
did -- but it means vertical alignment carries no meaning to the compiler:

    Chords: | Am  .   .   .  |     4 tokens -> quarters
    Melody: | A4  .   C5  E5 |     4 tokens -> quarters
    Lyrics: | the tide came  |     3 tokens -> thirds

``came`` is written directly beneath ``C5``. ``C5`` sounds on beat 2.0 and
``came`` lands on beat 2.667, because the lyric row divided the bar into three
and the melody divided it into four. A reader trusts the column; nothing in the
compiler could see it, warn about it, or draw it.

``TimeGrid`` gives every token a position computed **the same way** -- a lyric
and a note go through one function, which is what lets a renderer put them in
one column and a merge reason about them in one space. Three things fall out of
it that were previously separate problems:

* rendering is ``x = unit * bar_width``, a coordinate transform rather than a
  layout engine;
* merging is set intersection on ``(row, bar, unit)``, so two agents editing
  different rows *provably* cannot collide -- the row axis is disjoint;
* linting can finally express "this row disagrees with its neighbours".

This module only records and answers questions. It emits no diagnostics and
changes no timing: the arranger populates it from positions it has already
computed, so if building the grid ever moved a note, the grid would be wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Placement", "TimeGrid"]

# Bar boundaries are compared with a tolerance because onsets are produced by
# division: a bar-3 downbeat can arrive as 11.999999999999998.
_EPSILON = 1e-9


@dataclass(frozen=True)
class Placement:
    """One written token, positioned on the common matrix."""

    token: str
    row: str        # "chords" | "melody" | "lyrics" | "player:bass"
    kind: str       # note | chord | sustain | rest | text
    bar: int        # absolute bar index from the start of the piece
    onset: float    # beats from the start of the piece
    width: float    # beats
    unit: float     # position within its own bar, 0.0 <= unit < 1.0

    @property
    def sounds(self) -> bool:
        return self.kind in {"note", "chord"}


@dataclass
class TimeGrid:
    """Every token in every row, on one coordinate system."""

    bar_beats: float = 4.0
    placements: list[Placement] = field(default_factory=list)

    def add(self, *, token: str, row: str, kind: str, onset: float, width: float) -> Placement:
        """Place one token. ``bar`` and ``unit`` are derived here and nowhere
        else, so that a lyric and a note cannot drift apart by being computed
        in two places."""
        beats = self.bar_beats or 4.0
        position = onset / beats
        # Nudge before flooring. Onsets are produced by division, so a bar-3
        # downbeat arrives as 11.999999999999998; flooring that lands the token
        # in bar 2, a whole bar from where it was written.
        bar = int(position + _EPSILON)
        unit = position - bar
        if unit < _EPSILON:
            unit = 0.0
        placement = Placement(
            token=token, row=row, kind=kind, bar=bar, onset=onset, width=width, unit=unit
        )
        self.placements.append(placement)
        return placement

    def __len__(self) -> int:
        return len(self.placements)

    def __bool__(self) -> bool:
        return bool(self.placements)

    def rows(self) -> dict[str, list[Placement]]:
        """Placements grouped by row, in the order the rows first appear."""
        out: dict[str, list[Placement]] = {}
        for placement in self.placements:
            out.setdefault(placement.row, []).append(placement)
        return out

    def in_bar(self, bar: int) -> list[Placement]:
        """Every placement in one bar, ordered by position then row."""
        return sorted(
            (p for p in self.placements if p.bar == bar),
            key=lambda p: (p.unit, p.row),
        )

    def bars(self) -> list[int]:
        return sorted({p.bar for p in self.placements})

    def subdivisions(self, bar: int) -> dict[str, int]:
        """How many tokens each row wrote in one bar.

        This is the raw material for the alignment question: rows whose counts
        differ are rows whose columns do not mean what they look like.
        """
        counts: dict[str, int] = {}
        for placement in self.placements:
            if placement.bar == bar:
                counts[placement.row] = counts.get(placement.row, 0) + 1
        return counts

    def disagreements(self) -> list[tuple[int, dict[str, int]]]:
        """Bars where the rows do not divide the bar the same way.

        Reported, never enforced. Uneven subdivision is legal and often
        deliberate -- a held chord under a running melody is two tokens against
        sixteen, and there is nothing wrong with it. What this answers is the
        narrower question a renderer and a linter both need: *in this bar, does
        a column mean anything?*
        """
        out: list[tuple[int, dict[str, int]]] = []
        for bar in self.bars():
            counts = self.subdivisions(bar)
            if len(set(counts.values())) > 1:
                out.append((bar, counts))
        return out

    def column(self, bar: int, unit: float, tolerance: float = 1e-6) -> list[Placement]:
        """Every token standing at one position in one bar -- the tokens a
        reader would say are in the same column, as opposed to the ones that
        merely look that way."""
        return sorted(
            (
                p
                for p in self.placements
                if p.bar == bar and abs(p.unit - unit) <= tolerance
            ),
            key=lambda p: p.row,
        )
