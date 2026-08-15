"""The ensemble layer: claims, versions, atomic writes and a deterministic merge.

The property under test is the one the design exists for: several agents write
one score at the same time without corrupting each other. Two voices at once
both land; two writes to one voice from the same base do not, and the loser is
told what to rebase onto.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tapscript.agent.tools import Sandbox, ToolRegistry
from tapscript.mcp import ensemble
from tapscript.mcp.server import Server
from tapscript.runtime.config import load_config

BASS = "[A]\n@bass | a1 . e2 . | f1 . c2 . |\n"
BASS_REVISED = "[A]\n@bass | a1 e2 a2 e2 | f1 c2 f2 c2 |\n"
VIOLIN = "[A]\n@violin1 | e4 . a4 . | c5 . f4 . |\n"
CHORDS = "[A]\nChords: | Am . . . | F . . . |\n"


class SessionTest(unittest.TestCase):
    """A session in a temporary directory, never in the user's workspace."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.session = ensemble.open_session(
            "harbour",
            root=self.root,
            title="Harbour Lights",
            key="Am",
            tempo=96,
            meter="4/4",
            bars=2,
            sections=[{"name": "A", "description": "Verse - 2 Bars", "bars": 2}],
            voices=["@bass", "@violin1", "chords"],
        )


class TestOpening(SessionTest):
    def test_a_session_is_a_directory_with_a_manifest(self) -> None:
        self.assertTrue((self.root / "harbour" / "manifest.json").is_file())
        self.assertTrue((self.root / "harbour" / "parts").is_dir())
        manifest = self.session.manifest()
        self.assertEqual(manifest.key, "Am")
        self.assertEqual(manifest.tempo, 96)
        self.assertEqual(manifest.section_names(), ["A"])

    def test_reopening_keeps_what_is_there(self) -> None:
        self.session.write_part("bass", "alice", BASS, 0, "first pass")
        again = ensemble.open_session("harbour", root=self.root, key="C", tempo=200)
        self.assertEqual(again.manifest().key, "Am", "reopening must not rewrite the header")
        self.assertEqual(again.manifest().voices["bass"].summary, "first pass")

    def test_sessions_are_listed(self) -> None:
        ensemble.open_session("second", root=self.root)
        self.assertEqual(ensemble.list_sessions(self.root), ["harbour", "second"])

    def test_a_missing_session_names_the_ones_that_exist(self) -> None:
        with self.assertRaises(ensemble.EnsembleError) as caught:
            ensemble.find_session("nowhere", root=self.root)
        self.assertIn("harbour", str(caught.exception))

    def test_names_are_checked(self) -> None:
        for bad in ("../escape", "one/two", ""):
            with self.subTest(name=bad), self.assertRaises(ensemble.EnsembleError):
                ensemble.open_session(bad, root=self.root)


class TestClaims(SessionTest):
    def test_a_voice_has_one_owner(self) -> None:
        self.session.join("@bass", "alice")
        with self.assertRaises(ensemble.EnsembleError) as caught:
            self.session.join("@bass", "bob")
        self.assertIn("alice", str(caught.exception))
        self.assertIn("@violin1", str(caught.exception), "the refusal should name a free voice")

    def test_joining_returns_everything_needed_to_start(self) -> None:
        state = self.session.join("@bass", "alice")
        self.assertEqual(state["meta"]["key"], "Am")
        self.assertEqual(state["you"]["voice"], "@bass")
        self.assertTrue(state["you"]["yours"])
        self.assertEqual(state["you"]["base_version"], 0)

    def test_a_released_voice_can_be_taken(self) -> None:
        self.session.join("@bass", "alice")
        self.session.leave("@bass", "alice")
        self.session.join("@bass", "bob")
        self.assertEqual(self.session.manifest().voices["bass"].owner, "bob")

    def test_only_the_owner_may_release(self) -> None:
        self.session.join("@bass", "alice")
        with self.assertRaises(ensemble.EnsembleError):
            self.session.leave("@bass", "bob")

    def test_takeover_is_possible_but_explicit(self) -> None:
        self.session.join("@bass", "alice")
        self.session.join("@bass", "bob", takeover=True)
        self.assertEqual(self.session.manifest().voices["bass"].owner, "bob")
        actions = [entry["action"] for entry in self.session.entries()]
        self.assertIn("takeover", actions)

    def test_a_held_voice_refuses_another_agents_write(self) -> None:
        self.session.join("@bass", "alice")
        with self.assertRaises(ensemble.EnsembleError) as caught:
            self.session.write_part("bass", "bob", BASS, 0)
        self.assertIn("held by alice", str(caught.exception))


