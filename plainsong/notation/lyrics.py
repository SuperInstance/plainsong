"""Bind syllables to notes rather than to time of their own.

A lyric row divides its bar independently of the melody, so a word written
directly beneath a note does not sound with it:

    Melody: | A4  .   C5  E5 |     4 tokens -> quarters
    Lyrics: | the tide came  |     3 tokens -> thirds

`came` lands two thirds of a beat after the `C5` it sits under. Every other
notation format says this is simply wrong: syllables bind to *notes*, and the
formats disagree only about the mechanism. MusicXML and MEI attach the syllable
to the note, which makes mismatch inexpressible but is impossible for a
row-based text format. ABC and LilyPond *count* -- they walk a flat syllable
stream in lockstep against the notes. Plainsong is already a flat stream, so
counting it is.

**The barline resyncs.** Each bar's syllables bind to that bar's notes and
nothing carries across. A miscount costs one bar and recovers, instead of
shifting every remaining word in the song. Plainsong writes `|` in every row, so
the mechanism was already in the syntax and merely unhonoured.

**Padding is not melisma.** `proposals/02-the-voyage.md` proposed reading a
sustain token in a lyric row as a melisma, by analogy with ABC's `_`. Real
notation disagrees. Writers use `.` in a lyric row to hold the *column* under a
melody that sustains:

    Melody: | Bb3 .   F4    .   |
    Lyrics: | sing .   every .   |

Two words, two notes. Read as melismas the dots would each consume a note and
`every` would fall off the end of the bar. So a sustain or rest token in a lyric
row is alignment padding and binds to nothing. A syllable held across several
notes still works, and needs no marking: write fewer words than there are notes
and the last one carries to the next word, which is how a lead sheet already
reads.
"""

from __future__ import annotations

from .ir import Diagnostic, LyricEvent
from .parser import REST_TOKENS, SUSTAIN_TOKENS
from .timegrid import TimeGrid

__all__ = ["MODES", "DEFAULT_MODE", "is_padding", "bind"]

MODES = ("independent", "bound")
DEFAULT_MODE = "independent"

#: Rows whose sounding tokens a syllable may be sung on.
_MELODY = "melody"


def is_padding(token: str) -> bool:
    """True for a lyric token that holds a column rather than naming a sound."""
    lowered = token.strip().lower()
    return (
        lowered in SUSTAIN_TOKENS
        or lowered in REST_TOKENS
        or lowered.startswith(("(hold", "(rest", "(sil"))
    )


def bind(grid: TimeGrid) -> tuple[list[LyricEvent], list[Diagnostic]]:
    """Place each syllable on the note it is sung on.

    Returns the events and any diagnostics. Bars with no melody to bind to are
    reported and left for the caller to position however it did before -- there
    is nothing to bind a syllable to, and dropping words silently is the worst
    of the available answers.
    """
    events: list[LyricEvent] = []
    diagnostics: list[Diagnostic] = []
    unbindable: list[int] = []

    by_bar: dict[int, list] = {}
    for placement in grid.placements:
        if placement.row == "lyrics":
            by_bar.setdefault(placement.bar, []).append(placement)

    for bar in sorted(by_bar):
        words = [p for p in sorted(by_bar[bar], key=lambda p: p.unit) if not is_padding(p.token)]
        if not words:
            continue
        targets = sorted(
            (p for p in grid.placements if p.bar == bar and p.row == _MELODY and p.sounds),
            key=lambda p: p.unit,
        )
        if not targets:
            # Nothing to bind to. Keep every token exactly where the bar's own
            # subdivision put it -- the same events this bar produced before --
            # because dropping words silently is the worst available answer.
            unbindable.append(bar)
            for placement in sorted(by_bar[bar], key=lambda p: p.unit):
                events.append(
                    LyricEvent(start=placement.onset, text=placement.token, duration=placement.width)
                )
            continue

        for index, word in enumerate(words[: len(targets)]):
            target = targets[index]
            # A word lasts until the next word's note, so a line with fewer
            # words than notes carries the syllable across them -- melisma
            # without a mark, which is how a lead sheet already reads.
            if index + 1 < min(len(words), len(targets)):
                end = targets[index + 1].onset
            else:
                end = targets[-1].onset + targets[-1].width
            events.append(
                LyricEvent(start=target.onset, text=word.token, duration=max(end - target.onset, 0.0))
            )

        if len(words) > len(targets):
            dropped = len(words) - len(targets)
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    message=f"bar {bar + 1}: {len(words)} syllable(s) for {len(targets)} note(s); "
                    f"{dropped} not sung",
                    hint="the barline resyncs, so only this bar is affected",
                )
            )

    if unbindable:
        shown = ", ".join(str(b + 1) for b in unbindable[:4])
        more = len(unbindable) - 4
        diagnostics.append(
            Diagnostic(
                severity="warning",
                message=f"lyrics in bar(s) {shown}{f' and {more} more' if more > 0 else ''} "
                "have no melody to bind to; left where they were written",
                hint="a syllable is sung on a note, so a Lyrics: row needs a Melody: row "
                "in the same section",
            )
        )

    return events, diagnostics
