"""The Overture Boot: one score, two actualizations, one state.

Casey's doctrine under test: a game grown out of a quilt construct starts
with all its state features played as starting notes. The same
``examples/overture-boot.song`` compiles to audio (the boot plays as an
overture) and parses to game-state JSON (``tools/overture_to_state.py``),
and the two must agree -- the seed voice you hear hashed into the world seed
is the seed voice the state tool read.

These tests are deliberately independent of the annotation-rows work: they
build on the Vel: machinery's pattern, unknown ``Name:`` rows kept as data,
and would keep passing if that capability later arrives.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from plainsong import pipeline
from plainsong.notation.ir import ROLE_ANNOTATION, ROLE_NOTE

ROOT = Path(__file__).resolve().parents[1]
SONG = ROOT / "examples" / "overture-boot.song"
TOOL = ROOT / "tools" / "overture_to_state.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("overture_to_state", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


overture_to_state = _load_tool()


class TestTheOvertureParses(unittest.TestCase):
    def test_it_compiles_with_annotation_rows_kept_as_data(self):
        result = pipeline.compile_text(SONG.read_text(encoding="utf-8"))
        self.assertTrue(result.ok)
        # The Score:/Bg:/Seed: rows are info-level annotations, never warnings.
        severities = [d.severity for d in result.score.diagnostics]
        self.assertNotIn("warning", severities)
        self.assertNotIn("error", severities)
        names = {line.name for s in result.score.sections for line in s.lines
                 if line.role in (ROLE_NOTE, ROLE_ANNOTATION)}
        self.assertEqual(names, {"Score", "Bg", "Seed"})

    def test_every_state_voice_actually_plays(self):
        # Success is not evidence: count the notes, not the exit code.
        result = pipeline.compile_text(SONG.read_text(encoding="utf-8"))
        tracks = {t.name: t for t in result.arrangement.tracks}
        self.assertEqual(len(tracks["bass"].notes), 8)      # the seed melody
        self.assertEqual(len(tracks["melody"].notes), 7)    # the player state


class TestTheStateActualization(unittest.TestCase):
    TEXT = SONG.read_text(encoding="utf-8")

    def test_parsing_twice_yields_identical_json(self):
        first = json.dumps(overture_to_state.overture_state(self.TEXT), sort_keys=True)
        second = json.dumps(overture_to_state.overture_state(self.TEXT), sort_keys=True)
        self.assertEqual(first, second)

    def test_the_cli_is_deterministic_across_processes(self):
        runs = []
        for _ in range(2):
            out = subprocess.run(
                [sys.executable, str(TOOL), str(SONG)],
                capture_output=True, text=True, check=True, cwd=ROOT,
            )
            runs.append(out.stdout)
        self.assertEqual(runs[0], runs[1])

    def test_the_state_reads_what_was_written(self):
        state = overture_to_state.overture_state(self.TEXT)
        self.assertEqual(state["player"], {
            "hp": 100, "lives": 3, "position": [5, 0], "energy": 86,
        })
        self.assertEqual(state["score"], {"start": 0, "high_scores": [480, 360, 240]})
        self.assertEqual(state["background"], ["night", "stars", "ridge", "grid"])
        self.assertEqual(state["rng"], {
            "spawn": 42, "drop": 1337, "weather": 777, "encounter": 9001,
        })

    def test_a_different_seed_note_grows_a_different_world(self):
        # One semitone in the seed voice, everything else untouched.
        mutated = self.TEXT.replace("e2 . a1 .", "f2 . a1 .", 1)
        self.assertNotEqual(mutated, self.TEXT, "the mutation did not take")
        was = overture_to_state.overture_state(self.TEXT)["world"]
        now = overture_to_state.overture_state(mutated)["world"]
        self.assertNotEqual(was["seed"], now["seed"])
        self.assertNotEqual(was["hash"], now["hash"])
        # And the player state is untouched by a terrain change: the melody
        # is the player, the bass is the world, and neither leaks into the other.
        player_was = overture_to_state.overture_state(self.TEXT)["player"]
        player_now = overture_to_state.overture_state(mutated)["player"]
        self.assertEqual(player_was, player_now)


class TestBothActualizationsAgree(unittest.TestCase):
    TEXT = SONG.read_text(encoding="utf-8")

    def test_the_seed_voice_you_hear_is_the_seed_that_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "overture.wav"
            result = pipeline.compile_text(self.TEXT, audio=audio)
            self.assertTrue(result.ok)
            self.assertTrue(result.audio_path is not None and result.audio_path.exists())
            self.assertGreater(result.audio_path.stat().st_size, 100_000)  # really renders
            heard = overture_to_state.bass_pitches(result.arrangement)
        state = overture_to_state.overture_state(self.TEXT)
        self.assertEqual(heard, [int(n) for n in state["world"]["from"].split(",")])
        self.assertEqual(state["world"]["from"], "40,33,36,31,38,33,40,33")


if __name__ == "__main__":
    unittest.main()