class TestWriting(SessionTest):
    def test_a_part_is_written_and_versioned(self) -> None:
        result = self.session.write_part("bass", "alice", BASS, 0, "walking line")
        self.assertTrue(result["accepted"])
        self.assertEqual(result["bars"], 2)
        self.assertTrue((self.root / "harbour" / "parts" / "bass.tap").is_file())
        self.assertEqual(self.session.manifest().voices["bass"].version, result["version"])

    def test_invalid_notation_never_lands(self) -> None:
        with self.assertRaises(ensemble.EnsembleError) as caught:
            self.session.write_part("bass", "alice", "[A]\nnothing playable in here\n", 0)
        self.assertIn("not written", str(caught.exception))
        self.assertIn("nothing to play", str(caught.exception))
        self.assertFalse((self.root / "harbour" / "parts" / "bass.tap").exists())

    def test_a_part_may_only_speak_for_its_own_voice(self) -> None:
        with self.assertRaises(ensemble.EnsembleError) as caught:
            self.session.write_part("violin1", "carol", BASS, 0)
        self.assertIn("only contain @violin1 rows", str(caught.exception))

    def test_a_part_without_a_section_goes_in_the_first_one(self) -> None:
        self.session.write_part("bass", "alice", "@bass | a1 . e2 . |", 0)
        self.assertIn("[A]", self.session.score())

    def test_writing_leaves_no_temporary_files_behind(self) -> None:
        self.session.write_part("bass", "alice", BASS, 0)
        leftovers = [
            path.name
            for path in (self.root / "harbour").rglob("*")
            if path.name.endswith(".tmp")
        ]
        self.assertEqual(leftovers, [])

    def test_every_change_is_logged(self) -> None:
        self.session.join("@bass", "alice")
        self.session.write_part("bass", "alice", BASS, 0, "walking line under the verse")
        entries = self.session.entries()
        self.assertEqual(entries[0]["action"], "open")
        self.assertEqual(entries[-1]["voice"], "bass")
        self.assertEqual(entries[-1]["agent"], "alice")
        self.assertEqual(entries[-1]["summary"], "walking line under the verse")
        self.assertEqual([entry["version"] for entry in entries], [1, 2, 3])

    def test_line_endings_do_not_change_the_bytes(self) -> None:
        self.session.write_part("bass", "alice", BASS.replace("\n", "\r\n"), 0)
        self.assertEqual(self.session.part("bass"), BASS)


class TestLockAcquisition(SessionTest):
    """Taking the lock has to survive what the platform actually raises."""

    def test_a_delete_pending_lock_is_waited_out_not_raised(self) -> None:
        """Windows reports a delete-pending file as PermissionError.

        When one writer releases the lock while another is taking it, Windows
        raises PermissionError from os.open rather than FileExistsError. Both
        mean "somebody has it, wait"; treating only the latter as contention
        made a concurrent claim fail outright.
        """
        real_open = os.open
        calls = {"n": 0}

        def flaky_open(path, flags, *args, **kwargs):
            if str(path).endswith(ensemble.LOCK):
                calls["n"] += 1
                if calls["n"] <= 3:
                    raise PermissionError(13, "Permission denied")
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(os, "open", flaky_open):
            self.session.join("cello", "agent-cello")

        self.assertGreater(calls["n"], 3, "the lock should have been retried")
        self.assertEqual(self.session.manifest().voices["cello"].owner, "agent-cello")

    def test_an_unwritable_directory_is_reported_not_disguised(self) -> None:
        """A real permission problem must not masquerade as contention."""

        def always_denied(path, flags, *args, **kwargs):
            raise PermissionError(13, "Permission denied")

        with mock.patch.object(os, "open", always_denied):
            with self.assertRaises(ensemble.EnsembleError) as caught:
                ensemble._FileLock(self.session.directory, timeout=0.05).__enter__()
        message = str(caught.exception)
        self.assertIn("PermissionError", message)
        self.assertIn("writable", message)


