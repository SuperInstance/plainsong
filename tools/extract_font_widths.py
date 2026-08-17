#!/usr/bin/env python3
"""Read glyph advance widths out of a TrueType font, with the standard library.

The SVG renderer computes its own text layout and then declares the answer with
`textLength`, so the browser fits the rendered text to the width we planned for
even when it substitutes a different font. That needs a width table, and the
table has to *ship*: a renderer cannot read a font off the machine it runs on,
because the font is not there on Windows or macOS and this package hardcodes no
paths.

So this generates `plainsong/render/fontmetrics.py` from a real font file. It is
a build-time tool, not part of the product, and it is here rather than in a
scratch directory because the numbers in that module are otherwise unexplained
and unreproducible.

    python3 tools/extract_font_widths.py \\
        /usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf

Liberation Sans is the reference because it is metric-compatible with Arial,
which is the only member of the usual fallback stack whose metrics we can
actually verify -- there is no Helvetica on this machine to diff against, and
Liberation's `M` is 833/1000 em, Arial's figure rather than Helvetica's 889.
"""

from __future__ import annotations

import pathlib
import struct
import sys

#: Everything a chord chart, a section label or a lyric row can contain.
WANTED = (
    "".join(chr(c) for c in range(0x20, 0x7F))       # printable ASCII
    + "°øΔ∆♭♮♯"    # ° ø Δ ∆ ♭ ♮ ♯
    + "–—‘’“”…"    # – — ‘ ’ “ ” …
)


def _tables(data: bytes) -> dict[str, tuple[int, int]]:
    if data[:4] == b"ttcf":
        raise SystemExit("this is a font collection; extract a single face first")
    count = struct.unpack(">H", data[4:6])[0]
    out = {}
    for index in range(count):
        record = 12 + 16 * index
        tag = data[record : record + 4].decode("ascii", "replace")
        offset, length = struct.unpack(">II", data[record + 8 : record + 16])
        out[tag] = (offset, length)
    return out


def _cmap(data: bytes, offset: int):
    """Return a codepoint -> glyph id lookup from a format 4 subtable."""
    count = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
    chosen = None
    for index in range(count):
        record = offset + 4 + 8 * index
        platform, encoding, sub = struct.unpack(">HHI", data[record : record + 8])
        if (platform, encoding) in ((3, 1), (0, 3), (0, 4)):
            chosen = offset + sub
    if chosen is None:
        raise SystemExit("no Unicode cmap subtable found")
    fmt = struct.unpack(">H", data[chosen : chosen + 2])[0]
    if fmt != 4:
        raise SystemExit(f"cmap format {fmt} is not supported; only format 4 is")

    seg_x2 = struct.unpack(">H", data[chosen + 6 : chosen + 8])[0]
    segments = seg_x2 // 2
    ends = struct.unpack(f">{segments}H", data[chosen + 14 : chosen + 14 + seg_x2])
    starts = struct.unpack(f">{segments}H", data[chosen + 16 + seg_x2 : chosen + 16 + 2 * seg_x2])
    deltas = struct.unpack(f">{segments}h", data[chosen + 16 + 2 * seg_x2 : chosen + 16 + 3 * seg_x2])
    range_offset_at = chosen + 16 + 3 * seg_x2
    range_offsets = struct.unpack(f">{segments}H", data[range_offset_at : range_offset_at + seg_x2])

    def lookup(codepoint: int) -> int:
        for index in range(segments):
            if starts[index] <= codepoint <= ends[index]:
                if range_offsets[index] == 0:
                    return (codepoint + deltas[index]) & 0xFFFF
                address = (
                    range_offset_at
                    + 2 * index
                    + range_offsets[index]
                    + 2 * (codepoint - starts[index])
                )
                glyph = struct.unpack(">H", data[address : address + 2])[0]
                return (glyph + deltas[index]) & 0xFFFF if glyph else 0
        return 0

    return lookup


