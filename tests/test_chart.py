"""The SVG chord chart.

Phase 3 of `proposals/02-the-voyage.md`. The chart is a projection of the time
matrix -- a chord's x position is `unit * bar_width` -- so the thing worth
testing hardest is that it forms no opinion of its own about where anything is,
and that nothing reaches the page which cannot be drawn.
"""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from plainsong import pipeline
from plainsong.render.chart import (
    THICK_BARLINE,
    THIN_BARLINE,
    ChartOptions,
    fold,
    render,
    text_width,
    unrenderable,
)
from plainsong.render.fontmetrics import MISSING, WIDTHS, WIDTHS_BOLD

SONG = (
    "**TRACK: Autumn Light**\n[MetaData]\nkey: Cmaj | tempo: 92 | time: 4/4\n\n"
    "[V1] (Verse - 2 Bars)\n"
    "Chords: | Cmaj7 . Am7 . | Dm7 . G7 . |\n"
    "Melody: | E4 . A4 . | D5 . B4 . |\n"
    "Lyrics: | the light is | low across the |\n"
)


def chart(text: str = SONG, options: ChartOptions | None = None) -> str:
    return render(pipeline.compile_text(text).arrangement, options)


class TestItIsAFileYouCanShip(unittest.TestCase):
    def test_it_is_well_formed_xml(self):
        root = ET.fromstring(chart())
        self.assertTrue(root.tag.endswith("svg"))

    def test_it_reaches_outside_itself_for_nothing(self):
        """GitHub renders a chart as `<img src=...>`, which cannot fetch a
        webfont, run script, or load a stylesheet. Anything external is a
        blank space on somebody's README."""
        svg = chart()
        # The SVG namespace is an identifier rather than something fetched, and
        # is the one URL a standalone chart may legitimately contain.
        self.assertEqual(svg.count("http://www.w3.org/2000/svg"), 1)
        without_namespace = svg.replace("http://www.w3.org/2000/svg", "")
        for forbidden in ("http://", "https://", "@import", "<script", "xlink:href", "url("):
            self.assertNotIn(
                forbidden, without_namespace, f"the chart reaches outside itself: {forbidden}"
            )

    def test_the_same_notation_draws_the_same_bytes(self):
        self.assertEqual(chart(), chart())

    def test_it_carries_a_background(self):
        # An `<img>` cannot inherit the host page's colour, so a transparent
        # chart is black text on black in a dark README.
        self.assertIn('class="paper"', chart())


class TestNothingUndrawableReachesThePage(unittest.TestCase):
    """Liberation Sans has U+266F but not U+266D or U+266E, so a chart may not
    carry a flat or a natural sign whatever the source spelled."""

    def test_the_font_really_is_missing_the_flat(self):
        self.assertIn("♭", MISSING)
        self.assertIn("♮", MISSING)
        self.assertNotIn("♯", MISSING)

    def test_unicode_accidentals_are_folded(self):
        self.assertEqual(fold("E7♭9"), "E7b9")
        self.assertEqual(fold("F♯"), "F#")
        self.assertEqual(fold("B♮"), "Bn")

    def test_a_song_written_with_unicode_flats_draws_ascii(self):
        svg = chart(
            "**TRACK: U**\n[MetaData]\nkey: Am | tempo: 100 | time: 4/4\n\n"
            "[V1] (Verse - 1 Bars)\nChords: | E7♭9 . B♭ . |\n"
        )
        self.assertEqual(unrenderable(svg), [])
        self.assertIn("E7b9", svg)
        self.assertIn("Bb", svg)

    def test_unrenderable_reports_what_would_not_draw(self):
        self.assertEqual(unrenderable("Bb"), [])
        # `fold` is applied first, so only something with no mapping survives.
        self.assertEqual(unrenderable("♭"), [])


class TestTextHoldsTheWidthItWasMeasuredFor(unittest.TestCase):
    def test_every_text_declares_its_length(self):
        root = ET.fromstring(chart())
        texts = [e for e in root.iter() if e.tag.endswith("}text")]
        self.assertTrue(texts)
        for element in texts:
            self.assertIn("textLength", element.attrib, ET.tostring(element))
            self.assertEqual(element.attrib.get("lengthAdjust"), "spacingAndGlyphs")

    def test_spacing_and_glyphs_rather_than_spacing(self):
        """`spacing` distributes the n-1 gaps between characters, so a
        single-character chord symbol has nothing to adjust and a substituted
        font renders at its own width. Quoted from the SVG2 spec."""
        self.assertNotIn('lengthAdjust="spacing"', chart())

    def test_the_declared_length_is_the_measured_advance(self):
        size = 28.0
        self.assertAlmostEqual(
            text_width("Am", size), (WIDTHS["A"] + WIDTHS["m"]) * size / 1000.0
        )

    def test_bold_is_measured_bold(self):
        # `m`, `b` and `j` differ between the faces, and those are exactly the
        # letters chord symbols are made of. Measuring regular and drawing bold
        # makes lengthAdjust smear every glyph.
        self.assertNotEqual(WIDTHS["m"], WIDTHS_BOLD["m"])
        self.assertGreater(text_width("Cmaj7", 28.0, bold=True), text_width("Cmaj7", 28.0))

    def test_an_unknown_character_does_not_collapse_to_zero(self):
        # A zero width would stack the following glyphs on top of it.
        self.assertGreater(text_width("中", 28.0), 0.0)


