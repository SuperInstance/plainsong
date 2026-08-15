"""Paths, configuration, capabilities, transforms, specs and the CLI."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tapscript.interfaces.cli import main
from tapscript.library import Library
from tapscript.notation import arrange, parse
from tapscript.runtime.capabilities import probe
from tapscript.runtime.config import DEFAULTS, dumps_toml, load_config
from tapscript.runtime.paths import Paths, find_project_root
from tapscript.specs import load_specs, verify_all
from tapscript.transform import describe, retempo, to_text, transpose

PIECE = """**TRACK: Runtime Test**
[MetaData]
key: Am | tempo: 100 | swing: 10% | subdivision: 8th
time: 3/4 | mood: Steady

[V1] (Verse)
Chords: | Am . . | F . . |
Melody: | A4 C5 E5 | F4 A4 C5 |
Lyrics: | one two three | four five six |
@bass | a1 . e2 | f1 . c2 | vel: 70
"""


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestPaths(unittest.TestCase):
    def test_environment_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {"TAPSCRIPT_CONFIG_DIR": directory}):
                self.assertEqual(str(Paths().config_dir), directory)

    def test_project_root_detection(self):
        self.assertIsNotNone(find_project_root(Path(__file__).parent))

    def test_workspace_is_project_local_inside_a_project(self):
        paths = Paths(project_root=Path("/tmp/example-project"))
        self.assertEqual(paths.workspace, Path("/tmp/example-project/.tapscript/workspace"))

    def test_no_home_directory_is_hardcoded(self):
        """Regression: earlier versions wrote to a fixed ~/.openclaw path."""
        source = Path(__file__).resolve().parent.parent / "tapscript"
        offenders = []
        for path in source.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for marker in ("~/.openclaw", "/home/eileen", "/Users/"):
                if marker in text:
                    offenders.append(f"{path.name}: {marker}")
        self.assertEqual(offenders, [])


class TestConfig(unittest.TestCase):
    def test_defaults_are_present(self):
        config = load_config()
        self.assertEqual(config.get("core", "bar_fill"), "rescale")
        self.assertEqual(config.get("render", "ticks_per_beat"), 480)

    def test_environment_overrides_defaults(self):
        with mock.patch.dict(os.environ, {"TAPSCRIPT_PROVIDER": "deepseek"}):
            self.assertEqual(load_config().get("llm", "provider"), "deepseek")

    def test_typed_environment_coercion(self):
        with mock.patch.dict(os.environ, {"TAPSCRIPT_WEB_PORT": "9000"}):
            self.assertEqual(load_config().get("web", "port"), 9000)

    def test_file_is_read(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "config.toml").write_text('[llm]\nprovider = "gemini"\n')
            with mock.patch.dict(os.environ, {"TAPSCRIPT_CONFIG_DIR": directory}, clear=False):
                self.assertEqual(load_config().get("llm", "provider"), "gemini")

    def test_save_writes_only_the_differences(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {"TAPSCRIPT_CONFIG_DIR": directory}, clear=False):
                config = load_config()
                config.set("llm", "provider", "xai")
                target = config.save()
            text = target.read_text()
            self.assertIn('provider = "xai"', text)
            self.assertNotIn("ticks_per_beat", text)

    def test_toml_emitter_handles_types(self):
        text = dumps_toml({"s": {"a": "x", "b": 2, "c": True, "d": 1.5}})
        self.assertIn('a = "x"', text)
        self.assertIn("b = 2", text)
        self.assertIn("c = true", text)

    def test_every_default_section_is_documented(self):
        for section in ("core", "render", "llm", "agent", "web"):
            self.assertIn(section, DEFAULTS)


class TestCapabilities(unittest.TestCase):
    def test_probe_reports_python(self):
        report = probe(refresh=True)
        self.assertTrue(report.has("python"))
        self.assertIn("capabilities available", report.summary())

    def test_serialisable(self):
        json.dumps(probe().as_dict())

    def test_host_agent_detection(self):
        with mock.patch.dict(os.environ, {"TAPSCRIPT_HOST_AGENT": "openclaw"}, clear=False):
            self.assertTrue(probe(refresh=True).has("host_agent"))


class TestTransform(unittest.TestCase):
    def test_round_trip_preserves_the_music(self):
        original = parse(PIECE)
        again = parse(to_text(original))
        self.assertEqual(arrange(original).note_count, arrange(again).note_count)
        self.assertEqual(again.meta.title, "Runtime Test")
        self.assertEqual(str(again.meta.meter), "3/4")
        self.assertEqual(again.meta.swing, 0.1)

    def test_transpose_moves_chords_and_melody(self):
        moved = parse(transpose(PIECE, "Cm"))
        self.assertEqual(moved.meta.key.name(), "Cm")
        self.assertIn("Cm", to_text(moved))
        first = arrange(parse(PIECE)).tracks[1].notes[0].pitch
        second = arrange(moved).tracks[1].notes[0].pitch
        self.assertEqual(second - first, 3)

    def test_transpose_by_semitones(self):
        self.assertEqual(parse(transpose(PIECE, 2)).meta.key.name(), "Bm")

    def test_lyrics_are_left_alone(self):
        self.assertIn("one two three", transpose(PIECE, "F"))

    def test_player_rows_keep_their_velocity(self):
        self.assertIn("vel: 70", transpose(PIECE, "D"))

    def test_retempo(self):
        self.assertEqual(parse(retempo(PIECE, 84)).meta.tempo, 84)

    def test_describe_is_serialisable(self):
        json.dumps(describe(PIECE))


class TestLibrary(unittest.TestCase):
    def setUp(self):
        self.library = Library()

    def test_finds_notation(self):
        self.assertGreater(len(self.library), 0)

    def test_search_matches_titles(self):
        results = self.library.search("hallelujah", limit=5)
        self.assertTrue(any("hallelujah" in entry.title.lower() for entry in results))

    def test_find_by_name(self):
        first = self.library.all()[0]
        self.assertEqual(self.library.find(first.name).path, first.path)

    def test_collections(self):
        self.assertGreater(sum(self.library.collections().values()), 0)


class TestSpecs(unittest.TestCase):
    def test_specs_load(self):
        specs = load_specs()
        self.assertGreaterEqual(len(specs), 4)
        for spec in specs:
            self.assertTrue(spec.title)
            self.assertTrue(spec.checks, f"{spec.id} has no checks")

    def test_all_specs_pass(self):
        failures = [result for result in verify_all() if result.status == "FAIL"]
        self.assertEqual(
            failures,
            [],
            "\n".join(
                f"{result.spec.id}: {check.id} -- {check.detail}"
                for result in failures
                for check in result.failures
            ),
        )


class TestCli(unittest.TestCase):
    def test_version(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--version")
        self.assertEqual(caught.exception.code, 0)

    def test_help_when_bare(self):
        code, out, _err = run_cli()
        self.assertEqual(code, 0)
        self.assertIn("usage", out)

    def test_new_then_info_then_compile(self):
        with tempfile.TemporaryDirectory() as directory:
            song = Path(directory) / "song.tap"
            self.assertEqual(run_cli("new", "Test Song", "-o", str(song))[0], 0)
            self.assertTrue(song.exists())

            code, out, _err = run_cli("info", str(song))
            self.assertEqual(code, 0)
            self.assertIn("Test Song", out)

            code, _out, _err = run_cli(
                "compile", str(song), "-o", str(Path(directory) / "out.mid"),
                "--audio", str(Path(directory) / "out.wav"),
            )
            self.assertEqual(code, 0)
            self.assertTrue((Path(directory) / "out.mid").exists())
            self.assertTrue((Path(directory) / "out.wav").exists())

    def test_json_output_is_parseable(self):
        with tempfile.TemporaryDirectory() as directory:
            song = Path(directory) / "song.tap"
            run_cli("new", "Json Song", "-o", str(song))
            code, out, _err = run_cli("--json", "info", str(song))
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["title"], "Json Song")

    def test_check_reports_a_broken_file(self):
        with tempfile.TemporaryDirectory() as directory:
            broken = Path(directory) / "broken.tap"
            broken.write_text("this file has no notation in it at all\n")
            code, _out, err = run_cli("check", str(broken))
            self.assertEqual(code, 1)
            self.assertIn("error", err)

    def test_check_passes_a_good_file(self):
        with tempfile.TemporaryDirectory() as directory:
            song = Path(directory) / "song.tap"
            run_cli("new", "Good", "-o", str(song))
            self.assertEqual(run_cli("check", str(song))[0], 0)

    def test_transpose_to_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            song = Path(directory) / "song.tap"
            run_cli("new", "Move Me", "-o", str(song))
            code, out, _err = run_cli("transpose", str(song), "C")
            self.assertEqual(code, 0)
            self.assertIn("key: C", out)

    def test_missing_file_is_reported(self):
        code, _out, err = run_cli("compile", "/definitely/not/here.tap")
        self.assertEqual(code, 2)
        self.assertIn("no such file", err)

    def test_doctor_runs(self):
        code, out, _err = run_cli("doctor")
        self.assertEqual(code, 0)
        self.assertIn("python", out)

    def test_providers_lists_the_catalogue(self):
        code, out, _err = run_cli("providers")
        self.assertEqual(code, 0)
        self.assertIn("openrouter", out)

    def test_config_get_and_list(self):
        self.assertEqual(run_cli("config", "get", "core.bar_fill")[1].strip(), "rescale")
        self.assertIn("[render]", run_cli("config", "list")[1])

    def test_the_two_version_numbers_agree(self):
        """`version.py` calls itself the single source of truth; packaging duplicates it.

        A release is a pushed tag, and the number in the wheel comes from
        `pyproject.toml` while everything a user sees at runtime comes from
        `version.py`. If they drift, `tapscript --version` reports one thing and
        `pip show` another, and the release that revealed it is already published.
        """
        import re
        from pathlib import Path

        from tapscript.version import __version__

        pyproject = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(
            encoding="utf-8"
        )
        declared = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject)
        self.assertIsNotNone(declared, "pyproject.toml has no version")
        self.assertEqual(
            declared.group(1),
            __version__,
            "pyproject.toml and tapscript/version.py disagree",
        )


if __name__ == "__main__":
    unittest.main()
