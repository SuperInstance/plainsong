"""The MCP server: the protocol itself, the tool surface, resources and features.

The protocol is tested by driving a real server with real JSON-RPC messages
through an in-process transport, because the thing that breaks is the wire
format rather than the Python behind it.
"""

from __future__ import annotations

import http.client
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from plainsong import features
from plainsong.agent.tools import Sandbox, ToolRegistry
from plainsong.mcp import protocol
from plainsong.mcp.protocol import Dispatcher
from plainsong.mcp.resources import NotFound, Resources
from plainsong.mcp.server import PROTOCOL_VERSION, Server, build_http_handler
from plainsong.runtime.config import load_config

NOTATION = """**TRACK: Protocol Sample**
[MetaData]
key: Am | tempo: 96 | swing: 0% | subdivision: 8th
time: 4/4

[A] (Verse - 2 Bars)
Chords: | Am . . . | F . . . |
Melody: | A4 . C5 E5 | F4 . A4 C5 |
@bass | a1 . e2 . | f1 . c2 . |
"""


def message(method: str, params: dict | None = None, identifier: int | None = 1) -> str:
    """One JSON-RPC message as a client would send it."""
    payload: dict = {"jsonrpc": "2.0", "method": method}
    if identifier is not None:
        payload["id"] = identifier
    if params is not None:
        payload["params"] = params
    return json.dumps(payload)


class Client:
    """An in-process client: writes lines in, reads lines back."""

    def __init__(self, server: Server) -> None:
        self.server = server
        self.next_id = 0

    def send(self, method: str, params: dict | None = None) -> dict | None:
        self.next_id += 1
        answer = self.server.handle_text(message(method, params, self.next_id))
        return None if answer is None else json.loads(answer)

    def notify(self, method: str, params: dict | None = None) -> str | None:
        return self.server.handle_text(message(method, params, None))

    def result(self, method: str, params: dict | None = None) -> dict:
        answer = self.send(method, params)
        assert answer is not None, f"{method} was not answered"
        assert "error" not in answer, answer["error"]
        return answer["result"]

    def call(self, name: str, **arguments) -> dict:
        return self.result("tools/call", {"name": name, "arguments": arguments})


def build_server(directory: Path) -> Server:
    config = load_config()
    registry = ToolRegistry(sandbox=Sandbox(root=directory / "work"), config=config)
    return Server(config=config, registry=registry, session_root=directory / "sessions")


class TestHandshake(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.server = build_server(Path(self.temporary.name))
        self.client = Client(self.server)

    def test_initialize_advertises_tools_resources_and_prompts(self) -> None:
        result = self.client.result(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "t"}},
        )
        self.assertEqual(result["protocolVersion"], PROTOCOL_VERSION)
        self.assertIn("tools", result["capabilities"])
        self.assertIn("resources", result["capabilities"])
        self.assertIn("prompts", result["capabilities"])
        self.assertEqual(result["serverInfo"]["name"], "plainsong")
        self.assertTrue(result["instructions"].strip())

    def test_an_older_protocol_version_is_answered_in_kind(self) -> None:
        result = self.client.result("initialize", {"protocolVersion": "2024-11-05"})
        self.assertEqual(result["protocolVersion"], "2024-11-05")

    def test_an_unknown_protocol_version_gets_ours(self) -> None:
        result = self.client.result("initialize", {"protocolVersion": "1999-01-01"})
        self.assertEqual(result["protocolVersion"], PROTOCOL_VERSION)

    def test_initialized_notification_is_not_answered(self) -> None:
        self.assertIsNone(self.client.notify("notifications/initialized"))
        self.assertTrue(self.server.initialized)

    def test_ping(self) -> None:
        self.assertEqual(self.client.result("ping"), {})

    def test_full_handshake_then_a_tool_call(self) -> None:
        self.client.result("initialize", {"protocolVersion": PROTOCOL_VERSION})
        self.client.notify("notifications/initialized")
        listed = self.client.result("tools/list")["tools"]
        names = {tool["name"] for tool in listed}
        self.assertIn("compile_score", names)
        self.assertIn("ensemble_write_part", names)
        result = self.client.call("compile_score", content=NOTATION)
        self.assertFalse(result["isError"])
        self.assertIn("Protocol Sample", result["content"][0]["text"])