def widths(path: pathlib.Path) -> tuple[str, dict[str, int], list[str]]:
    data = path.read_bytes()
    tables = _tables(data)
    for required in ("head", "hhea", "hmtx", "cmap"):
        if required not in tables:
            raise SystemExit(f"font has no {required} table")

    units_per_em = struct.unpack(">H", data[tables["head"][0] + 18 : tables["head"][0] + 20])[0]
    metric_count = struct.unpack(">H", data[tables["hhea"][0] + 34 : tables["hhea"][0] + 36])[0]
    hmtx = tables["hmtx"][0]
    lookup = _cmap(data, tables["cmap"][0])

    def advance(glyph: int) -> int:
        # Past numberOfHMetrics every glyph repeats the last advance.
        index = min(glyph, metric_count - 1)
        return struct.unpack(">H", data[hmtx + 4 * index : hmtx + 4 * index + 2])[0]

    # The name table would be nicer, but the file name is enough provenance and
    # this tool exists to be read as much as to be run.
    table: dict[str, int] = {}
    missing: list[str] = []
    for character in WANTED:
        glyph = lookup(ord(character))
        if glyph == 0:
            missing.append(character)
            continue
        # Store in 1/1000 em, the AFM convention, rounded to an integer: the
        # error is under a thousandth of an em and the table stays readable.
        table[character] = round(advance(glyph) * 1000 / units_per_em)
    return path.name, table, missing


def emit(
    source: str,
    table: dict[str, int],
    missing: list[str],
    bold_source: str = "",
    bold: dict[str, int] | None = None,
) -> str:
    lines = [
        '"""Glyph advance widths, in units of 1/1000 em.',
        "",
        "Generated by `tools/extract_font_widths.py`. Do not edit by hand: rerun the",
        f"tool against {source}.",
        "",
        "These are Liberation Sans, which is metric-compatible with Arial. That is the",
        "narrowest claim the evidence supports -- no Helvetica was available to diff",
        "against, and Liberation's `M` is 833/1000 em, which is Arial's figure and not",
        "Adobe Helvetica's 889. The renderer names all three in its font stack anyway,",
        "because `textLength` corrects the difference: the width we declare is the width",
        "the browser fits the text to, whichever font it actually has.",
        "",
        "Characters absent from the font are absent here, and `width_of` falls back for",
        "them. The flat and natural signs are the ones that matter:",
        "",
    ]
    for character in missing:
        lines.append(f"    U+{ord(character):04X} {character!r} is not in the font")
    lines += [
        '"""',
        "",
        "from __future__ import annotations",
        "",
        '__all__ = ["WIDTHS", "WIDTHS_BOLD", "MISSING", "UNITS_PER_EM", "SOURCE"]',
        "",
        f'SOURCE = "{source}"',
        f'BOLD_SOURCE = "{bold_source}"',
        "UNITS_PER_EM = 1000",
        "",
        "#: Characters the reference font does not contain at all.",
        "MISSING = (" + ", ".join(f'"\\u{ord(c):04x}"' for c in missing) + ",)",
        "",
        "WIDTHS: dict[str, int] = {",
    ]
    def key_for(character: str) -> str:
        if character == "\\":
            return '"\\\\"'
        if character == '"':
            return "'\"'"
        if ord(character) < 0x7F:
            return f'"{character}"'
        return f'"\\u{ord(character):04x}"'

    for character, width in sorted(table.items()):
        lines.append(f"    {key_for(character)}: {width},")
    lines.append("}")
    lines.append("")
    lines += [
        "#: The bold face, measured separately. Rendering bold against the regular",
        "#: widths makes `lengthAdjust` squeeze every glyph to fit a width the text",
        "#: does not have, which is visible on a chord symbol as smeared letters.",
        "WIDTHS_BOLD: dict[str, int] = {",
    ]
    for character, width in sorted((bold or {}).items()):
        lines.append(f"    {key_for(character)}: {width},")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2
    path = pathlib.Path(argv[1])
    if not path.exists():
        raise SystemExit(f"no such font: {path}")
    source, table, missing = widths(path)

    bold_source, bold = "", {}
    if len(argv) == 3:
        bold_path = pathlib.Path(argv[2])
        if not bold_path.exists():
            raise SystemExit(f"no such font: {bold_path}")
        bold_source, bold, _ = widths(bold_path)

    target = pathlib.Path(__file__).resolve().parent.parent / "plainsong" / "render" / "fontmetrics.py"
    target.write_text(emit(source, table, missing, bold_source, bold), encoding="utf-8")
    print(f"{len(table)} widths from {source}, {len(bold)} bold from {bold_source or '(none)'} -> {target}")
    if missing:
        print("absent from the font: " + " ".join(f"U+{ord(c):04X}" for c in missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
