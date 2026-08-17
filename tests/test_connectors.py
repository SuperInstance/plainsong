"""Connectors: plugin edges that bridge Plainsong to the outside world.

This suite verifies that connectors are discovered, validated, and run
correctly, that failed connectors degrade gracefully, and that the plugin
registry resists poisoning by broken modules. Network operations are mocked
throughout.
"""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

from plainsong.connectors.base import Connector, ConnectorRegistry, ConnectorResult
from plainsong.connectors.builtin import FileConnector, WebhookConnector
from plainsong.notation import arrange, parse

# Minimal test notation to create an Arrangement.
SIMPLE_TAP = """**TRACK: Test**
[MetaData]
title: Test Song | key: Dm | tempo: 120 | time: 4/4

[A] (1 bar)
@organ | d3 . . . |
"""


def make_arrangement():
    """Parse test notation and arrange it, the way the rest of the codebase does."""
    return arrange(parse(SIMPLE_TAP))


class TestConnectorResultBool(unittest.TestCase):
    """ConnectorResult.__bool__: failed is falsey, succeeded is truthy."""

    def test_failed_result_is_falsey(self):
        """A failed result evaluates to False in boolean context."""
        result = ConnectorResult(ok=False, detail="something went wrong")
        self.assertFalse(result)
        self.assertFalse(bool(result))

    def test_successful_result_is_truthy(self):
        """A successful result evaluates to True in boolean context."""
        result = ConnectorResult(ok=True, detail="all good")
        self.assertTrue(result)
        self.assertTrue(bool(result))

    def test_failed_result_with_outputs_is_still_falsey(self):
        """A failed result stays False even if it has outputs."""
        result = ConnectorResult(ok=False, detail="failed", outputs=["/tmp/file.mid"])
        self.assertFalse(result)


class TestConnectorRegistryRegister(unittest.TestCase):
    """ConnectorRegistry.register: rejects missing name, works as decorator."""

    def test_register_requires_name(self):
        """Registering a connector class without a name raises ValueError."""
        registry = ConnectorRegistry()

        class NoName(Connector):
            name = ""  # Empty name is invalid

            def send(self, arrangement, **options):
                pass

        with self.assertRaises(ValueError) as exc:
            registry.register(NoName)
        self.assertIn("needs a name", str(exc.exception))

    def test_register_works_as_decorator(self):
        """register() can be used as a class decorator."""
        registry = ConnectorRegistry()

        @registry.register
        class DecoratorConnector(Connector):
            name = "decorator_test"

            def send(self, arrangement, **options):
                return ConnectorResult(True)

        # The class should still be the same
        self.assertEqual(DecoratorConnector.name, "decorator_test")
        # And it should be in the registry
        self.assertIn("decorator_test", registry.names())

    def test_register_stores_class_in_registry(self):
        """Registering a connector makes it retrievable by name."""
        registry = ConnectorRegistry()

        @registry.register
        class MyConnector(Connector):
            name = "my_connector"

            def send(self, arrangement, **options):
                return ConnectorResult(True)

        retrieved = registry.get("my_connector")
        self.assertIs(retrieved, MyConnector)


class TestConnectorRegistryCreate(unittest.TestCase):
    """ConnectorRegistry.create: unknown name raises KeyError listing known names."""

    def test_create_unknown_name_raises_keyerror(self):
        """Creating a connector with an unknown name raises KeyError."""
        registry = ConnectorRegistry()

        @registry.register
        class KnownConnector(Connector):
            name = "known"

            def send(self, arrangement, **options):
                pass

        with self.assertRaises(KeyError) as exc:
            registry.create("unknown")
        error_msg = str(exc.exception)
        # Should mention the unknown name and list known ones
        self.assertIn("unknown", error_msg)
        self.assertIn("known", error_msg)

    def test_create_known_name_returns_instance(self):
        """Creating a connector with a known name returns an instance."""
        registry = ConnectorRegistry()

        @registry.register
        class TestConnector(Connector):
            name = "test"

            def send(self, arrangement, **options):
                return ConnectorResult(True)

        instance = registry.create("test")
        self.assertIsInstance(instance, TestConnector)


