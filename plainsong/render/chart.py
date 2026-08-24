"""A chord chart as SVG, with no dependencies and no font on the machine.

The layout is a projection of `Arrangement.grid`: a chord's horizontal position
is `unit * bar_width`, where `unit` is the position it already occupies inside
its bar. That is the whole reason the time matrix exists — the renderer forms no
opinion of its own about where anything is, so a chart cannot disagree with the
MIDI file about when a chord arrives.

Three things decide how this looks, all of them checked against primary sources
rather than recalled:

**Text is measured, then declared.** Widths come from `fontmetrics.py`, and each
`<text>` carries `textLength` with `lengthAdjust="spacingAndGlyphs"`. SVG treats
both as geometry rather than style, so the browser fits the rendered string to
the width we planned for even when it substitutes a different font. `spacing`
alone would not do: it distributes the *n−1* gaps between characters, so for a
single-character chord symbol like `C` there is nothing to adjust and a
substituted font renders at its own width.

**One staff space is 0.25 em.** SMuFL registers glyphs two ways — scoring
metrics at 0.25 em per staff space and text metrics at 0.2 em — and a chart
drawn with Bravura's `engravingDefaults` is using the scoring figures, so it
wants 0.25. Those defaults, read from `bravura-1.481`: a thin barline is 0.16
staff spaces and a thick one 0.5.

**The flat sign is not in the font.** Liberation Sans carries U+266F ♯ and not
U+266D ♭ or U+266E ♮, which is the wrong half to lose for a corpus full of
flats. Accidentals are folded to ASCII on the way out, whatever the source
spelled.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..notation.ir import Arrangement
from .fontmetrics import MISSING, WIDTHS, WIDTHS_BOLD

__all__ = ["ChartOptions", "render", "text_width"]

# Bravura engravingDefaults, in staff spaces.
THIN_BARLINE = 0.16
THICK_BARLINE = 0.5

#: SMuFL scoring metrics: one staff space is a quarter of the em.
STAFF_SPACES_PER_EM = 4.0

#: The font has no flat and no natural, so nothing may reach the output holding
#: one. Sharp is folded too, for a chart that spells accidentals one way.
_FOLD = {"♭": "b", "♮": "n", "♯": "#", "∆": "Δ"}

_FALLBACK_WIDTH = 556
"""Used for a character the reference font does not contain. The digit width,
which is close to the average and never zero -- a zero would stack glyphs."""


@dataclass
class ChartOptions:
    """Everything about the drawing, in staff spaces unless stated."""

    staff_space: float = 7.0  # px; the one number the chart scales from
    bars_per_line: int = 4
    bar_width: float = 16.0  # staff spaces
    line_height: float = 7.5  # staff spaces between system baselines
    margin: float = 3.5  # staff spaces
    show_lyrics: bool = True
    title: bool = True

    @property
    def font_size(self) -> float:
        return self.staff_space * STAFF_SPACES_PER_EM


def fold(text: str) -> str:
    """Rewrite characters the reference font cannot draw."""
    return "".join(_FOLD.get(character, character) for character in text)


def text_width(text: str, font_size: float, bold: bool = False) -> float:
    """Advance width of a string, in the same units as `font_size`.

    The weight matters. Measuring the regular face and rendering bold makes
    `lengthAdjust` squeeze every glyph into a width the text does not have,
    which shows up on a chord symbol as visibly smeared letters -- and `m`,
    `b` and `j` are exactly where the two faces differ.
    """
    table = WIDTHS_BOLD if bold else WIDTHS
    total = sum(table.get(character, _FALLBACK_WIDTH) for character in text)
    return total * font_size / 1000.0


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _text(x: float, y: float, body: str, size: float, cls: str, anchor: str = "start") -> str:
    """A `<text>` that holds the width it was laid out for.

    `textLength` is the measured advance and `lengthAdjust="spacingAndGlyphs"`
    makes the browser honour it whatever font it ends up using.
    """
    body = fold(body)
    if not body.strip():
        return ""
    width = text_width(body, size, bold="chord" in cls)
    return (
        f'<text class="{cls}" x="{x:.2f}" y="{y:.2f}" textLength="{width:.2f}" '
        f'lengthAdjust="spacingAndGlyphs" text-anchor="{anchor}">{_escape(body)}</text>'
    )


def _chords_by_bar(arrangement: Arrangement) -> dict[int, list[tuple[float, str]]]:
    """Chord symbols keyed by bar, as (unit, token), from the time matrix.

    Taken from every row, not only `Chords:`. A melody row may legitimately
    carry a chord symbol and the arranger already honours that; in the relative
    dialect a row mixing roman numerals with scale degrees is read as melody,
    so a chart reading only the chord row draws a page of empty bars for a piece
    whose harmony is written down plainly.
    """
    seen: dict[int, dict[float, str]] = {}
    for placement in arrangement.grid.placements:
        if placement.kind != "chord":
            continue
        bar = seen.setdefault(placement.bar, {})
        # A dedicated chord row wins a tie: it is the one written to be read.
        if placement.unit not in bar or placement.row == "chords":
            bar[placement.unit] = placement.token
    return {bar: sorted(units.items()) for bar, units in seen.items()}


def _required_width(items: list[tuple[float, str]], size: float, bold: bool, gap: float) -> float:
    """The narrowest bar width at which none of these items overlap.

    Each item sits at `unit * width`, so the next one starting at `next_unit`
    is clear only when `width * (next_unit - unit)` covers this item's advance
    plus a gap. Taking the largest such requirement over the bar gives the
    width exactly, with no guessing and no iteration. Two items written at the
    same position cannot be separated by any width, so they are skipped rather
    than driving it to infinity.
    """
    need = 0.0
    for index, (unit, token) in enumerate(items):
        following = items[index + 1][0] if index + 1 < len(items) else 1.0
        span = following - unit
        if span <= 1e-9:
            continue
        need = max(need, (text_width(fold(token), size, bold) + gap) / span)
    return need


def _lyrics_by_bar(arrangement: Arrangement, bar_beats: float) -> dict[int, list[tuple[float, str]]]:
    out: dict[int, list[tuple[float, str]]] = {}
    for event in arrangement.lyrics:
        if not event.text.strip():
            continue
        bar = int(event.start / bar_beats + 1e-9)
        unit = (event.start - bar * bar_beats) / bar_beats
        out.setdefault(bar, []).append((max(unit, 0.0), event.text))
    for bar in out:
        out[bar].sort()
    return out


def _sections_by_bar(arrangement: Arrangement, bar_beats: float) -> dict[int, str]:
    return {int(beat / bar_beats + 1e-9): name for name, beat in arrangement.section_starts if name}


_STYLE = """
:root { color-scheme: light dark; }
.paper  { fill: #faf8f4; }
.ink    { fill: #1a1714; }
.rule   { stroke: #1a1714; }
.faint  { fill: #6f6862; }
.chord  { font-weight: 700; }
text { font-family: Liberation Sans, Arial, Helvetica, sans-serif; }
@media (prefers-color-scheme: dark) {
  .paper { fill: #14120f; }
  .ink   { fill: #f2ede6; }
  .rule  { stroke: #f2ede6; }
  .faint { fill: #9a938c; }
}
"""


def render(arrangement: Arrangement, options: ChartOptions | None = None) -> str:
    """Draw a chord chart. Returns a complete, standalone SVG document."""
    options = options or ChartOptions()
    space = options.staff_space
    size = options.font_size
    bar_beats = arrangement.meta.meter.beats_per_bar

    chords = _chords_by_bar(arrangement)
    lyrics = _lyrics_by_bar(arrangement, bar_beats) if options.show_lyrics else {}
    sections = _sections_by_bar(arrangement, bar_beats)

    bars = sorted(set(chords) | set(lyrics) | set(sections))
    if not bars:
        bars = [0]
    last_bar = max(bars)

    per_line = max(1, options.bars_per_line)
    lines = last_bar // per_line + 1
    margin = options.margin * space

    # The bar is as wide as its contents need. Having real widths is the point
    # of measuring: `Cmaj7 . Am7 .` and `C . . .` do not need the same room, and
    # a fixed width either wastes half the page or overlaps the symbols.
    bar_w = max(
        options.bar_width * space,
        max(
            (_required_width(items, size, True, space * 0.9) for items in chords.values()),
            default=0.0,
        ),
        max(
            (_required_width(items, size * 0.7, False, space * 0.5) for items in lyrics.values()),
            default=0.0,
        ),
    )

    line_h = options.line_height * space
    if lyrics:
        line_h += space * 2.2  # room for the words, and for the next section label

    heading = size * 2.3 if (options.title and arrangement.meta.title) else 0.0
    width = margin * 2 + bar_w * per_line
    height = margin * 2 + heading + line_h * lines

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.2f} {height:.2f}" role="img" '
        f'aria-label="{_escape(fold(arrangement.meta.title or "chord chart"))}">',
        f"<style>{_STYLE}</style>",
        f'<rect class="paper" width="{width:.2f}" height="{height:.2f}"/>',
    ]

    if heading:
        parts.append(_text(margin, margin + size, arrangement.meta.title, size * 1.15, "ink"))
        # On its own line rather than beside the title: a long title and a
        # right-aligned metadata line collide, and which one wins depends on
        # the title, so there is no width at which the layout is safe.
        meta_line = (
            f"{arrangement.meta.key.text}  ·  {arrangement.meta.meter}  ·  {arrangement.meta.tempo:g} bpm"
        )
        parts.append(_text(margin, margin + size * 1.95, meta_line, size * 0.62, "faint"))

    top = margin + heading
    for index in range(lines):
        y = top + line_h * index
        baseline = y + line_h * 0.62
        first = index * per_line

        # The staff line every bar sits on. One rule per system rather than per
        # bar, so a bar with nothing in it still reads as a bar. It stops at the
        # last real bar: a final system holding one bar should not draw a rule
        # across three bars that do not exist.
        filled = min(per_line, last_bar - first + 1)
        parts.append(
            f'<line class="rule" x1="{margin:.2f}" y1="{baseline + space * 0.9:.2f}" '
            f'x2="{margin + bar_w * filled:.2f}" y2="{baseline + space * 0.9:.2f}" '
            f'stroke-width="{THIN_BARLINE * space:.2f}" opacity="0.28"/>'
        )

        for column in range(per_line):
            bar = first + column
            if bar > last_bar:
                break
            x = margin + bar_w * column

            # Always thin: this is the *opening* edge of a bar, which is an
            # interior barline however near the end of the piece it falls. Only
            # the line that closes the last bar is thick.
            parts.append(
                f'<line class="rule" x1="{x:.2f}" y1="{baseline - space * 2.4:.2f}" '
                f'x2="{x:.2f}" y2="{baseline + space * 0.9:.2f}" '
                f'stroke-width="{THIN_BARLINE * space:.2f}"/>'
            )

            if bar in sections:
                parts.append(
                    _text(x + space * 0.4, baseline - space * 3.0, sections[bar], size * 0.6, "faint")
                )

            for unit, symbol in chords.get(bar, []):
                # Left-aligned to the beat, not centred on it: confirmed
                # against working practice, and the casual "centred over the
                # beat" phrasing found elsewhere is imprecise.
                parts.append(_text(x + space * 0.5 + unit * bar_w, baseline, symbol, size, "ink chord"))

            for unit, word in lyrics.get(bar, []):
                parts.append(
                    _text(x + space * 0.5 + unit * bar_w, baseline + space * 2.6, word, size * 0.7, "faint")
                )

        # The closing barline of the system.
        if first <= last_bar:
            columns = min(per_line, last_bar - first + 1)
            x = margin + bar_w * columns
            final = first + columns - 1 == last_bar
            parts.append(
                f'<line class="rule" x1="{x:.2f}" y1="{baseline - space * 2.4:.2f}" '
                f'x2="{x:.2f}" y2="{baseline + space * 0.9:.2f}" '
                f'stroke-width="{(THICK_BARLINE if final else THIN_BARLINE) * space:.2f}"/>'
            )

    parts.append("</svg>")
    return "\n".join(part for part in parts if part) + "\n"


def unrenderable(text: str) -> list[str]:
    """Characters that would not draw, after folding. Empty is the good answer."""
    return [character for character in fold(text) if character in MISSING]
