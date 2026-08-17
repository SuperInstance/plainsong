#!/usr/bin/env python3
"""Run notation through the browser demo and the Python compiler, and compare.

`docs/demo/index.html` carries its own parser, arranger and MIDI writer in
JavaScript, because the landing page has to run with nothing installed. That is
the one deliberate exception to "one of everything", and the thing it risks is
exactly what the rule exists to prevent: the page quietly disagreeing with the
compiler it advertises.

`tests/test_demo.py` guards what it can without a JavaScript runtime -- the
lookup tables, the token classes, the note counts the page claims. It cannot
execute the page. This script can, and it compares the one thing that matters:
**pitch, start and duration of every note.**

That is not a hypothetical gap. The demo shipped with `.` and `-` in its REST
set where the compiler has them in SUSTAIN, so `| Am . . . |` played a one-beat
chord and three beats of silence instead of a chord lasting the bar. Every held
note on the front door was cut to a single subdivision. Note *counts* were
identical -- a rest and a sustain both add no note -- so the parity test passed
throughout. Running this script against that revision reports six of eight cases
differing, every difference a duration.

CI does not run this: the suite installs nothing and assumes no browser. Run it
by hand after touching either implementation.

    python3 tools/demo_differential.py
    DEMO_PAGE=/path/to/other.html python3 tools/demo_differential.py

Needs a Chromium binary. Set CHROME if it is not on PATH or in the usual
Playwright location.
"""

from __future__ import annotations

import html
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = pathlib.Path(os.environ.get("DEMO_PAGE", ROOT / "docs" / "demo" / "index.html"))

CASES: dict[str, str] = {
    "6/8": (
        "**TRACK: Six**\n[MetaData]\nkey: C | tempo: 90 | time: 6/8\n\n"
        "[V1] (Verse - 2 Bars)\n"
        "Melody: | C4 D4 E4 F4 G4 A4 | B4 . . C5 . . |\n"
        "Chords: | C . . | G . . |\n"
    ),
    "triplets": (
        "**TRACK: Tri**\n[MetaData]\nkey: C | tempo: 100 | time: 4/4\n\n"
        "[V1] (Verse - 1 Bars)\nMelody: | C4 E4 G4 |\n"
    ),
    "3/4": (
        "**TRACK: W**\n[MetaData]\nkey: C | tempo: 120 | time: 3/4\n\n"
        "[V1] (Verse - 2 Bars)\nChords: | C . . | G . . |\nMelody: | E4 . G4 | D4 . B3 |\n"
    ),
    "sustains": (
        "**TRACK: S**\n[MetaData]\nkey: C | tempo: 60 | time: 4/4\n\n"
        "[V1] (Verse - 1 Bars)\nChords: | Am . . . |\nMelody: | A4 - - E5 |\n"
    ),
    "rests": (
        "**TRACK: R**\n[MetaData]\nkey: C | tempo: 60 | time: 4/4\n\n"
        "[V1] (Verse - 1 Bars)\nMelody: | C4 _ E4 x |\n"
    ),
    "stacks": (
        "**TRACK: St**\n[MetaData]\nkey: C | tempo: 60 | time: 4/4\n\n"
        "[V1] (Verse - 1 Bars)\nMelody: | c3-e3-g3 . . . |\n"
    ),
    "repeated rows": (
        "**TRACK: Rep**\n[MetaData]\nkey: C | tempo: 60 | time: 4/4\n\n"
        "[V1] (Verse - 2 Bars)\nMelody: | C4 . . . |\nMelody: | D4 . . . |\n"
    ),
    "chord qualities": (
        "**TRACK: Q**\n[MetaData]\nkey: C | tempo: 60 | time: 4/4\n\n"
        "[V1] (Verse - 2 Bars)\nChords: | CM7 . D9 . | G7alt . EbMaj7 . |\n"
    ),
}

Note = list  # [pitch, start, duration]


def find_chrome() -> str:
    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    for pattern in ("chromium-*/chrome-linux/chrome", "chromium_headless_shell-*/chrome-linux/headless_shell"):
        for path in sorted(pathlib.Path("/opt/pw-browsers").glob(pattern), reverse=True):
            return str(path)
    raise SystemExit("no Chromium found; set CHROME=/path/to/chrome")


def through_the_page(chrome: str, notation: str, workdir: pathlib.Path) -> list[Note] | None:
    """Compile `notation` inside the real page and read the notes back out."""
    source = PAGE.read_text(encoding="utf-8")
    probe = (
        "\nsource.value=" + json.dumps(notation) + ";compileNow();"
        "document.title='P:'+JSON.stringify(current.notes.map("
        "n=>[n.pitch,+n.beat.toFixed(4),+n.beats.toFixed(4)]).sort());\n"
    )
    cut = source.rindex("</script>")
    page = workdir / "differential.html"
    page.write_text(source[:cut] + probe + source[cut:], encoding="utf-8")
    result = subprocess.run(
        [chrome, "--headless", "--no-sandbox", "--disable-gpu",
         "--virtual-time-budget=600", "--dump-dom", f"file://{page}"],
        capture_output=True, text=True,
    )
    found = re.search(r"<title>P:(.*?)</title>", result.stdout, re.S)
    return json.loads(html.unescape(found.group(1))) if found else None


def through_the_compiler(notation: str) -> list[Note]:
    from plainsong.notation import arrange, parse
    from plainsong.notation.arrange import ArrangeOptions

    arrangement = arrange(parse(notation), ArrangeOptions(humanize=False))
    return sorted(
        [n.pitch, round(n.start, 4), round(n.duration, 4)]
        for track in arrangement.tracks
        for n in track.notes
    )


def main() -> int:
    sys.path.insert(0, str(ROOT))
    chrome = find_chrome()
    workdir = pathlib.Path(os.environ.get("TMPDIR", "/tmp"))
    print(f"page  {PAGE}\nchrome {chrome}\n")
    disagreed = 0
    for name, notation in CASES.items():
        page_notes = through_the_page(chrome, notation, workdir)
        real = through_the_compiler(notation)
        if page_notes is None:
            print(f"  {name:16} THE PAGE RETURNED NOTHING")
            disagreed += 1
            continue
        page_notes = sorted(page_notes)
        if page_notes == real:
            print(f"  {name:16} ok    {len(real):3d} notes, pitch/start/duration identical")
            continue
        disagreed += 1
        print(f"  {name:16} DIFFER  page={len(page_notes)} compiler={len(real)}")
        # The lengths legitimately differ when one side produces more notes --
        # that is a finding to report, not an error to raise.
        for a, b in zip(page_notes, real, strict=False):
            if a != b:
                print(f"      page {a}   compiler {b}")
        for extra in page_notes[len(real):]:
            print(f"      page only {extra}")
        for missing in real[len(page_notes):]:
            print(f"      compiler only {missing}")
    print("\nall agree" if not disagreed else f"\n{disagreed} case(s) disagree")
    return 1 if disagreed else 0


if __name__ == "__main__":
    raise SystemExit(main())