class TestConcurrency(SessionTest):
    """The property the whole design exists for."""

    def _write(self, results: dict, voice: str, agent: str, content: str, base: int) -> None:
        try:
            results[agent] = self.session.write_part(voice, agent, content, base, f"{agent} wrote")
        except ensemble.EnsembleError as exc:
            results[agent] = exc

    def test_two_agents_on_two_voices_both_succeed(self) -> None:
        results: dict = {}
        threads = [
            threading.Thread(target=self._write, args=(results, "bass", "alice", BASS, 0)),
            threading.Thread(target=self._write, args=(results, "violin1", "bob", VIOLIN, 0)),
            threading.Thread(target=self._write, args=(results, "chords", "carol", CHORDS, 0)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        for agent, outcome in results.items():
            self.assertNotIsInstance(outcome, Exception, f"{agent}: {outcome}")
            self.assertTrue(outcome["accepted"])
        versions = sorted(outcome["version"] for outcome in results.values())
        self.assertEqual(len(set(versions)), 3, "each write should get its own version")
        merged = self.session.score()
        for fragment in ("@bass", "@violin1", "Chords:"):
            self.assertIn(fragment, merged)

    def test_two_agents_on_one_voice_from_one_base_leave_one_winner(self) -> None:
        results: dict = {}
        started = threading.Barrier(2)

        def write(agent: str, content: str) -> None:
            started.wait(timeout=5)
            self._write(results, "bass", agent, content, 0)

        threads = [
            threading.Thread(target=write, args=("alice", BASS)),
            threading.Thread(target=write, args=("bob", BASS_REVISED)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        winners = [agent for agent, outcome in results.items() if not isinstance(outcome, Exception)]
        losers = [agent for agent, outcome in results.items() if isinstance(outcome, Exception)]
        self.assertEqual(len(winners), 1, f"expected exactly one winner: {results}")
        self.assertEqual(len(losers), 1, f"expected exactly one rebase: {results}")

        rejection = results[losers[0]]
        self.assertIsInstance(rejection, ensemble.Conflict)
        self.assertIn("moved on", str(rejection))
        state = rejection.state
        self.assertEqual(state["content"], self.session.part("bass"))
        self.assertGreater(state["voice_version"], 0)

    def test_the_loser_can_rebase_and_write(self) -> None:
        self.session.write_part("bass", "alice", BASS, 0)
        with self.assertRaises(ensemble.Conflict) as caught:
            self.session.write_part("bass", "bob", BASS_REVISED, 0)
        current = caught.exception.state
        accepted = self.session.write_part(
            "bass", "bob", BASS_REVISED, current["voice_version"], "rebased"
        )
        self.assertTrue(accepted["accepted"])
        self.assertIn("a1 e2 a2 e2", self.session.part("bass"))

    def test_a_write_to_another_voice_does_not_invalidate_yours(self) -> None:
        state = self.session.read(voice="bass", agent="alice")
        base = state["you"]["base_version"]
        self.session.write_part("violin1", "bob", VIOLIN, 0)
        self.assertTrue(self.session.write_part("bass", "alice", BASS, base)["accepted"])

    def test_the_manifest_survives_a_crowd(self) -> None:
        """Twenty concurrent claims on twenty voices leave twenty owners."""
        voices = [f"v{index}" for index in range(20)]
        # A bare Thread swallows whatever its target raises, which would make a
        # claim that failed look exactly like a claim that was lost. Record the
        # exceptions so a failure here names its own cause.
        failures: dict[str, BaseException] = {}

        def claim(voice: str) -> None:
            try:
                self.session.join(voice, f"agent-{voice}")
            except BaseException as exc:  # noqa: BLE001 - reported below
                failures[voice] = exc

        threads = [threading.Thread(target=claim, args=(voice,)) for voice in voices]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(
            failures, {}, f"claims raised: {[(v, repr(e)) for v, e in failures.items()]}"
        )
        manifest = self.session.manifest()
        missing = [voice for voice in voices if voice not in manifest.voices]
        self.assertEqual(missing, [], "voices lost from the manifest -- a write overwrote another")
        for voice in voices:
            self.assertEqual(manifest.voices[voice].owner, f"agent-{voice}")
        self.assertEqual(len(self.session.entries()), 21)


class TestMerge(SessionTest):
    def test_the_merged_score_carries_the_session_header(self) -> None:
        self.session.write_part("bass", "alice", BASS, 0)
        merged = self.session.score()
        self.assertIn("**TRACK: Harbour Lights**", merged)
        self.assertIn("key: Am | tempo: 96", merged)
        self.assertIn("[A] (Verse - 2 Bars)", merged)

    def test_the_merge_does_not_depend_on_the_order_of_arrival(self) -> None:
        other = ensemble.open_session(
            "mirror",
            root=self.root,
            title="Harbour Lights",
            key="Am",
            tempo=96,
            bars=2,
            sections=[{"name": "A", "description": "Verse - 2 Bars", "bars": 2}],
        )
        self.session.write_part("bass", "alice", BASS, 0)
        self.session.write_part("chords", "bob", CHORDS, 0)
        other.write_part("chords", "bob", CHORDS, 0)
        other.write_part("bass", "alice", BASS, 0)
        self.assertEqual(self.session.score(), other.score())

    def test_rows_come_out_in_lead_sheet_order(self) -> None:
        self.session.write_part("violin1", "carol", VIOLIN, 0)
        self.session.write_part("bass", "alice", BASS, 0)
        self.session.write_part("chords", "bob", CHORDS, 0)
        rows = [
            line
            for line in self.session.score().splitlines()
            if line.startswith(("Chords:", "Melody:", "Lyrics:", "@"))
        ]
        self.assertEqual(
            [row.split()[0] for row in rows], ["Chords:", "@bass", "@violin1"]
        )

    def test_the_merged_score_compiles(self) -> None:
        self.session.write_part("bass", "alice", BASS, 0)
        self.session.write_part("chords", "bob", CHORDS, 0)
        status = self.session.status()
        self.assertEqual(status["errors"], [])
        self.assertEqual(status["bars"], 2)

    def test_sections_a_part_introduces_are_recorded(self) -> None:
        self.session.write_part(
            "bass", "alice", "[A]\n@bass | a1 . e2 . |\n\n[B]\n@bass | f1 . c2 . |\n", 0
        )
        self.assertEqual(self.session.manifest().section_names(), ["A", "B"])
        self.assertIn("[B]", self.session.score())


class TestReading(SessionTest):
    def setUp(self) -> None:
        super().setUp()
        self.session.join("@bass", "alice")
        self.session.write_part("bass", "alice", BASS, 0, "walking line under the verse")
        self.session.write_part("chords", "bob", CHORDS, 0, "verse changes")

    def test_one_call_answers_what_a_joining_agent_needs(self) -> None:
        state = self.session.read(voice="@violin1", agent="carol")
        self.assertEqual(state["meta"]["key"], "Am")
        self.assertEqual(state["meta"]["tempo"], 96)
        self.assertEqual(state["meta"]["meter"], "4/4")
        self.assertEqual(state["window"]["total_bars"], 2)
        self.assertEqual(state["sections"][0]["name"], "A")

        voices = {voice["voice"]: voice for voice in state["voices"]}
        self.assertEqual(voices["@bass"]["owner"], "alice")
        self.assertTrue(voices["@bass"]["held"])
        self.assertFalse(voices["@violin1"]["held"])
        self.assertIn("@violin1", state["free_voices"])
        self.assertEqual(voices["@bass"]["summary"], "walking line under the verse")

    def test_the_window_says_what_the_others_are_playing(self) -> None:
        window = self.session.read(voice="violin1", bars="2")["window"]
        self.assertEqual((window["from"], window["to"]), (2, 2))
        self.assertEqual(len(window["bars"]), 1)
        bar = window["bars"][0]
        self.assertEqual(bar["section"], "A")
        self.assertEqual(bar["voices"]["@bass"], "f1 . c2 .")
        self.assertEqual(bar["voices"]["Chords:"], "F . . .")

    def test_your_own_part_comes_with_the_version_to_write_against(self) -> None:
        state = self.session.read(voice="bass", agent="alice")
        self.assertEqual(state["you"]["content"], BASS)
        self.assertTrue(state["you"]["yours"])
        self.assertEqual(
            state["you"]["base_version"], self.session.manifest().voices["bass"].version
        )

    def test_recent_changes_are_included(self) -> None:
        recent = self.session.read(history=3)["recent"]
        self.assertEqual(len(recent), 3)
        self.assertEqual(recent[-1]["summary"], "verse changes")

    def test_status_is_the_short_form(self) -> None:
        status = self.session.status()
        self.assertEqual(status["held"], ["@bass"])
        self.assertEqual(status["changes"], 4)
        self.assertEqual(status["bars"], 2)

    def test_rendering_writes_the_score_and_a_midi_file(self) -> None:
        result = self.session.render(config=load_config())
        self.assertTrue(result["ok"])
        self.assertTrue(Path(result["midi"]).is_file())
        self.assertTrue(Path(result["score"]).is_file())


class TestOverTheProtocol(unittest.TestCase):
    """The same session, driven the way an MCP client would drive it."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        config = load_config()
        self.server = Server(
            config=config,
            registry=ToolRegistry(sandbox=Sandbox(root=root / "work"), config=config),
            session_root=root / "sessions",
        )

    def call(self, name: str, **arguments) -> dict:
        answer = self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        return answer["result"]

    def payload(self, result: dict) -> dict:
        return json.loads(result["content"][0]["text"])

    def test_two_agents_co_author_a_piece(self) -> None:
        opened = self.payload(
            self.call(
                "ensemble_open",
                session="duet",
                title="Duet",
                key="Dm",
                tempo=108,
                bars=2,
                voices=["@bass", "@violin1"],
            )
        )
        self.assertEqual(opened["meta"]["key"], "Dm")

        first = self.payload(
            self.call("ensemble_join", session="duet", voice="@bass", agent="alice")
        )
        second = self.payload(
            self.call("ensemble_join", session="duet", voice="@violin1", agent="bob")
        )
        self.assertEqual(first["you"]["base_version"], 0)
        self.assertEqual(second["you"]["base_version"], 0)

        for voice, agent, content in (
            ("@bass", "alice", "[A]\n@bass | d1 . a1 . | g1 . d2 . |\n"),
            ("@violin1", "bob", "[A]\n@violin1 | d4 . f4 . | g4 . a4 . |\n"),
        ):
            result = self.call(
                "ensemble_write_part",
                session="duet",
                voice=voice,
                agent=agent,
                content=content,
                base_version=0,
                summary=f"{agent} wrote {voice}",
            )
            self.assertFalse(result["isError"], result["content"][0]["text"])

        status = self.payload(self.call("ensemble_status", session="duet"))
        self.assertEqual(status["errors"], [])
        self.assertEqual(sorted(status["held"]), ["@bass", "@violin1"])

        rendered = self.payload(self.call("ensemble_render", session="duet"))
        self.assertTrue(rendered["ok"])
        self.assertTrue(Path(rendered["midi"]).is_file())

    def test_a_stale_write_comes_back_as_a_readable_failure(self) -> None:
        self.call("ensemble_open", session="stale", bars=2, voices=["@bass"])
        self.call(
            "ensemble_write_part",
            session="stale",
            voice="@bass",
            agent="alice",
            content=BASS,
            base_version=0,
        )
        result = self.call(
            "ensemble_write_part",
            session="stale",
            voice="@bass",
            agent="alice",
            content=BASS_REVISED,
            base_version=0,
        )
        self.assertTrue(result["isError"])
        body = self.payload(result)
        self.assertIn("moved on", body["error"])
        self.assertEqual(body["rebase"]["content"], BASS)

    def test_writing_without_a_base_version_is_refused(self) -> None:
        self.call("ensemble_open", session="unversioned", bars=2)
        result = self.call(
            "ensemble_write_part",
            session="unversioned",
            voice="@bass",
            agent="alice",
            content=BASS,
        )
        self.assertTrue(result["isError"])
        self.assertIn("base_version", result["content"][0]["text"])

    def test_reading_without_a_session_lists_them(self) -> None:
        self.call("ensemble_open", session="one")
        self.call("ensemble_open", session="two")
        self.assertEqual(self.payload(self.call("ensemble_read"))["sessions"], ["one", "two"])

    def test_features_can_be_taken_from_a_session(self) -> None:
        self.call("ensemble_open", session="analysed", key="Am", tempo=96, bars=2)
        self.call(
            "ensemble_write_part",
            session="analysed",
            voice="@bass",
            agent="alice",
            content=BASS,
            base_version=0,
        )
        report = self.payload(self.call("analyze_features", session="analysed"))
        self.assertEqual(report["bars"], 2)
        self.assertEqual(len(report["per_bar"][0]["vector"]), 16)

    def test_an_unknown_session_is_a_readable_failure(self) -> None:
        result = self.call("ensemble_status", session="nothing-here")
        self.assertTrue(result["isError"])
        self.assertIn("no session called", result["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
