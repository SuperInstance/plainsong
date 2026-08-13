"""The 3.10 TOML fallback.

``tomllib`` arrived in 3.11, so on 3.10 configuration is read by
``tapscript/runtime/_toml.py`` instead. A hand-written parser that disagrees
with the real one would be worse than no 3.10 support at all, so these tests
are differential: on 3.11+ every case is parsed by both and the results
compared. On 3.10 the comparison is skipped and only the shape is checked.
"""

from __future__ import annotations

import glob
import sys
import unittest
from pathlib import Path

from tapscript.runtime import _toml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - the 3.10 path
    tomllib = None

REPO = Path(__file__).resolve().parent.parent

CASES = [
    "a = 1\nb = -2\nc = 3.5\nd = 1e3\ne = 1_000\nf = 0xff\ng = 0b101\nh = 0o17\n",
    "a = true\nb = false\n",
    's1 = "hi\\nthere"\ns2 = \'raw\\nnot\'\n',
    's = """\nmulti\nline\n"""\n',
    "s = '''\nliteral\nmulti\n'''\n",
    "arr = [1, 2, 3]\nnested = [[1, 2], [3]]\nmixed = [\"a\", \"b\"]\nempty = []\n",
    "arr = [\n  1,\n  2,  # trailing comment\n]\n",
    "[a]\nx = 1\n[a.b]\ny = 2\n",
    "[[t]]\nn = 1\n\n[[t]]\nn = 2\n",
    'inline = { x = 1, y = "z" }\n',
    "# nothing but a comment\n",
    'q = "with \\"quotes\\" inside"\n',
    'u = "\\u0041\\u00e9"\n',
    'esc = """line \\\n    continued"""\n',
    '"quoted key" = 1\n',
    "a.b.c = 5\n",
    "",
]


@unittest.skipIf(tomllib is None, "tomllib is unavailable, so there is nothing to compare against")
class TestMatchesTomllib(unittest.TestCase):
    """The fallback must agree with the standard library exactly."""

    def test_documents(self):
        for index, text in enumerate(CASES):
            with self.subTest(case=index, text=text[:40]):
                self.assertEqual(_toml.loads(text), tomllib.loads(text))

    def test_every_toml_file_in_the_repository(self):
        paths = sorted(glob.glob(str(REPO / "specs" / "*.toml"))) + [str(REPO / "pyproject.toml")]
        self.assertGreater(len(paths), 3, "expected several TOML files to check against")
        for path in paths:
            with self.subTest(path=Path(path).name):
                text = Path(path).read_text(encoding="utf-8")
                self.assertEqual(_toml.loads(text), tomllib.loads(text))

    def test_binary_load_matches(self):
        path = REPO / "specs" / "core-notation.toml"
        with path.open("rb") as first, path.open("rb") as second:
            self.assertEqual(_toml.load(first), tomllib.load(second))


class TestShape(unittest.TestCase):
    """Checks that hold with or without tomllib present."""

    def test_tables_and_arrays_of_tables(self):
        data = _toml.loads('[spec]\nid = "x"\ntags = ["a", "b"]\n\n[[check]]\nid = "one"\n\n[[check]]\nid = "two"\n')
        self.assertEqual(data["spec"]["id"], "x")
        self.assertEqual(data["spec"]["tags"], ["a", "b"])
        self.assertEqual([check["id"] for check in data["check"]], ["one", "two"])

    def test_multiline_string_drops_the_opening_newline(self):
        self.assertEqual(_toml.loads('why = """\nline one\nline two\n"""\n')["why"], "line one\nline two\n")

    def test_types_are_python_types(self):
        data = _toml.loads("i = 42\nf = 0.5\nb = true\ns = 'x'\n")
        self.assertIsInstance(data["i"], int)
        self.assertIsInstance(data["f"], float)
        self.assertIsInstance(data["b"], bool)
        self.assertIsInstance(data["s"], str)

    def test_unsupported_value_is_refused_not_guessed(self):
        # Dates are valid TOML but not implemented. Silently returning a string
        # would be worse than saying so.
        with self.assertRaises(_toml.TOMLDecodeError):
            _toml.loads("when = 1979-05-27T07:32:00Z\n")

    def test_errors_carry_a_line_number(self):
        with self.assertRaises(_toml.TOMLDecodeError) as caught:
            _toml.loads("a = 1\nb = \n")
        self.assertIn("line", str(caught.exception))

    def test_duplicate_key_is_refused(self):
        with self.assertRaises(_toml.TOMLDecodeError):
            _toml.loads("a = 1\na = 2\n")

    def test_unterminated_string_is_refused(self):
        with self.assertRaises(_toml.TOMLDecodeError):
            _toml.loads('a = "no closing quote\n')


class TestUsedByTheSystem(unittest.TestCase):
    """The fallback has to satisfy the code that reads configuration."""

    def test_specs_load_through_the_fallback(self):
        from tapscript import specs

        original = specs.tomllib
        specs.tomllib = _toml
        try:
            loaded = specs.load_specs()
        finally:
            specs.tomllib = original
        self.assertGreaterEqual(len(loaded), 4)
        for spec in loaded:
            self.assertTrue(spec.title)
            self.assertTrue(spec.checks, f"{spec.id} lost its checks")

    def test_config_reads_through_the_fallback(self):
        import tempfile

        from tapscript.runtime import config

        original = config.tomllib
        config.tomllib = _toml
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.toml"
                path.write_text('[llm]\nprovider = "gemini"\n\n[web]\nport = 9111\n')
                data = config._read_toml(path)
        finally:
            config.tomllib = original
        self.assertEqual(data["llm"]["provider"], "gemini")
        self.assertEqual(data["web"]["port"], 9111)

    def test_round_trips_what_the_emitter_writes(self):
        from tapscript.runtime.config import dumps_toml

        payload = {
            "llm": {"provider": "xai", "model": "grok-4", "temperature": 0.7, "max_retries": 3},
            "agent": {"transcript": True, "auto_approve": False},
        }
        self.assertEqual(_toml.loads(dumps_toml(payload)), payload)


@unittest.skipIf(sys.version_info >= (3, 11), "only meaningful where tomllib is absent")
class TestOnPython310(unittest.TestCase):  # pragma: no cover - runs on 3.10 only
    def test_the_fallback_is_the_one_in_use(self):
        from tapscript.runtime import config

        self.assertIs(config.tomllib, _toml)


if __name__ == "__main__":
    unittest.main()
