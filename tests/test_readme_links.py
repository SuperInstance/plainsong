"""The README is the PyPI project page, so its links have to work from there.

`pyproject.toml` sets `readme = "README.md"`, which means this file is rendered
verbatim as the long description on PyPI. A relative link like
`[notation](docs/notation.md)` resolves on GitHub and 404s on PyPI, and a
relative image does not render at all — which is how the published page came to
tell people to read a dozen documents none of which they could reach, and to run
example files that a `pip install` does not put on disk.

So the links are absolute. The cost of that is losing the guarantee that they
point at something real, since nothing local resolves them any more. This test
buys it back: every GitHub URL into this repository is mapped back to a path and
checked to exist.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

BLOB = "https://github.com/SuperInstance/plainsong/blob/master/"
RAW = "https://raw.githubusercontent.com/SuperInstance/plainsong/master/"

LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")


def targets() -> list[str]:
    return LINK_RE.findall(README.read_text(encoding="utf-8"))


class TestTheReadmeWorksOnPyPI(unittest.TestCase):
    def test_no_relative_links_remain(self):
        """A relative link is invisible on PyPI, silently."""
        relative = [
            t
            for t in targets()
            if not t.startswith(("http://", "https://", "#", "mailto:"))
        ]
        self.assertEqual(relative, [], f"these 404 on the PyPI page: {relative}")

    def test_every_link_into_this_repo_points_at_a_real_file(self):
        missing = []
        for target in targets():
            for prefix in (BLOB, RAW):
                if target.startswith(prefix):
                    path = target[len(prefix) :].split("#")[0]
                    if not (ROOT / path).exists():
                        missing.append(target)
        self.assertEqual(missing, [], f"link points at a file that is not here: {missing}")

    def test_images_use_raw_rather_than_blob(self):
        """A `blob` URL serves an HTML page, so an <img> pointing at one is a
        broken image on PyPI and in any other renderer."""
        images = re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", README.read_text(encoding="utf-8"))
        wrong = [i for i in images if i.startswith(BLOB)]
        self.assertEqual(wrong, [], f"image must use raw.githubusercontent.com: {wrong}")

    def test_the_version_it_claims_is_the_version_in_the_tree(self):
        """The status line said "Version 1.0" while PyPI shipped 1.2.0."""
        from plainsong.version import __version__

        claimed = re.search(r"(?m)^Version (\d+\.\d+)\.", README.read_text(encoding="utf-8"))
        self.assertIsNotNone(claimed, "the README no longer states a version")
        major_minor = ".".join(__version__.split(".")[:2])
        self.assertEqual(
            claimed.group(1),
            major_minor,
            f"README says {claimed.group(1)}, the tree is {__version__}",
        )


if __name__ == "__main__":
    unittest.main()
