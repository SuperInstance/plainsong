"""The browser demo is a second implementation, so it can drift.

`docs/demo/index.html` carries its own parser, arranger and MIDI writer in
JavaScript, because the demo has to run with nothing installed. That is a
deliberate exception to "one of everything", and the thing it risks is exactly
what the rule exists to prevent: the page quietly disagreeing with the compiler
it advertises.

CI has no JavaScript runtime, so this cannot run the page. What it can do is
hold the page's own claims against the reference implementation. The page states
the note count it produces for each preset; these tests compile the same
notation with the real compiler and require the same answer. A change to the
arranger that moves a count fails here, which is the reminder to re-check the
demo rather than let it rot.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from plainsong.notation import arrange, parse
from plainsong.notation.arrange import ArrangeOptions

PAGE = Path(__file__).resolve().parent.parent / "docs" / "demo" / "index.html"


def _presets() -> dict[str, str]:
    """The notation the page ships, read out of its PRESETS object."""
    text = PAGE.read_text(encoding="utf-8")
    block = re.search(r"const PRESETS=\{(.*`)\};", text, re.S)
    assert block, "could not find the PRESETS object in the demo page"
    return dict(re.findall(r"(\w+):`(.*?)`", block.group(1), re.S))


def _claimed() -> dict[str, int]:
    text = PAGE.read_text(encoding="utf-8")
    block = re.search(r'<script type="application/json" id="parity">(.*?)</script>', text, re.S)
    assert block, "the demo page carries no parity block"
    return json.loads(block.group(1))


class TestDemoParity(unittest.TestCase):
    def test_the_page_exists_and_is_self_contained(self):
        """No external fetch: the demo must work offline, from a file:// URL."""
        text = PAGE.read_text(encoding="utf-8")
        for forbidden in ("<script src=", "<link rel=\"stylesheet\"", "@import", "fetch(", "XMLHttpRequest"):
            self.assertNotIn(forbidden, text, f"the demo reaches outside itself: {forbidden}")

    def test_every_preset_is_valid_notation(self):
        for name, notation in _presets().items():
            with self.subTest(preset=name):
                score = parse(notation)
                self.assertEqual([d.format() for d in score.errors()], [], name)

    def test_the_note_counts_the_page_claims_are_the_ones_we_produce(self):
        """If this fails, the compiler moved and the demo now misreports it."""
        presets, claimed = _presets(), _claimed()
        self.assertEqual(sorted(presets), sorted(claimed), "a preset has no claimed count")
        for name, notation in presets.items():
            with self.subTest(preset=name):
                arrangement = arrange(parse(notation), ArrangeOptions(humanize=False))
                self.assertEqual(
                    arrangement.note_count,
                    claimed[name],
                    f"{name}: the page says {claimed[name]} notes, the compiler makes "
                    f"{arrangement.note_count}",
                )


if __name__ == "__main__":
    unittest.main()