class TestDescribeAll(unittest.TestCase):
    """describe_all: returns row for connectors, including those that raise on construction."""

    def test_describe_all_includes_working_connector(self):
        """describe_all includes a description of a working connector."""
        registry = ConnectorRegistry()

        @registry.register
        class WorkingConnector(Connector):
            name = "working"
            summary = "This one works"

            def send(self, arrangement, **options):
                return ConnectorResult(True)

        descriptions = registry.describe_all()
        self.assertEqual(len(descriptions), 1)
        self.assertEqual(descriptions[0]["name"], "working")
        self.assertEqual(descriptions[0]["summary"], "This one works")

    def test_describe_all_survives_connector_construction_failure(self):
        """describe_all still returns a row even if a connector's __init__ raises."""
        registry = ConnectorRegistry()

        @registry.register
        class BrokenInit(Connector):
            name = "broken_init"

            def __init__(self, config=None, **options):
                raise RuntimeError("Broken from the start")

            def send(self, arrangement, **options):
                pass

        @registry.register
        class WorkingConnector(Connector):
            name = "working"

            def send(self, arrangement, **options):
                return ConnectorResult(True)

        descriptions = registry.describe_all()
        # Should have 2 connectors, not crash
        self.assertEqual(len(descriptions), 2)
        # Find the broken one
        broken_desc = next(d for d in descriptions if d["name"] == "broken_init")
        self.assertFalse(broken_desc["available"])
        self.assertIn("Broken from the start", broken_desc["detail"])


class TestLoadDirectory(unittest.TestCase):
    """load_directory: loads modules from temp dir, skips broken ones, preserves others."""

    def test_load_directory_loads_valid_connector_module(self):
        """load_directory loads a valid connector module from a temp directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Write a valid connector module
            connector_file = tmppath / "my_connector.py"
            connector_file.write_text("""
from plainsong.connectors.base import Connector, ConnectorResult, registry

@registry.register
class MyConnector(Connector):
    name = "my_test_connector"
    def send(self, arrangement, **options):
        return ConnectorResult(True, detail="works")
""")

            registry = ConnectorRegistry()
            # Patch the global registry so loaded modules use our test registry
            with patch("plainsong.connectors.base.registry", registry):
                loaded = registry.load_directory(tmppath)
            self.assertIn("my_connector", loaded)
            # The connector should now be available
            self.assertIsNotNone(registry.get("my_test_connector"))

    def test_load_directory_silently_skips_broken_module(self):
        """load_directory silently skips a module that raises on import."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Write a broken module
            broken_file = tmppath / "broken.py"
            broken_file.write_text("raise RuntimeError('This module is broken')")

            # Write a working module that should still load
            working_file = tmppath / "working.py"
            working_file.write_text("""
from plainsong.connectors.base import Connector, ConnectorResult, registry

@registry.register
class WorkingConnector(Connector):
    name = "working_loaded"
    def send(self, arrangement, **options):
        return ConnectorResult(True)
""")

            registry = ConnectorRegistry()
            with patch("plainsong.connectors.base.registry", registry):
                loaded = registry.load_directory(tmppath)
            # Broken module should NOT be in loaded list
            self.assertNotIn("broken", loaded)
            # Working module SHOULD be in loaded list and functional
            self.assertIn("working", loaded)
            self.assertIsNotNone(registry.get("working_loaded"))

    def test_load_directory_skips_underscore_prefixed_files(self):
        """load_directory skips files starting with underscore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Write a module that should be skipped
            skipped_file = tmppath / "_internal.py"
            skipped_file.write_text("""
from plainsong.connectors.base import Connector, ConnectorResult, registry

