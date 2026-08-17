"""The agent loop, its tools and the sandbox around them."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from plainsong.agent.kernel import Agent, load_prompt
from plainsong.agent.tools import Sandbox, SandboxError, ToolRegistry
from plainsong.llm import build_provider
from plainsong.llm.base import Provider
from plainsong.llm.catalog import ProviderInfo
from plainsong.llm.types import CompletionRequest, CompletionResponse, ToolCall
from plainsong.runtime.config import load_config

NOTATION = """[A]
Chords: | Am . . . | F . . . |
Melody: | A4 . C5 E5 | F4 . A4 C5 |
"""


class ScriptedProvider(Provider):
    """A provider that replays a fixed list of responses."""

    def __init__(self, responses: list[CompletionResponse]) -> None:
        super().__init__(ProviderInfo(id="scripted", label="Scripted", api="echo"), model="scripted")
        self.responses = list(responses)
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.requests.append(request)
        if not self.responses:
            return CompletionResponse(text="(out of script)", provider="scripted")
        return self.responses.pop(0)


class TestSandbox(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.sandbox = Sandbox(root=Path(self.directory.name) / "work")

    def tearDown(self):
        self.directory.cleanup()

    def test_relative_paths_resolve_inside(self):
        target = self.sandbox.resolve("songs/a.song", for_write=True)
        self.assertTrue(str(target).startswith(str(self.sandbox.root)))

    def test_escape_is_refused(self):
        for path in ("../outside.txt", "/etc/passwd", "songs/../../oops"):
            with self.assertRaises(SandboxError):
                self.sandbox.resolve(path, for_write=True)

    def test_extra_readable_paths_are_read_only(self):
        readable = Path(self.directory.name) / "reference"
        readable.mkdir()
        sandbox = Sandbox(root=self.sandbox.root, extra_readable=[readable])
        sandbox.resolve(str(readable / "notes.md"))
        with self.assertRaises(SandboxError):
            sandbox.resolve(str(readable / "notes.md"), for_write=True)


class TestTools(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.registry = ToolRegistry(
            sandbox=Sandbox(root=Path(self.directory.name)), config=load_config()
        )

    def tearDown(self):
        self.directory.cleanup()

    def test_specs_are_well_formed(self):
        for spec in self.registry.specs():
            self.assertTrue(spec.name)
            self.assertTrue(spec.description)
            self.assertEqual(spec.parameters["type"], "object")
            for required in spec.parameters.get("required", []):
                self.assertIn(required, spec.parameters["properties"])

    def test_unknown_tool_is_reported_not_raised(self):
        result = self.registry.call("no_such_tool", {})
        self.assertIn("no tool named", result)
        self.assertIn("Available tools", result)

    def test_wrong_arguments_are_reported(self):
        self.assertIn("error", self.registry.call("read_file", {"wrong": "x"}))

    def test_write_and_read(self):
        self.registry.call("write_file", {"path": "notes.md", "content": "hello"})
        self.assertEqual(self.registry.call("read_file", {"path": "notes.md"}), "hello")

    def test_write_score_validates_first(self):
        result = self.registry.call("write_score", {"path": "bad.song", "content": "not notation"})
        self.assertIn("not written", result)
        self.assertFalse((Path(self.directory.name) / "bad.song").exists())

    def test_write_score_accepts_valid_notation(self):
        result = self.registry.call("write_score", {"path": "good.song", "content": NOTATION})
        self.assertIn("wrote", result)
        self.assertTrue((Path(self.directory.name) / "good.song").exists())

    def test_write_score_adds_the_extension(self):
        self.registry.call("write_score", {"path": "noext", "content": NOTATION})
        self.assertTrue((Path(self.directory.name) / "noext.song").exists())

    def test_compile_reports_the_arrangement(self):
        self.registry.call("write_score", {"path": "song.song", "content": NOTATION})
        result = self.registry.call("compile_score", {"path": "song.song"})
        self.assertIn("notes", result)
        self.assertTrue((Path(self.directory.name) / "output" / "song.mid").exists())

    def test_sandbox_escape_is_reported_as_an_error(self):
        result = self.registry.call("write_file", {"path": "../escape.txt", "content": "x"})
        self.assertIn("outside the working directory", result)

    def test_notation_reference_is_shipped(self):
        reference = self.registry.call("notation_reference", {})
        self.assertIn("Chords:", reference)
        self.assertIn("@name", reference)

    def test_probe_host_lists_capabilities(self):
        self.assertIn("python", self.registry.call("probe_host", {}))

    def test_record_decision_writes_a_journal(self):
        self.registry.call("record_decision", {"note": "chose the builtin synth"})
        journal = Path(self.directory.name) / "BUILD-JOURNAL.md"
        self.assertIn("chose the builtin synth", journal.read_text())

    def test_results_are_truncated(self):
        self.registry.call("write_file", {"path": "big.txt", "content": "x" * 50_000})
        self.assertIn("truncated", self.registry.call("read_file", {"path": "big.txt"}))


class TestAgentLoop(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.config = load_config()
        self.registry = ToolRegistry(
            sandbox=Sandbox(root=Path(self.directory.name)), config=self.config
        )

    def tearDown(self):
        self.directory.cleanup()

    def _agent(self, provider) -> Agent:
        return Agent(provider=provider, tools=self.registry, config=self.config)

    def test_plain_reply_ends_the_loop(self):
        provider = ScriptedProvider([CompletionResponse(text="done")])
        result = self._agent(provider).run("hello")
        self.assertEqual(result.reply, "done")
        self.assertEqual(result.steps, 1)
        self.assertTrue(result.ok)

    def test_tool_call_then_reply(self):
        provider = ScriptedProvider(
            [
                CompletionResponse(
                    tool_calls=[
                        ToolCall(id="1", name="write_score", arguments={"path": "x.song", "content": NOTATION})
                    ]
                ),
                CompletionResponse(text="wrote it"),
            ]
        )
        result = self._agent(provider).run("write something")
        self.assertEqual(result.reply, "wrote it")
        self.assertEqual(result.tool_calls, ["write_score"])
        self.assertEqual(result.steps, 2)
        self.assertTrue((Path(self.directory.name) / "x.song").exists())

    def test_tool_results_are_fed_back(self):
        provider = ScriptedProvider(
            [
                CompletionResponse(tool_calls=[ToolCall(id="1", name="probe_host", arguments={})]),
                CompletionResponse(text="ok"),
            ]
        )
        self._agent(provider).run("look around")
        second = provider.requests[1]
        self.assertEqual(second.messages[-1].role, "tool")
        self.assertIn("python", second.messages[-1].content)

    def test_step_budget_is_enforced(self):
        provider = ScriptedProvider(
            [
                CompletionResponse(tool_calls=[ToolCall(id=str(i), name="probe_host", arguments={})])
                for i in range(10)
            ]
        )
        agent = Agent(provider=provider, tools=self.registry, config=self.config, max_steps=3)
        result = agent.run("loop forever")
        self.assertEqual(result.steps, 3)
        self.assertIn("step limit", result.stopped_because)

    def test_provider_failure_is_returned_not_raised(self):
        class Failing(ScriptedProvider):
            def complete(self, request):
                from plainsong.llm.types import ProviderError

                raise ProviderError("no key", provider="failing")

        result = self._agent(Failing([])).run("hello")
        self.assertFalse(result.ok)
        self.assertIn("no key", result.error)

    def test_events_are_emitted(self):
        events = []
        provider = ScriptedProvider(
            [
                CompletionResponse(tool_calls=[ToolCall(id="1", name="probe_host", arguments={})]),
                CompletionResponse(text="done"),
            ]
        )
        agent = Agent(
            provider=provider, tools=self.registry, config=self.config, on_event=events.append
        )
        agent.run("hello")
        kinds = [event.kind for event in events]
        self.assertIn("tool_call", kinds)
        self.assertIn("tool_result", kinds)
        self.assertIn("done", kinds)

    def test_system_prompt_and_context_are_sent_once(self):
        provider = ScriptedProvider([CompletionResponse(text="a"), CompletionResponse(text="b")])
        agent = self._agent(provider)
        agent.run("first")
        agent.run("second")
        system_messages = [m for m in provider.requests[1].messages if m.role == "system"]
        self.assertEqual(len(system_messages), 1)
        self.assertIn("working directory", system_messages[0].content)

    def test_transcript_round_trips(self):
        provider = ScriptedProvider([CompletionResponse(text="saved")])
        agent = self._agent(provider)
        agent.run("hello")
        path = agent.save(Path(self.directory.name) / "session.json")
        data = json.loads(path.read_text())
        self.assertEqual(data["provider"], "scripted")

        restored = self._agent(ScriptedProvider([]))
        restored.load(path)
        self.assertEqual(len(restored.messages), len(agent.messages))

    def test_end_to_end_with_the_offline_provider(self):
        agent = Agent(provider=build_provider("echo"), tools=self.registry, config=self.config)
        result = agent.run("write me something quiet")
        self.assertTrue(result.ok)
        self.assertIn("write_score", result.tool_calls)
        written = list(Path(self.directory.name).glob("*.song"))
        self.assertEqual(len(written), 1)


class TestPrompts(unittest.TestCase):
    def test_roles_have_prompts(self):
        for role in ("composer", "builder"):
            self.assertGreater(len(load_prompt(role)), 200, role)

    def test_missing_prompt_is_empty_not_an_error(self):
        self.assertEqual(load_prompt("nonexistent"), "")


class TestDangerousToolGate(unittest.TestCase):
    """`allow_dangerous` gates tools marked `dangerous`. Today nothing is marked.

    That is a trap rather than a bug: the flag is offered on the MCP server as
    `--allow-dangerous` ("offer tools that need approval"), so the next person to
    add a destructive tool will reasonably assume it is guarded. These two tests
    make the mechanism proven and the policy deliberate -- adding a dangerous
    tool has to be a conscious, reviewed change rather than a silent one.
    """

    def _registry(self, allow: bool):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return ToolRegistry(
            sandbox=Sandbox(root=Path(directory.name)),
            config=load_config(),
            allow_dangerous=allow,
        )

    def test_a_dangerous_tool_is_refused_unless_it_is_allowed(self):
        """The gate actually gates. Registered here rather than shipped."""
        for allowed in (False, True):
            with self.subTest(allow_dangerous=allowed):
                registry = self._registry(allowed)
                registry.add(
                    "detonate", "test-only", {"type": "object", "properties": {}},
                    lambda: "boom", dangerous=True,
                )
                text, failed = registry.call_result("detonate", {})
                if allowed:
                    self.assertEqual(text, "boom")
                    self.assertFalse(failed)
                else:
                    self.assertTrue(failed)
                    self.assertIn("needs approval", text)
                    self.assertNotIn("boom", text)

    def test_a_dangerous_tool_is_not_even_listed_without_the_flag(self):
        """A model must not be told about a tool it will then be refused."""
        registry = self._registry(False)
        registry.add(
            "detonate", "test-only", {"type": "object", "properties": {}},
            lambda: "boom", dangerous=True,
        )
        self.assertNotIn("detonate", [spec.name for spec in registry.specs()])

    def test_no_shipped_tool_is_marked_dangerous(self):
        """Pins the current policy so that changing it is a decision, not a drift.

        If you are here because this failed, you added a tool that needs
        approval. That is fine -- confirm the gate is what you wanted, then name
        it below.
        """
        registry = self._registry(False)
        marked = sorted(name for name, tool in registry.tools.items() if tool.dangerous)
        self.assertEqual(marked, [], "a shipped tool is now gated; see this test's docstring")


if __name__ == "__main__":
    unittest.main()