class TestTheChartAgreesWithTheGrid(unittest.TestCase):
    """The renderer must not form a second opinion about where a chord is."""

    def test_a_chord_sits_at_its_unit_within_the_bar(self):
        arrangement = pipeline.compile_text(SONG).arrangement
        placements = [
            p for p in arrangement.grid.placements if p.kind == "chord" and p.bar == 0
        ]
        units = sorted(p.unit for p in placements)
        self.assertEqual([round(u, 3) for u in units], [0.0, 0.5])

    def test_chords_written_on_a_melody_row_are_drawn(self):
        """In the relative dialect a row mixing roman numerals with scale
        degrees reads as melody. A chart taking only the `Chords:` row draws a
        page of empty bars for a piece whose harmony is written down plainly."""
        svg = chart(
            "[V1]\n| i 1 . | VII 7 . |\n"
        )
        self.assertIn("VII", svg)

    def test_an_empty_piece_still_draws_something(self):
        svg = chart("[V1]\nMelody: | C4 . . . |\n")
        ET.fromstring(svg)   # must not raise


class TestBarsAreAsWideAsTheirContents(unittest.TestCase):
    def test_a_crowded_bar_widens_the_chart(self):
        narrow = chart(
            "**TRACK: N**\n[MetaData]\nkey: C | tempo: 100 | time: 4/4\n\n"
            "[V1] (Verse - 1 Bars)\nChords: | C . . . |\n"
        )
        wide = chart(
            "**TRACK: W**\n[MetaData]\nkey: C | tempo: 100 | time: 4/4\n\n"
            "[V1] (Verse - 1 Bars)\nChords: | Cmaj7#11 Abm7b5 Db7alt Gbmaj9 |\n"
        )
        self.assertGreater(_svg_width(wide), _svg_width(narrow))

    def test_symbols_in_one_bar_do_not_overlap(self):
        svg = chart(
            "**TRACK: W**\n[MetaData]\nkey: C | tempo: 100 | time: 4/4\n\n"
            "[V1] (Verse - 1 Bars)\nChords: | Cmaj7#11 Abm7b5 Db7alt Gbmaj9 |\n"
        )
        root = ET.fromstring(svg)
        chords = [
            e
            for e in root.iter()
            if e.tag.endswith("}text") and "chord" in e.attrib.get("class", "")
        ]
        placed = sorted(
            (float(e.attrib["x"]), float(e.attrib["textLength"])) for e in chords
        )
        for (x, width), (next_x, _) in zip(placed, placed[1:], strict=False):
            self.assertLessEqual(x + width, next_x + 1e-6, f"{x}+{width} overruns {next_x}")


class TestEngravingConstants(unittest.TestCase):
    """Read out of `steinbergmedia/bravura` rather than remembered."""

    def test_barline_thicknesses_are_bravuras(self):
        self.assertEqual(THIN_BARLINE, 0.16)
        self.assertEqual(THICK_BARLINE, 0.5)

    def test_only_the_closing_barline_is_thick(self):
        """The left edge of the final bar is an interior barline, however near
        the end of the piece it falls. Drawing it thick puts a double bar in
        the middle of the last system."""
        svg = chart(
            "**TRACK: T**\n[MetaData]\nkey: C | tempo: 100 | time: 4/4\n\n"
            "[V1] (Verse - 2 Bars)\nChords: | C . . . | G . . . |\n"
        )
        root = ET.fromstring(svg)
        rules = [e for e in root.iter() if e.tag.endswith("}line")]
        verticals = [e for e in rules if e.attrib["x1"] == e.attrib["x2"]]
        widths = [float(e.attrib["stroke-width"]) for e in verticals]
        thick = [w for w in widths if w > THIN_BARLINE * 7.0 * 1.5]
        self.assertEqual(len(thick), 1, f"expected one thick barline, got {widths}")
        # And it is the rightmost line on the system.
        rightmost = max(verticals, key=lambda e: float(e.attrib["x1"]))
        self.assertGreater(float(rightmost.attrib["stroke-width"]), THIN_BARLINE * 7.0 * 1.5)

    def test_the_em_is_divided_into_four_staff_spaces(self):
        # SMuFL scoring metrics: one staff space is 0.25 em. The 0.2 em figure
        # that appears in the same specification is for *text* metrics, glyphs
        # set inline in prose, which is not what a chart is.
        options = ChartOptions(staff_space=10.0)
        self.assertEqual(options.font_size, 40.0)


def _svg_width(svg: str) -> float:
    return float(ET.fromstring(svg).attrib["width"])


if __name__ == "__main__":
    unittest.main()
