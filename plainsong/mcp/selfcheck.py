"""Checks that ``specs/mcp.toml`` points at.

Each function returns ``(ok, detail)``, runs without network access, without
optional dependencies, and writes only inside a temporary directory. They are
the executable half of the spec: a user runs them to find out whether this
install can serve MCP, and the build agent runs them after a change.

They live here rather than in ``plainsong/selfcheck.py`` so that deleting
``mcp/`` takes its checks with it.
"""

from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path
from typing import Any

SAMPLE = """**TRACK: MCP Sample**
[MetaData]
key: Am | tempo: 96 | swing: 0% | subdivision: 8th
time: 4/4

[A] (Verse - 2 Bars)
Chords: | Am . . . | F . . . |
Melody: | A4 . C5 E5 | F4 . A4 C5 |
@bass | a1 . e2 . | f1 . c2 . |
"""

BASS = "[A]\n@bass | a1 . e2 . | f1 . c2 . |\n"
VIOLIN = "[A]\n@violin1 | e4 . a4 . | c5 . f4 . |\n"


def _server(directory: Path) -> Any:
    """A server whose tools can only reach *directory*."""
    from ..agent.tools import Sandbox, ToolRegistry
    from ..runtime.config import load_config
    from .server import Server

    config = load_config()
    registry = ToolRegistry(sandbox=Sandbox(root=directory / "work"), config=config)
    return Server(config=config, registry=registry, session_root=directory / "sessions")


def _call(server: Any, method: str, params: dict[str, Any] | None = None, identifier: int = 1) -> Any:
    message = {"jsonrpc": "2.0", "id": identifier, "method": method, "params": params or {}}
    return server.handle(message)


def check_handshake() -> tuple[bool, str]:
    """A client can initialize, list tools and call one."""
    with tempfile.TemporaryDirectory() as directory:
        server = _server(Path(directory))
        initialized = _call(server, "initialize", {"protocolVersion": "2025-06-18"})
        result = initialized.get("result", {})
        if not result.get("protocolVersion"):
            return False, f"initialize returned {initialized}"
        for capability in ("tools", "resources", "prompts"):
            if capability not in result.get("capabilities", {}):
                return False, f"{capability} is not advertised"
        if server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is not None:
            return False, "a notification was answered"

        listed = _call(server, "tools/list", identifier=2)["result"]["tools"]
        names = {tool["name"] for tool in listed}
        if not {"compile_score", "ensemble_read", "analyze_features"} <= names:
            return False, f"tools missing from the list: {sorted(names)}"
        for tool in listed:
            if tool.get("inputSchema", {}).get("type") != "object":
                return False, f"{tool['name']} has no object input schema"

        called = _call(
            server,
            "tools/call",
            {"name": "compile_score", "arguments": {"content": SAMPLE}},
            identifier=3,
        )["result"]
        if called.get("isError"):
            return False, f"compile_score failed: {called['content'][0]['text'][:120]}"
        return True, f"{len(listed)} tools, handshake and one call over JSON-RPC"


def check_protocol_errors() -> tuple[bool, str]:
    """Bad input is answered with the right code and never stops the loop."""
    with tempfile.TemporaryDirectory() as directory:
        server = _server(Path(directory))
        cases = [
            ("{not json", -32700),
            ('{"jsonrpc": "1.0", "id": 1, "method": "ping"}', -32600),
            ('{"jsonrpc": "2.0", "id": 2, "method": "nope/nope"}', -32601),
            ('{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {}}', -32602),
        ]
        for text, expected in cases:
            answer = server.handle_text(text)
            if answer is None:
                return False, f"{text[:24]!r} was not answered"
            code = json.loads(answer).get("error", {}).get("code")
            if code != expected:
                return False, f"{text[:24]!r} answered with {code}, expected {expected}"

        if server.handle_text('{"jsonrpc": "2.0", "method": "ping"}') is not None:
            return False, "a notification was answered"

        failing = _call(
            server,
            "tools/call",
            {"name": "read_file", "arguments": {"path": "nothing-here.song"}},
            identifier=4,
        )
        result = failing.get("result")
        if result is None or not result.get("isError"):
            return False, "a failing tool was not reported as a tool error"
        if "error" in failing:
            return False, "a failing tool was reported as a protocol error"
        return True, "parse, request, method, params and tool failures all reported correctly"


