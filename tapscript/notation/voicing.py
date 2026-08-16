"""Choosing which notes of a chord actually sound, and where.

A chord symbol names more notes than a texture usually wants. Something has to
decide what to leave out, and the engine this replaced decided by taking the
lowest four:

    D9   ->  D F# A C E     written
             D F# A C       played

Which is `D7`. Every ninth chord in the corpus lost its ninth this way, and
`E7#9` -- the chord the whole Hendrix record is built on -- came out as `E7`.
The cap itself is defensible; four voices is a reasonable default. Taking the
bottom four is not, because it discards in exactly the order a musician keeps.

A player thinning a voicing drops the fifth first and the root second. The
third and the seventh stay, because they are what distinguish major from minor
from dominant, and the extension stays, because it is the reason the symbol was
written that way at all. That ordering is the whole content of this module.

Which strategy is the default was decided by measurement rather than taste --
see `docs/voicing.md` for the scores. The comparison is reproducible:

    python3 -m tapscript voicing --compare
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["STRATEGIES", "voice", "Voicing", "DEFAULT_STRATEGY"]

DEFAULT_STRATEGY = "guide"

#: What a degree is worth when something has to go.
#:
#: Lower keeps. The fifth leaves first because it reinforces the root and adds
#: no colour; the root leaves next because in an ensemble a bass instrument is
#: usually playing it anyway. The third and seventh are last because they *are*
#: the chord's identity. Everything above the seventh sits between the two
#: groups: more expendable than a guide tone, far less expendable than a fifth.
DROP_ORDER: dict[int, int] = {
    5: 0,    # first to go
    1: 1,    # then the root
    11: 2,   # then the eleventh, which is the muddiest extension
    9: 3,
    13: 4,
    6: 5,
    2: 5,
    4: 5,
    3: 9,    # never, in practice
    7: 9,
}

#: Degrees whose natural form is plain but whose altered form is the point.
#: A `C7#5` that loses its sharp fifth is a `C7`; the alteration has to be
#: treated as identity rather than as decoration, or the drop order throws away
#: the very note the symbol was written for.
NATURAL: dict[int, int] = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11, 9: 14, 11: 17, 13: 21}


@dataclass(frozen=True)
class Voicing:
    """The notes chosen, and what was left out."""

    notes: tuple[int, ...]
    dropped: tuple[int, ...] = ()

    def __iter__(self):
        return iter(self.notes)

    def __len__(self) -> int:
        return len(self.notes)


def _altered(degrees: dict[int, int]) -> set[int]:
    """Degrees sitting somewhere other than their natural place."""
    return {d for d, offset in degrees.items() if d in NATURAL and offset != NATURAL[d]}


def _ranked(degrees: dict[int, int]) -> list[int]:
    """Degrees in the order they should be given up.

    An altered degree is promoted to the same rank as a guide tone: it is why
    the chord is called what it is called.
    """
    altered = _altered(degrees)
    return sorted(
        degrees,
        key=lambda d: (9 if d in altered else DROP_ORDER.get(d, 5), -d),
    )


def _stack(degrees: dict[int, int], root: int, limit: int) -> Voicing:
    """The old behaviour: lowest notes first. Kept so it can be measured."""
    offsets = sorted(set(degrees.values()))
    return Voicing(tuple(root + o for o in offsets[:limit]), tuple(offsets[limit:]))


def _guide(degrees: dict[int, int], root: int, limit: int) -> Voicing:
    """Keep identity and colour; give up the fifth, then the root.

    The notes stay in their written register, so this changes *which* notes
    sound and not where they sit. That keeps it a small, reviewable change
    against the old behaviour -- register is a separate argument.
    """
    keep = set(_ranked(degrees)[-limit:]) if limit else set(degrees)
    offsets = sorted(degrees[d] for d in keep)
    dropped = sorted(degrees[d] for d in degrees if d not in keep)
    return Voicing(tuple(root + o for o in offsets), tuple(dropped))


def _shell(degrees: dict[int, int], root: int, limit: int) -> Voicing:
    """Root, third, seventh, and the highest extension. The pianist's left hand."""
    wanted: list[int] = []
    for degree in (1, 3, 7):
        if degree in degrees:
            wanted.append(degree)
    extensions = sorted((d for d in degrees if d > 7 or d in (2, 4, 6)), reverse=True)
    wanted.extend(extensions)
    keep = wanted[:limit] if limit else wanted
    offsets = sorted(degrees[d] for d in keep)
    dropped = sorted(degrees[d] for d in degrees if d not in keep)
    return Voicing(tuple(root + o for o in offsets), tuple(dropped))


def _drop2(degrees: dict[int, int], root: int, limit: int) -> Voicing:
    """`_guide`, then the second voice from the top moved down an octave.

    The standard four-part spacing for guitar and for horn sections. It opens
    out a close cluster, which is what makes an extension audible as colour
    rather than as a crunch against its neighbour.
    """
    close = _guide(degrees, root, limit)
    notes = list(close.notes)
    if len(notes) >= 3:
        notes[-2] -= 12
        notes.sort()
    return Voicing(tuple(notes), close.dropped)


def _spread(degrees: dict[int, int], root: int, limit: int) -> Voicing:
    """`_guide`, with the lowest note dropped an octave to clear the middle.

    Wide at the bottom, close at the top, which is how the harmonic series is
    arranged and roughly how a piano voicing sits.
    """
    close = _guide(degrees, root, limit)
    notes = list(close.notes)
    if len(notes) >= 3 and notes[0] - 12 >= 24:
        notes[0] -= 12
    return Voicing(tuple(sorted(notes)), close.dropped)


STRATEGIES = {
    "stack": _stack,
    "guide": _guide,
    "shell": _shell,
    "drop2": _drop2,
    "spread": _spread,
}


def voice(
    chord,
    octave: int = 3,
    limit: int = 4,
    strategy: str = DEFAULT_STRATEGY,
) -> Voicing:
    """Choose the sounding notes for *chord*.

    Falls back to the plain stack when a chord carries no degree map -- roman
    numerals build one directly from intervals -- because without degree labels
    there is no way to tell a fifth from a seventh, and guessing would be worse
    than the old behaviour it replaces.
    """
    root = (octave + 1) * 12 + chord.root_pc
    degrees = getattr(chord, "degrees", None)
    if not degrees:
        offsets = sorted(set(chord.intervals()))
        kept = offsets[:limit] if limit else offsets
        return Voicing(tuple(root + o for o in kept), tuple(offsets[len(kept):]))

    chosen = STRATEGIES.get(strategy, _guide)(degrees, root, limit)
    notes = [n for n in chosen.notes if 0 <= n <= 127]

    if chord.bass_pc is not None and chord.bass_pc != chord.root_pc:
        bass = (octave + 1) * 12 + chord.bass_pc
        while notes and bass >= notes[0]:
            bass -= 12
        if bass >= 0:
            notes.insert(0, bass)
    return Voicing(tuple(notes), chosen.dropped)