@registry.register
class InternalConnector(Connector):
    name = "internal"
    def send(self, arrangement, **options):
        return ConnectorResult(True)
""")

            registry = ConnectorRegistry()
            with patch("plainsong.connectors.base.registry", registry):
                loaded = registry.load_directory(tmppath)
            self.assertNotIn("_internal", loaded)
            # Connector should not be accessible
            self.assertIsNone(registry.get("internal"))

    def test_load_directory_returns_empty_for_nonexistent_directory(self):
        """load_directory returns [] for a directory that does not exist."""
        registry = ConnectorRegistry()
        loaded = registry.load_directory(Path("/nonexistent/directory/path"))
        self.assertEqual(loaded, [])

    def test_load_directory_does_not_reload_same_path_twice(self):
        """load_directory does not load the same path twice."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            connector_file = tmppath / "once.py"
            connector_file.write_text("""
from plainsong.connectors.base import Connector, ConnectorResult, registry

@registry.register
class OnceConnector(Connector):
    name = "once"
    def send(self, arrangement, **options):
        return ConnectorResult(True)
""")

            registry = ConnectorRegistry()
            with patch("plainsong.connectors.base.registry", registry):
                # First load
                loaded1 = registry.load_directory(tmppath)
                self.assertIn("once", loaded1)

                # Try to load the same path again
                loaded2 = registry.load_directory(tmppath)
                # Should return empty because the path is already in _loaded_paths
                self.assertEqual(loaded2, [])


class TestConnectorAvailable(unittest.TestCase):
    """Connector.available: returns False with detail for missing capabilities."""

    def test_available_with_no_requires_returns_true(self):
        """A connector with requires=() returns (True, 'ready')."""

        class SimpleConnector(Connector):
            name = "simple"
            requires = ()

            def send(self, arrangement, **options):
                return ConnectorResult(True)

        connector = SimpleConnector()
        ok, detail = connector.available()
        self.assertTrue(ok)
        self.assertEqual(detail, "ready")

    def test_available_with_missing_capability_returns_false(self):
        """A connector requiring a missing capability returns (False, detail)."""

        class RequiresCapability(Connector):
            name = "requires_test"
            requires = ("nonexistent_capability",)

            def send(self, arrangement, **options):
                return ConnectorResult(True)

        connector = RequiresCapability()
        ok, detail = connector.available()
        self.assertFalse(ok)
        self.assertIn("nonexistent_capability", detail)