def check_ensemble_concurrency() -> tuple[bool, str]:
    """Two voices at once both land; two writes to one voice do not."""
    from . import ensemble

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        session = ensemble.open_session(
            "spec", root=root, title="Spec", key="Am", tempo=96, bars=2, voices=["@bass", "@violin1"]
        )
        outcomes: dict[str, Any] = {}

        def write(voice: str, agent: str, content: str, base: int) -> None:
            try:
                outcomes[agent] = session.write_part(voice, agent, content, base, "spec write")
            except ensemble.EnsembleError as exc:
                outcomes[agent] = exc

        threads = [
            threading.Thread(target=write, args=("bass", "one", BASS, 0)),
            threading.Thread(target=write, args=("violin1", "two", VIOLIN, 0)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        if any(isinstance(outcome, Exception) for outcome in outcomes.values()):
            return False, f"disjoint voices collided: {outcomes}"

        try:
            session.write_part("bass", "three", BASS, 0, "stale")
        except ensemble.Conflict as exc:
            if not exc.state.get("content"):
                return False, "a rejected write was not given the current part to rebase onto"
        except ensemble.EnsembleError as exc:
            return False, f"a stale write was refused for the wrong reason: {exc}"
        else:
            return False, "a stale write was accepted"

        state = session.read()
        if len(state["voices"]) != 2:
            return False, f"expected two voices, got {state['voices']}"
        return True, "two voices written at once; a write against an old version was refused"


def check_merge_is_deterministic() -> tuple[bool, str]:
    """The same parts always merge to the same bytes, whatever order they arrived in."""
    from . import ensemble

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        first = ensemble.open_session("one", root=root, title="Both", key="Am", tempo=96, bars=2)
        first.write_part("bass", "a", BASS, 0)
        first.write_part("violin1", "b", VIOLIN, 0)

        second = ensemble.open_session("two", root=root, title="Both", key="Am", tempo=96, bars=2)
        second.write_part("violin1", "b", VIOLIN, 0)
        second.write_part("bass", "a", BASS, 0)

        if first.score() != second.score():
            return False, "merge depends on the order the parts arrived in"
        if first.score() != first.score():
            return False, "merge is not repeatable"
        from ..notation import parse

        merged = parse(first.score())
        if merged.has_errors:
            return False, f"the merged score does not parse: {merged.errors()[0].message}"
        return True, f"{len(first.score().splitlines())} lines, identical from either order"


def check_features() -> tuple[bool, str]:
    """Sixteen features per bar, in range, and the same every time."""
    from .. import features
    from ..notation import arrange, parse

    arrangement = arrange(parse(SAMPLE))
    bars = features.extract(arrangement)
    if len(bars) != 2:
        return False, f"expected 2 bars, got {len(bars)}"
    for bar in bars:
        if len(bar.vector) != 16:
            return False, f"bar {bar.bar} produced {len(bar.vector)} features"
        for name, value in bar.values.items():
            low = -1.0 if name == "contour_direction" else 0.0
            if not low <= value <= 1.0:
                return False, f"{name} is {value}, outside [{low}, 1]"
    if [bar.vector for bar in bars] != [bar.vector for bar in features.extract(arrangement)]:
        return False, "the same arrangement produced different features"
    silent = "[A]\nMelody: | C4 D4 E4 F4 |\n\n[B]\nLyrics: | one two |\n\n[C]\nMelody: | G4 A4 B4 C5 |\n"
    middle = features.extract(arrange(parse(silent)))
    if len(middle) != 3 or middle[1].values["rest_ratio"] != 1.0:
        return False, "a bar with no notes in it is not reported as silent"
    return True, "16 features over 2 bars, in range and repeatable"


def check_resources_and_prompts() -> tuple[bool, str]:
    """The documented resources and prompts are there and readable."""
    with tempfile.TemporaryDirectory() as directory:
        server = _server(Path(directory))
        listed = _call(server, "resources/list")["result"]["resources"]
        uris = {resource["uri"] for resource in listed}
        if "plainsong://notation-reference" not in uris:
            return False, f"the notation reference is not listed: {sorted(uris)[:4]}"

        templates = _call(server, "resources/templates/list", identifier=2)["result"]
        patterns = {template["uriTemplate"] for template in templates["resourceTemplates"]}
        for wanted in ("plainsong://library/{name}", "plainsong://session/{name}"):
            if wanted not in patterns:
                return False, f"{wanted} is not offered as a template"

        read = _call(server, "resources/read", {"uri": "plainsong://capabilities"}, identifier=3)["result"][
            "contents"
        ][0]
        if not read["text"].strip().startswith("{"):
            return False, "capabilities did not come back as JSON"

        missing = _call(server, "resources/read", {"uri": "plainsong://spec/nothing"}, identifier=4)
        if "error" not in missing:
            return False, "an unknown resource was not reported as an error"

        prompts = _call(server, "prompts/list", identifier=5)["result"]["prompts"]
        names = {prompt["name"] for prompt in prompts}
        if not {"composer", "builder"} <= names:
            return False, f"prompts are {sorted(names)}"
        got = _call(server, "prompts/get", {"name": "composer"}, identifier=6)["result"]
        if not got["messages"][0]["content"]["text"].strip():
            return False, "the composer prompt came back empty"
        return True, f"{len(listed)} resources, {len(patterns)} templates, {len(names)} prompts"


def check_conductor_bridge() -> tuple[bool, str]:
    """The conductor is reached if it is installed, and reported if it is not."""
    with tempfile.TemporaryDirectory() as directory:
        server = _server(Path(directory))
        result = _call(
            server,
            "tools/call",
            {
                "name": "apply_directives",
                "arguments": {
                    "content": SAMPLE,
                    "directives": {
                        "directives": [{"action": "lay_back", "intensity": 0.5, "duration_beats": 4}]
                    },
                    "features": False,
                },
            },
        )["result"]
        text = result["content"][0]["text"]
        if result["isError"]:
            if "no conductor" in text:
                return True, "no conductor installed, and the tool said so instead of failing"
            return False, f"the bridge failed: {text[:160]}"
        report = json.loads(text)
        if "after" not in report:
            return False, f"the conducted result is missing its summary: {sorted(report)}"
        return True, "directives read and applied through plainsong.perform.conduct"
