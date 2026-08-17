"""tools.register and Resources() no longer hard-bind to this repo's ensemble.py.

They used to resolve it with a bare relative import (``from . import ensemble
as ens``), which meant the sibling plainsong-mcp repo could not share these
two files without silently binding its tool surface to *this* repo's copy of
ensemble.py. Both now accept the ensemble implementation as a parameter and
fall back to this package's own module only when none is given, so:

  - calling them with nothing (as ``plainsong.mcp.server`` does) behaves
    exactly as before, and
  - calling them with a different module -- as the sibling repo would --
    makes every ensemble_* tool and every session resource call into *that*
    module instead.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from plainsong.agent.tools import Sandbox, ToolRegistry
from plainsong.mcp import tools as mcp_tools
from plainsong.mcp.resources import Resources
from plainsong.runtime.config import load_config


class FakeEnsembleError(Exception):
    pass


class FakeConflict(FakeEnsembleError):
    def __init__(self, message: str, state: object = None) -> None:
        super().__init__(message)
        self.state = state


class FakeSession:
    """A stand-in for plainsong.mcp.ensemble.Session."""


def fake_ensemble_module(calls: list[str]) -> SimpleNamespace:
    """A minimal object with the same names as plainsong.mcp.ensemble.

    Every entry point tools.py and resources.py can reach records its name in
    *calls*, so a test can tell the injected module was actually used rather
    than the real one.
    """

    def list_sessions(root, paths):
        calls.append("list_sessions")
        return ["from-fake-module"]

    def find_session(name, root=None, paths=None):
        calls.append("find_session")
        raise FakeEnsembleError(f"fake: no such session {name!r}")

    def open_session(name, **kwargs):
        calls.append("open_session")
        raise FakeEnsembleError("fake: open_session called")

    def parse_bar_range(bars, count):
        calls.append("parse_bar_range")
        return 1, count

    return SimpleNamespace(
        Session=FakeSession,
        EnsembleError=FakeEnsembleError,
        Conflict=FakeConflict,
        list_sessions=list_sessions,
        find_session=find_session,
        open_session=open_session,
        parse_bar_range=parse_bar_range,
    )


def build_registry(directory: Path) -> ToolRegistry:
    config = load_config()
    return ToolRegistry(sandbox=Sandbox(root=directory / "work"), config=config)


class TestToolsRegisterInjection(unittest.TestCase):
    def test_default_still_uses_this_repos_ensemble(self) -> None:
        """Calling register() the way server.py does must not change behaviour."""
        with tempfile.TemporaryDirectory() as raw:
            registry = build_registry(Path(raw))
            mcp_tools.register(registry, session_root=Path(raw) / "sessions")
            self.assertEqual(len(registry.specs()), 27)

            # ensemble_status with no session name lists real sessions -- an
            # empty list from a fresh directory, not a "fake:" answer.
            text, failed = registry.call_result("ensemble_status", {})
            self.assertFalse(failed, text)
            self.assertNotIn("fake", text)

    def test_injected_ensemble_module_is_actually_used(self) -> None:
        """Passing ensemble= must route every ensemble_* tool through it."""
        calls: list[str] = []
        fake = fake_ensemble_module(calls)
        with tempfile.TemporaryDirectory() as raw:
            registry = build_registry(Path(raw))
            mcp_tools.register(
                registry, session_root=Path(raw) / "sessions", ensemble=fake
            )
            self.assertEqual(len(registry.specs()), 27, "injection must not add or drop tools")

            text, failed = registry.call_result("ensemble_status", {})
            self.assertFalse(failed, text)
            self.assertIn("from-fake-module", text)
            self.assertIn("list_sessions", calls)

            text, failed = registry.call_result(
                "ensemble_join", {"session": "s", "voice": "@bass", "agent": "a"}
            )
            self.assertTrue(failed)
            self.assertIn("fake: no such session", text)
            self.assertIn("find_session", calls)

    def test_two_registrations_do_not_share_state(self) -> None:
        """Each register() call is free to be given a different module."""
        calls_a: list[str] = []
        calls_b: list[str] = []
        with tempfile.TemporaryDirectory() as raw:
            registry_a = build_registry(Path(raw))
            registry_b = build_registry(Path(raw))
            mcp_tools.register(registry_a, ensemble=fake_ensemble_module(calls_a))
            mcp_tools.register(registry_b, ensemble=fake_ensemble_module(calls_b))

            registry_a.call_result("ensemble_status", {})
            self.assertEqual(calls_a, ["list_sessions"])
            self.assertEqual(calls_b, [])


class TestResourcesInjection(unittest.TestCase):
    def test_default_still_uses_this_repos_ensemble(self) -> None:
        config = load_config()
        with tempfile.TemporaryDirectory() as raw:
            resources = Resources(config, session_root=Path(raw) / "sessions")
            self.assertEqual(resources._sessions(), [])
            found = resources.list()
            self.assertEqual(len(found), 9)

    def test_injected_ensemble_module_is_actually_used(self) -> None:
        calls: list[str] = []
        fake = fake_ensemble_module(calls)
        config = load_config()
        with tempfile.TemporaryDirectory() as raw:
            resources = Resources(config, session_root=Path(raw) / "sessions", ensemble=fake)
            self.assertEqual(resources._sessions(), ["from-fake-module"])
            self.assertIn("list_sessions", calls)

            found = resources.list()
            # One more than the sessionless baseline: the fake module reports
            # one session ("from-fake-module"), and each session lists as its
            # own resource. The fixed set (notation-reference, capabilities,
            # every spec) is unchanged by which ensemble module is injected.
            self.assertEqual(len(found), 10)
            names = [entry["name"] for entry in found]
            self.assertIn("session: from-fake-module", names)


if __name__ == "__main__":
    unittest.main()