class TestFileConnector(unittest.TestCase):
    """FileConnector: writes .mid and .wav files, respects options, creates dirs."""

    def test_file_connector_writes_midi(self):
        """FileConnector writes a .mid file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            arrangement = make_arrangement()

            connector = FileConnector()
            result = connector.send(arrangement, directory=str(tmppath), audio=False)

            self.assertTrue(result)
            # Check that a MIDI file was created
            mid_files = list(tmppath.glob("*.mid"))
            self.assertEqual(len(mid_files), 1)
            self.assertGreater(mid_files[0].stat().st_size, 0)

    def test_file_connector_writes_wav_when_audio_enabled(self):
        """FileConnector writes a .wav file when audio is not disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            arrangement = make_arrangement()

            connector = FileConnector()
            result = connector.send(arrangement, directory=str(tmppath), audio=True)

            self.assertTrue(result)
            # Check that both MIDI and WAV were created
            mid_files = list(tmppath.glob("*.mid"))
            wav_files = list(tmppath.glob("*.wav"))
            self.assertEqual(len(mid_files), 1)
            self.assertEqual(len(wav_files), 1)
            self.assertGreater(mid_files[0].stat().st_size, 0)
            self.assertGreater(wav_files[0].stat().st_size, 0)

    def test_file_connector_skips_wav_when_audio_disabled(self):
        """FileConnector does not write .wav when audio is False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            arrangement = make_arrangement()

            connector = FileConnector()
            result = connector.send(arrangement, directory=str(tmppath), audio=False)

            self.assertTrue(result)
            wav_files = list(tmppath.glob("*.wav"))
            self.assertEqual(len(wav_files), 0)

    def test_file_connector_honours_directory_option(self):
        """FileConnector writes to the specified directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            subdir = tmppath / "music"
            arrangement = make_arrangement()

            connector = FileConnector()
            result = connector.send(arrangement, directory=str(subdir), audio=False)

            self.assertTrue(result)
            self.assertTrue(subdir.is_dir())
            self.assertGreater(len(list(subdir.glob("*.mid"))), 0)

    def test_file_connector_derives_stem_from_title(self):
        """FileConnector uses the arrangement's title as the filename stem."""
        tap_with_title = """**TRACK: My Awesome Song**
[MetaData]
key: Dm | tempo: 120 | time: 4/4

[A] (1 bar)
@organ | d3 . . . |
"""
        arrangement = arrange(parse(tap_with_title))

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            connector = FileConnector()
            result = connector.send(arrangement, directory=str(tmppath), audio=False)

            self.assertTrue(result)
            # Check that stem is derived from title (lowercase, spaces to dashes)
            mid_files = list(tmppath.glob("*.mid"))
            self.assertEqual(len(mid_files), 1)
            self.assertIn("my-awesome-song", mid_files[0].name)

    def test_file_connector_falls_back_to_default_stem_when_title_empty(self):
        """FileConnector falls back to 'plainsong' when title is empty."""
        tap_no_title = """[MetaData]
key: Dm | tempo: 120 | time: 4/4

[A] (1 bar)
@organ | d3 . . . |
"""
        arrangement = arrange(parse(tap_no_title))

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            connector = FileConnector()
            result = connector.send(arrangement, directory=str(tmppath), audio=False)

            self.assertTrue(result)
            mid_files = list(tmppath.glob("*.mid"))
            self.assertEqual(len(mid_files), 1)
            self.assertIn("plainsong", mid_files[0].name)

    def test_file_connector_creates_directory_if_missing(self):
        """FileConnector creates the output directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            missing_dir = tmppath / "level1" / "level2" / "music"
            arrangement = make_arrangement()

            connector = FileConnector()
            result = connector.send(arrangement, directory=str(missing_dir), audio=False)

            self.assertTrue(result)
            self.assertTrue(missing_dir.is_dir())
            self.assertGreater(len(list(missing_dir.glob("*.mid"))), 0)

    def test_file_connector_outputs_list_contains_file_paths(self):
        """FileConnector result includes the paths to created files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            arrangement = make_arrangement()

            connector = FileConnector()
            result = connector.send(arrangement, directory=str(tmppath), audio=False)

            self.assertTrue(result)
            self.assertEqual(len(result.outputs), 1)
            self.assertTrue(Path(result.outputs[0]).exists())