class TestToolSurface(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.server = build_server(Path(self.temporary.name))
        self.client = Client(self.server)

    def test_the_tool_list_is_the_registry(self) -> None:
        """Nothing keeps a second list: a tool added elsewhere shows up here."""
        self.server.registry.add("invented_tool", "Only for this test.", {"type": "object"}, str)
        names = {tool["name"] for tool in self.client.result("tools/list")["tools"]}
        self.assertIn("invented_tool", names)
        self.assertEqual(names, {spec.name for spec in self.server.registry.specs()})

    def test_every_tool_describes_its_input(self) -> None:
        for tool in self.client.result("tools/list")["tools"]:
            with self.subTest(tool=tool["name"]):
                self.assertTrue(tool["description"].strip())
                self.assertEqual(tool["inputSchema"]["type"], "object")

    def test_a_tool_that_fails_returns_a_result_not_an_error(self) -> None:
        answer = self.client.send("tools/call", {"name": "read_file", "arguments": {"path": "no"}})
        self.assertNotIn("error", answer)
        self.assertTrue(answer["result"]["isError"])
        self.assertIn("not a file", answer["result"]["content"][0]["text"])

    def test_a_tool_that_raises_is_reported_as_a_tool_error(self) -> None:
        def explode() -> str:
            raise RuntimeError("the piano fell over")

        self.server.registry.add("explode", "Raises.", {"type": "object"}, explode)
        answer = self.client.send("tools/call", {"name": "explode", "arguments": {}})
        self.assertNotIn("error", answer)
        self.assertTrue(answer["result"]["isError"])
        self.assertIn("the piano fell over", answer["result"]["content"][0]["text"])

    def test_an_unknown_tool_is_a_protocol_error(self) -> None:
        answer = self.client.send("tools/call", {"name": "nonesuch", "arguments": {}})
        self.assertEqual(answer["error"]["code"], protocol.INVALID_PARAMS)

    def test_structured_results_come_back_as_data_too(self) -> None:
        result = self.client.call("analyze_features", content=NOTATION)
        self.assertIn("structuredContent", result)
        self.assertEqual(result["structuredContent"]["bars"], 2)


class TestProtocolErrors(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.server = build_server(Path(self.temporary.name))

    def error_code(self, text: str) -> int:
        answer = self.server.handle_text(text)
        self.assertIsNotNone(answer, f"{text!r} was not answered")
        return json.loads(answer)["error"]["code"]

    def test_malformed_json(self) -> None:
        self.assertEqual(self.error_code("{oh dear"), protocol.PARSE_ERROR)

    def test_wrong_version(self) -> None:
        self.assertEqual(
            self.error_code('{"jsonrpc": "1.0", "id": 1, "method": "ping"}'),
            protocol.INVALID_REQUEST,
        )

    def test_missing_method(self) -> None:
        self.assertEqual(
            self.error_code('{"jsonrpc": "2.0", "id": 1}'), protocol.INVALID_REQUEST
        )

    def test_unknown_method(self) -> None:
        self.assertEqual(self.error_code(message("no/such")), protocol.METHOD_NOT_FOUND)

    def test_bad_params(self) -> None:
        self.assertEqual(
            self.error_code(message("tools/call", {})), protocol.INVALID_PARAMS
        )
        self.assertEqual(
            self.error_code(message("resources/read", {})), protocol.INVALID_PARAMS
        )
        self.assertEqual(
            self.error_code('{"jsonrpc": "2.0", "id": 1, "method": "ping", "params": 4}'),
            protocol.INVALID_PARAMS,
        )

    def test_notifications_are_never_answered(self) -> None:
        for text in (
            message("ping", None, None),
            message("no/such", None, None),
            '{"jsonrpc": "2.0", "method": "tools/call", "params": {}}',
        ):
            with self.subTest(text=text):
                self.assertIsNone(self.server.handle_text(text))

    def test_an_unknown_method_does_not_stop_the_loop(self) -> None:
        self.server.handle_text(message("no/such"))
        self.assertEqual(json.loads(self.server.handle_text(message("ping")))["result"], {})

    def test_a_handler_that_raises_becomes_an_internal_error(self) -> None:
        dispatcher = Dispatcher()

        def explode(params: dict) -> None:
            raise ValueError("no")

        dispatcher.register("explode", explode)
        answer = json.loads(dispatcher.handle_text(message("explode")))
        self.assertEqual(answer["error"]["code"], protocol.INTERNAL_ERROR)

    def test_batches_are_answered_as_a_batch(self) -> None:
        batch = json.dumps(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                {"jsonrpc": "2.0", "method": "ping"},
                {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            ]
        )
        answers = json.loads(self.server.handle_text(batch))
        self.assertEqual([answer["id"] for answer in answers], [1, 2])


class TestStdioTransport(unittest.TestCase):
    def test_a_session_over_a_pipe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            server = build_server(Path(directory))
            reader = io.StringIO(
                "\n".join(
                    [
                        message("initialize", {"protocolVersion": PROTOCOL_VERSION}, 1),
                        message("notifications/initialized", None, None),
                        "",
                        message("tools/list", None, 2),
                    ]
                )
                + "\n"
            )
            writer = io.StringIO()
            protocol.serve_stdio(server.dispatcher, reader, writer)
            lines = writer.getvalue().strip().splitlines()
            self.assertEqual(len(lines), 2, "the notification and the blank line were answered")
            self.assertEqual([json.loads(line)["id"] for line in lines], [1, 2])

    def test_a_client_that_closes_the_pipe_is_a_clean_stop(self) -> None:
        """A disconnect is how a session ends, not a crash.

        The host exits, the user closes the window, or something downstream has
        read all it wanted. The server must return 0 and say nothing rather than
        raising BrokenPipeError out of the serve loop -- there is nobody left to
        report it to, and a traceback makes a normal disconnect look like a
        failure to whatever launched the server. Found by plainsong-mcp's CI:
        `| grep -q` under `pipefail` closes the pipe on its first match.
        """

        class ClosedPipe(io.StringIO):
            def write(self, text: str) -> int:
                raise BrokenPipeError(32, "Broken pipe")

        with tempfile.TemporaryDirectory() as directory:
            server = build_server(Path(directory))
            reader = io.StringIO(
                message("initialize", {"protocolVersion": PROTOCOL_VERSION}, 1) + "\n"
            )
            self.assertEqual(protocol.serve_stdio(server.dispatcher, reader, ClosedPipe()), 0)


class TestDeprecationNoticeStaysOffTheWire(unittest.TestCase):
    """`plainsong mcp` is deprecated, and saying so must not break it.

    stdout *is* the protocol in stdio mode. A deprecation line printed there
    would desynchronise every client -- turning a courtesy into an outage --
    which is why the notice goes to stderr and why this test exists rather
    than a reading of the code.
    """

    def _run(self, args: list[str], env_extra: dict | None = None) -> subprocess.CompletedProcess:
        import os

        env = dict(os.environ)
        env.pop("PLAINSONG_NO_DEPRECATION", None)
        env.update(env_extra or {})
        root = Path(__file__).resolve().parent.parent
        return subprocess.run(
            [sys.executable, "-m", "plainsong", *args],
            input='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n',
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(root),
            env=env,
        )

    def test_stdout_carries_only_json_rpc(self) -> None:
        finished = self._run(["mcp"])
        for line in finished.stdout.splitlines():
            if not line.strip():
                continue
            # Fails loudly with the offending line rather than a bare False.
            try:
                json.loads(line)
            except ValueError:  # pragma: no cover - the failure path is the point
                self.fail(f"non-protocol line on stdout: {line!r}")

    def test_the_notice_is_on_stderr_and_names_the_replacement(self) -> None:
        finished = self._run(["mcp"])
        self.assertIn("deprecated", finished.stderr)
        self.assertIn("plainsong-mcp", finished.stderr)

    def test_it_can_be_silenced(self) -> None:
        finished = self._run(["mcp"], {"PLAINSONG_NO_DEPRECATION": "1"})
        self.assertNotIn("deprecated", finished.stderr)


class TestHttpTransport(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        server = build_server(Path(self.temporary.name))
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), build_http_handler(server))
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.url = f"http://127.0.0.1:{self.http.server_port}/"

    def post(self, body: str, headers: dict | None = None) -> tuple[int, str]:
        request = urllib.request.Request(
            self.url,
            data=body.encode("utf-8"),
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8")

    def test_the_same_messages_go_over_http(self) -> None:
        status, body = self.post(message("initialize", {"protocolVersion": PROTOCOL_VERSION}))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["result"]["protocolVersion"], PROTOCOL_VERSION)

    def test_a_notification_gets_no_body(self) -> None:
        status, body = self.post(message("notifications/initialized", None, None))
        self.assertEqual(status, 202)
        self.assertEqual(body, "")

    def test_cross_origin_is_refused(self) -> None:
        status, _ = self.post(message("ping"), {"Origin": "http://elsewhere.example"})
        self.assertEqual(status, 403)

    def test_a_rebound_hostname_is_refused_even_though_origin_matches_host(self) -> None:
        """DNS rebinding defeats an Origin-against-Host check on its own.

        An attacker points `evil.example` at 127.0.0.1. A page served from that
        domain then sends Origin and Host both reading `evil.example` -- they
        match perfectly, and a check that only compares the two waves it
        through to a tool that writes files. Requiring Host to name this
        machine breaks it, because a rebound request always carries the
        attacker's hostname.

        This guard existed here and not in `SuperInstance/plainsong-mcp`, the
        copy people `pip install`, and sat that way for months because nothing
        in either repository could notice. It is pinned on both sides now.
        """
        body = message("ping").encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=10)
        self.addCleanup(connection.close)
        connection.putrequest("POST", "/", skip_host=True, skip_accept_encoding=True)
        connection.putheader("Host", "evil.example")
        connection.putheader("Origin", "http://evil.example")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(len(body)))
        connection.endheaders()
        connection.send(body)

        self.assertEqual(connection.getresponse().status, 403)

    def test_a_rebound_hostname_is_refused_with_no_origin_at_all(self) -> None:
        """Origin is optional, and a non-browser client simply omits it.

        So the Host check cannot live inside the branch that compares them:
        with no Origin to disagree with, an Origin-only guard has nothing to
        say and lets the request through. `_host_is_local` runs first, before
        Origin is ever read, and this is the test that holds it there.
        """
        body = message("ping").encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=10)
        self.addCleanup(connection.close)
        connection.putrequest("POST", "/", skip_host=True, skip_accept_encoding=True)
        connection.putheader("Host", "evil.example")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(len(body)))
        connection.endheaders()
        connection.send(body)

        self.assertEqual(connection.getresponse().status, 403)

    def test_the_loopback_names_this_machine_answers(self) -> None:
        """The guard has to admit the names a local client actually sends.

        Refusing everything would pass both tests above and break the server,
        so this is the other half: `localhost`, `127.0.0.1` and a port suffix
        are all this machine.
        """
        for host in ("localhost", "127.0.0.1", "127.0.0.1:1", "[::1]"):
            with self.subTest(host=host):
                body = message("ping").encode("utf-8")
                connection = http.client.HTTPConnection(
                    "127.0.0.1", self.http.server_port, timeout=10
                )
                self.addCleanup(connection.close)
                connection.putrequest("POST", "/", skip_host=True, skip_accept_encoding=True)
                connection.putheader("Host", host)
                connection.putheader("Content-Type", "application/json")
                connection.putheader("Content-Length", str(len(body)))
                connection.endheaders()
                connection.send(body)

                self.assertEqual(connection.getresponse().status, 200)

    def test_get_reports_what_is_served(self) -> None:
        with urllib.request.urlopen(self.url, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["server"], "plainsong")
        self.assertIn("tools/call", body["methods"])