class TestWebhookConnector(unittest.TestCase):
    """WebhookConnector: posts to URLs, includes MIDI if requested, handles errors."""

    def test_webhook_connector_no_url_fails_without_network_call(self):
        """WebhookConnector with no url returns failed result without calling urlopen."""
        arrangement = make_arrangement()
        connector = WebhookConnector()

        result = connector.send(arrangement)

        self.assertFalse(result)
        self.assertIn("no url", result.detail)

    def test_webhook_connector_empty_url_fails_without_network_call(self):
        """WebhookConnector with empty url returns failed result without calling urlopen."""
        arrangement = make_arrangement()
        connector = WebhookConnector()

        result = connector.send(arrangement, url="   ")

        self.assertFalse(result)

    @patch("urllib.request.urlopen")
    def test_webhook_connector_http_200_returns_success(self, mock_urlopen):
        """WebhookConnector with 200 response returns successful result."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        arrangement = make_arrangement()
        connector = WebhookConnector()

        result = connector.send(arrangement, url="http://example.com/webhook")

        self.assertTrue(result)
        self.assertIn("200", result.detail)
        mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_webhook_connector_http_500_returns_failure(self, mock_urlopen):
        """WebhookConnector with 500 response returns failed result with status."""
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        arrangement = make_arrangement()
        connector = WebhookConnector()

        result = connector.send(arrangement, url="http://example.com/webhook")

        self.assertFalse(result)
        self.assertIn("500", result.detail)

    @patch("urllib.request.urlopen")
    def test_webhook_connector_exception_returns_failure(self, mock_urlopen):
        """WebhookConnector with network exception returns failed result."""
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        arrangement = make_arrangement()
        connector = WebhookConnector()

        result = connector.send(arrangement, url="http://example.com/webhook")

        self.assertFalse(result)
        self.assertIn("URLError", result.detail)

    @patch("urllib.request.urlopen")
    def test_webhook_connector_include_midi_base64_encoded(self, mock_urlopen):
        """WebhookConnector with include_midi encodes MIDI as base64 in body."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        arrangement = make_arrangement()
        connector = WebhookConnector()

        result = connector.send(
            arrangement,
            url="http://example.com/webhook",
            include_midi=True,
        )

        self.assertTrue(result)
        # Extract the body that was posted
        call_args = mock_urlopen.call_args
        request = call_args[0][0]  # First positional arg is the Request
        body = request.data
        payload = json.loads(body.decode("utf-8"))

        # Check that midi_base64 is present
        self.assertIn("midi_base64", payload)
        # Verify it's valid base64 by decoding it
        midi_bytes = base64.b64decode(payload["midi_base64"])
        # Should start with MIDI header
        self.assertTrue(midi_bytes.startswith(b"MThd"))

    @patch("urllib.request.urlopen")
    def test_webhook_connector_merges_caller_headers(self, mock_urlopen):
        """WebhookConnector merges caller-provided headers with Content-Type."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        arrangement = make_arrangement()
        caller_headers = {"Authorization": "Bearer token123", "X-Custom": "value"}
        connector = WebhookConnector()

        result = connector.send(
            arrangement,
            url="http://example.com/webhook",
            headers=caller_headers,
        )

        self.assertTrue(result)
        # Check the headers in the request
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        headers = request.headers

        # Should have Content-Type
        self.assertIn("content-type", {k.lower() for k in headers.keys()})
        # Should have custom headers
        self.assertIn("Authorization", headers)
        self.assertEqual(headers["Authorization"], "Bearer token123")


class TestBaseRun(unittest.TestCase):
    """base.run(): returns failed ConnectorResult when connector unavailable."""

    def test_run_returns_failed_result_when_connector_unavailable(self):
        """run() returns failed ConnectorResult when connector is not available."""
        from plainsong.connectors import base

        arrangement = make_arrangement()

        # Mock the discover function to return a registry with a connector that's unavailable
        unavailable_registry = ConnectorRegistry()

        @unavailable_registry.register
        class UnavailableConnector(Connector):
            name = "unavailable_test"
            requires = ("nonexistent_capability",)

            def send(self, arrangement, **options):
                # This should never be called
                raise AssertionError("send() should not be called for unavailable connector")

        with patch("plainsong.connectors.base.discover") as mock_discover:
            mock_discover.return_value = unavailable_registry

            result = base.run("unavailable_test", arrangement)

            self.assertFalse(result)
            self.assertIn("nonexistent_capability", result.detail)
            # Verify that send was never called
            # (we can't directly check this, but if send() was called, it would raise)

    @patch("urllib.request.urlopen")
    def test_run_successfully_runs_available_connector(self, mock_urlopen):
        """run() successfully calls send() when connector is available."""
        from plainsong.connectors import base

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        arrangement = make_arrangement()

        # The global registry should have the webhook connector registered
        result = base.run(
            "webhook",
            arrangement,
            url="http://example.com/webhook",
        )

        self.assertTrue(result)
        mock_urlopen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