class TestResources(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.server = build_server(Path(self.temporary.name))
        self.client = Client(self.server)

    def test_the_fixed_resources_are_listed_and_readable(self) -> None:
        listed = {entry["uri"] for entry in self.client.result("resources/list")["resources"]}
        self.assertIn("plainsong://notation-reference", listed)
        self.assertIn("plainsong://capabilities", listed)
        reference = self.client.result(
            "resources/read", {"uri": "plainsong://notation-reference"}
        )["contents"][0]
        self.assertIn("Plainsong notation reference", reference["text"])
        self.assertIn("markdown", reference["mimeType"])

    def test_specs_are_listed_and_readable(self) -> None:
        listed = [
            entry["uri"]
            for entry in self.client.result("resources/list")["resources"]
            if entry["uri"].startswith("plainsong://spec/")
        ]
        self.assertTrue(listed, "no specs were offered as resources")
        body = json.loads(
            self.client.result("resources/read", {"uri": listed[0]})["contents"][0]["text"]
        )
        self.assertTrue(body["checks"])

    def test_the_parameterised_sets_are_templates(self) -> None:
        templates = {
            entry["uriTemplate"]
            for entry in self.client.result("resources/templates/list")["resourceTemplates"]
        }
        self.assertEqual(
            templates,
            {
                "plainsong://library/{name}",
                "plainsong://session/{name}",
                "plainsong://spec/{id}",
            },
        )

    def test_an_unknown_uri_is_an_error(self) -> None:
        answer = self.client.send("resources/read", {"uri": "plainsong://nowhere/1"})
        self.assertIn("error", answer)
        answer = self.client.send("resources/read", {"uri": "https://example.com"})
        self.assertIn("error", answer)

    def test_a_session_is_readable_as_a_resource(self) -> None:
        self.client.call("ensemble_open", session="reading", key="Am", tempo=96, bars=2)
        body = json.loads(
            self.client.result("resources/read", {"uri": "plainsong://session/reading"})[
                "contents"
            ][0]["text"]
        )
        self.assertEqual(body["meta"]["key"], "Am")
        self.assertIn("score", body)

    def test_reading_directly_raises_not_found(self) -> None:
        resources = Resources(load_config())
        with self.assertRaises(NotFound):
            resources.read("plainsong://library/definitely-not-here-1234")


class TestPrompts(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.client = Client(build_server(Path(self.temporary.name)))

    def test_the_agent_prompts_are_offered(self) -> None:
        names = {prompt["name"] for prompt in self.client.result("prompts/list")["prompts"]}
        self.assertEqual(names, {"composer", "builder"})

    def test_a_prompt_comes_back_as_a_message(self) -> None:
        got = self.client.result("prompts/get", {"name": "composer"})
        content = got["messages"][0]["content"]
        self.assertEqual(got["messages"][0]["role"], "user")
        self.assertEqual(content["type"], "text")
        self.assertIn("composition agent", content["text"])

    def test_an_argument_is_appended(self) -> None:
        got = self.client.result(
            "prompts/get", {"name": "composer", "arguments": {"task": "a waltz in D minor"}}
        )
        self.assertIn("a waltz in D minor", got["messages"][0]["content"]["text"])

    def test_an_unknown_prompt_is_an_error(self) -> None:
        answer = self.client.send("prompts/get", {"name": "nobody"})
        self.assertEqual(answer["error"]["code"], protocol.INVALID_PARAMS)


class TestFeatures(unittest.TestCase):
    def setUp(self) -> None:
        from plainsong.notation import arrange, parse

        self.arrangement = arrange(parse(NOTATION))

    def test_sixteen_features_per_bar_in_the_documented_order(self) -> None:
        bars = features.extract(self.arrangement)
        self.assertEqual(len(bars), 2)
        self.assertEqual(len(features.FEATURE_NAMES), 16)
        for bar in bars:
            self.assertEqual(len(bar.vector), 16)
            self.assertEqual(list(bar.values), list(features.FEATURE_NAMES))

    def test_every_value_is_normalised(self) -> None:
        for bar in features.extract(self.arrangement):
            for name, value in bar.values.items():
                low = -1.0 if name == "contour_direction" else 0.0
                self.assertGreaterEqual(value, low, name)
                self.assertLessEqual(value, 1.0, name)

    def test_the_same_arrangement_gives_the_same_numbers(self) -> None:
        first = [bar.vector for bar in features.extract(self.arrangement)]
        second = [bar.vector for bar in features.extract(self.arrangement)]
        self.assertEqual(first, second)

    def test_a_silent_bar_is_all_rest(self) -> None:
        from plainsong.notation import arrange, parse

        silent_middle = "[A]\nMelody: | C4 D4 E4 F4 |\n\n[B]\nLyrics: | one two |\n\n[C]\nMelody: | G4 A4 B4 C5 |\n"
        bars = features.extract(arrange(parse(silent_middle)))
        self.assertEqual(len(bars), 3)
        self.assertEqual(bars[1].values["rest_ratio"], 1.0)
        self.assertEqual(bars[1].values["note_density"], 0.0)
        self.assertEqual(bars[1].onsets, 0)

    def test_density_rises_with_the_notes(self) -> None:
        from plainsong.notation import arrange, parse

        sparse = features.extract(arrange(parse("[A]\nMelody: | C4 . . . |\n")))[0]
        dense = features.extract(
            arrange(parse("[A]\nMelody: | C4 D4 E4 F4 G4 A4 B4 C5 |\n"))
        )[0]
        self.assertLess(sparse.values["note_density"], dense.values["note_density"])

    def test_register_is_read_from_the_pitches(self) -> None:
        from plainsong.notation import arrange, parse

        low = features.extract(arrange(parse("[A]\n@bass | c1 . e1 . |\n")))[0]
        high = features.extract(arrange(parse("[A]\nMelody: | C7 . E7 . |\n")))[0]
        self.assertEqual(low.values["bass_register"], 1.0)
        self.assertEqual(high.values["treble_activity"], 1.0)
        self.assertGreater(high.values["avg_pitch"], low.values["avg_pitch"])

    def test_one_voice_can_be_analysed_alone(self) -> None:
        whole = features.extract(self.arrangement)[0]
        bass = features.extract(self.arrangement, voice="bass")[0]
        self.assertLess(bass.values["note_density"], whole.values["note_density"])
        self.assertEqual(bass.values["bass_register"], 1.0)

    def test_a_summary_averages_the_bars(self) -> None:
        bars = features.extract(self.arrangement)
        mean = features.summarise(bars)
        self.assertEqual(set(mean), set(features.FEATURE_NAMES))
        expected = (bars[0].values["avg_pitch"] + bars[1].values["avg_pitch"]) / 2
        self.assertAlmostEqual(mean["avg_pitch"], expected, places=5)

    def test_the_table_has_a_row_per_bar(self) -> None:
        table = features.format_table(features.extract(self.arrangement))
        self.assertEqual(len(table.splitlines()), 3)


class TestConductorBridge(unittest.TestCase):
    """The bridge is soft: an install without perform/ must still serve."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.client = Client(build_server(Path(self.temporary.name)))

    def test_directives_are_applied_or_declined_cleanly(self) -> None:
        result = self.client.call(
            "apply_directives",
            content=NOTATION,
            directives={"directives": [{"action": "lay_back", "intensity": 0.5}]},
            features=False,
        )
        text = result["content"][0]["text"]
        if result["isError"]:
            self.assertIn("no conductor", text)
            return
        report = json.loads(text)
        self.assertIn("before", report)
        self.assertIn("after", report)
        self.assertEqual(report["after"]["notes"], report["before"]["notes"])

    def test_features_can_come_back_with_the_result(self) -> None:
        result = self.client.call(
            "apply_directives",
            content=NOTATION,
            directives={"directives": [{"action": "lay_back", "intensity": 0.5}]},
        )
        if result["isError"]:
            self.skipTest("this install has no conductor")
        report = json.loads(result["content"][0]["text"])
        self.assertEqual(len(report["after_features"]), 2)
        self.assertEqual(report["feature_names"], list(features.FEATURE_NAMES))


class TestSelfChecks(unittest.TestCase):
    def test_every_check_passes(self) -> None:
        from plainsong.mcp import selfcheck

        for name in sorted(dir(selfcheck)):
            if not name.startswith("check_"):
                continue
            with self.subTest(check=name):
                ok, detail = getattr(selfcheck, name)()
                self.assertTrue(ok, f"{name}: {detail}")


if __name__ == "__main__":
    unittest.main()
