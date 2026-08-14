"""Tests for the web interface without requiring a real browser."""

from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tapscript.interfaces.web.server import MAX_BODY, Api, build_handler
from tapscript.runtime.config import Config
from tapscript.runtime.paths import Paths

MINIMAL_NOTATION = """**TRACK: Test Piece**
[MetaData]
key: C | tempo: 100 | meter: 4/4

[Section]
Melody: | C4 D4 E4 F4 |
"""

VALID_NOTATION = """**TRACK: Transpose Test**
[MetaData]
key: C | tempo: 120 | meter: 4/4

[Section]
Melody: | C4 E4 G4 C5 |
"""


class TestApiSameOrigin(unittest.TestCase):
    """Test the _same_origin method for cross-origin rejection."""

    def setUp(self):
        """Create a temporary config with workspace."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.env_patch = mock.patch.dict(os.environ, {"TAPSCRIPT_WORKSPACE": str(self.workspace)})
        self.env_patch.start()
        self.config = Config(data={}, paths=Paths(project_root=None))

    def tearDown(self):
        """Clean up temp directory."""
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def _make_request_with_origin(self, origin: str | None) -> dict[str, Any]:
        """Helper to make a POST request and capture the response."""
        handler_class = build_handler(self.config)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        self.addCleanup(server.server_close)

        port = server.server_port

        def run_server():
            server.handle_request()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

        url = f"http://127.0.0.1:{port}/api/compile"
        request = Request(url, method="POST")
        if origin is not None:
            request.add_header("Origin", origin)
        request.add_header("Content-Type", "application/json")
        request.data = json.dumps({"content": MINIMAL_NOTATION}).encode("utf-8")

        try:
            response = urlopen(request)
            return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_no_origin_header_is_allowed(self):
        """A POST without Origin header should be accepted."""
        status, response = self._make_request_with_origin(None)
        # Should succeed or at least not be rejected for origin
        self.assertNotEqual(status, 403)

    def test_origin_with_matching_netloc_is_allowed(self):
        """A POST with an Origin matching the Host should be accepted."""
        handler_class = build_handler(self.config)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        self.addCleanup(server.server_close)

        port = server.server_port
        host = f"127.0.0.1:{port}"

        def run_server():
            server.handle_request()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

        url = f"http://127.0.0.1:{port}/api/compile"
        request = Request(url, method="POST")
        request.add_header("Origin", f"http://{host}")
        request.add_header("Content-Type", "application/json")
        request.data = json.dumps({"content": MINIMAL_NOTATION}).encode("utf-8")

        try:
            response = urlopen(request)
            status = response.status
        except HTTPError as e:
            status = e.code

        self.assertNotEqual(status, 403)

    def test_mismatched_origin_gets_403_on_post(self):
        """A POST with a mismatched Origin should return 403."""
        handler_class = build_handler(self.config)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        self.addCleanup(server.server_close)

        port = server.server_port

        def run_server():
            server.handle_request()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

        url = f"http://127.0.0.1:{port}/api/compile"
        request = Request(url, method="POST")
        request.add_header("Origin", "http://evil.com:9999")
        request.add_header("Content-Type", "application/json")
        request.data = json.dumps({"content": MINIMAL_NOTATION}).encode("utf-8")

        with self.assertRaises(HTTPError) as cm:
            urlopen(request)

        self.assertEqual(cm.exception.code, 403)
        response_data = json.loads(cm.exception.read().decode("utf-8"))
        self.assertIn("error", response_data)


class TestApiCompile(unittest.TestCase):
    """Test the compile API method."""

    def setUp(self):
        """Create a temporary config with workspace."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.env_patch = mock.patch.dict(os.environ, {"TAPSCRIPT_WORKSPACE": str(self.workspace)})
        self.env_patch.start()
        self.config = Config(data={}, paths=Paths(project_root=None))
        self.api = Api(self.config)

    def tearDown(self):
        """Clean up temp directory."""
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_empty_content_returns_error(self):
        """Compiling empty content should return an error dict."""
        result = self.api.compile({})
        self.assertIn("error", result)

    def test_whitespace_only_content_returns_error(self):
        """Compiling whitespace-only content should return an error dict."""
        result = self.api.compile({"content": "   \n\n  "})
        self.assertIn("error", result)

    def test_valid_notation_returns_ok_and_midi_url(self):
        """Compiling valid notation should return ok and midi_url."""
        result = self.api.compile({"content": MINIMAL_NOTATION})
        self.assertTrue(result.get("ok"))
        self.assertIn("midi_url", result)
        self.assertTrue(result["midi_url"].startswith("/files/"))

    def test_valid_notation_includes_midi_url(self):
        """The midi_url should point to the output file."""
        result = self.api.compile({"content": MINIMAL_NOTATION})
        midi_url = result.get("midi_url", "")
        self.assertIn(".mid", midi_url)

    def test_audio_false_produces_no_audio_url(self):
        """With audio=False, no audio_url should be in response."""
        result = self.api.compile({"content": MINIMAL_NOTATION, "audio": False})
        self.assertNotIn("audio_url", result)

    def test_audio_true_produces_audio_url(self):
        """With audio=True (or default), audio_url should be in response."""
        result = self.api.compile({"content": MINIMAL_NOTATION, "audio": True})
        # Only if audio rendering succeeded
        if "audio_url" in result:
            self.assertTrue(result["audio_url"].startswith("/files/"))


class TestApiTranspose(unittest.TestCase):
    """Test the transpose API method."""

    def setUp(self):
        """Create a temporary config with workspace."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.env_patch = mock.patch.dict(os.environ, {"TAPSCRIPT_WORKSPACE": str(self.workspace)})
        self.env_patch.start()
        self.config = Config(data={}, paths=Paths(project_root=None))
        self.api = Api(self.config)

    def tearDown(self):
        """Clean up temp directory."""
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_missing_content_returns_error(self):
        """Transposing without content should return an error dict."""
        result = self.api.transpose({"key": "D"})
        self.assertIn("error", result)

    def test_missing_key_returns_error(self):
        """Transposing without key should return an error dict."""
        result = self.api.transpose({"content": VALID_NOTATION})
        self.assertIn("error", result)

    def test_valid_key_string_transposes(self):
        """Transposing to a named key should succeed."""
        result = self.api.transpose({"content": VALID_NOTATION, "key": "D"})
        self.assertIn("content", result)
        self.assertNotIn("error", result)

    def test_valid_key_integer_transposes(self):
        """Transposing by a semitone offset should succeed."""
        result = self.api.transpose({"content": VALID_NOTATION, "key": "2"})
        self.assertIn("content", result)
        self.assertNotIn("error", result)

    def test_an_unreadable_key_is_refused_rather_than_guessed_at(self):
        """A key that names nothing is an error, not a silent near-miss.

        `parse_key` is forgiving so that a hand-typed `Key:` header cannot stop a
        file loading, and it reads "banana" as B major. Applied to a transpose
        request that forgiveness would hand back a real, wrong transposition.
        """
        for key in ("Z", "banana", "hello world", "H#"):
            with self.subTest(key=key):
                result = self.api.transpose({"content": VALID_NOTATION, "key": key})
                self.assertIn("error", result)
                self.assertNotIn("content", result)


class TestApiReadEntry(unittest.TestCase):
    """Test the read_entry API method."""

    def setUp(self):
        """Create a temporary config with workspace."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.env_patch = mock.patch.dict(os.environ, {"TAPSCRIPT_WORKSPACE": str(self.workspace)})
        self.env_patch.start()
        self.config = Config(data={}, paths=Paths(project_root=None))
        self.api = Api(self.config)

    def tearDown(self):
        """Clean up temp directory."""
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_nonexistent_entry_returns_error_dict(self):
        """Reading a non-existent entry should return an error dict, not raise."""
        result = self.api.read_entry("nonexistent_entry_12345")
        self.assertIn("error", result)
        self.assertNotIn("content", result)


class TestBodyHandling(unittest.TestCase):
    """Test the _body method for handling request bodies."""

    def setUp(self):
        """Create a temporary config with workspace."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.env_patch = mock.patch.dict(os.environ, {"TAPSCRIPT_WORKSPACE": str(self.workspace)})
        self.env_patch.start()
        self.config = Config(data={}, paths=Paths(project_root=None))

    def tearDown(self):
        """Clean up temp directory."""
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_an_oversized_content_length_is_refused_without_reading_it(self):
        """A body larger than MAX_BODY must be declined, not read.

        Sent over a raw connection: `urllib` recomputes Content-Length from the
        data it is actually given, so a request built that way can never declare
        a length it does not send, and the limit is never reached. Without the
        limit the handler would sit in `rfile.read()` waiting for 100 MB that is
        not coming, so this test would time out rather than fail.
        """
        handler_class = build_handler(self.config)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        self.addCleanup(server.server_close)
        port = server.server_port
        threading.Thread(target=server.handle_request, daemon=True).start()

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        self.addCleanup(connection.close)
        connection.putrequest("POST", "/api/compile", skip_accept_encoding=True)
        connection.putheader("Host", f"127.0.0.1:{port}")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(MAX_BODY + 1))
        connection.endheaders()
        connection.send(b"x" * 100)  # nowhere near what was declared

        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        self.assertIn("error", result)

    def test_zero_content_length_returns_empty_dict(self):
        """A request with Content-Length=0 should return empty dict from _body."""
        handler_class = build_handler(self.config)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        self.addCleanup(server.server_close)

        port = server.server_port

        def run_server():
            server.handle_request()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

        url = f"http://127.0.0.1:{port}/api/compile"
        request = Request(url, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Content-Length", "0")
        request.data = b""

        try:
            response = urlopen(request)
            result = json.loads(response.read().decode("utf-8"))
        except HTTPError as e:
            result = json.loads(e.read().decode("utf-8"))

        # With zero Content-Length, body parsing returns {}, so compile gets empty content
        self.assertIn("error", result)

    def test_malformed_json_returns_empty_dict(self):
        """A request with malformed JSON should return empty dict from _body."""
        handler_class = build_handler(self.config)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        self.addCleanup(server.server_close)

        port = server.server_port

        def run_server():
            server.handle_request()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

        url = f"http://127.0.0.1:{port}/api/compile"
        request = Request(url, method="POST")
        request.add_header("Content-Type", "application/json")
        malformed = b"{this is not valid json"
        request.add_header("Content-Length", str(len(malformed)))
        request.data = malformed

        try:
            response = urlopen(request)
            result = json.loads(response.read().decode("utf-8"))
        except HTTPError as e:
            result = json.loads(e.read().decode("utf-8"))

        # With malformed JSON, body parsing returns {}, so compile gets empty content
        self.assertIn("error", result)

    def test_non_utf8_bytes_returns_empty_dict(self):
        """A request with non-UTF-8 bytes should return empty dict from _body."""
        handler_class = build_handler(self.config)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        self.addCleanup(server.server_close)

        port = server.server_port

        def run_server():
            server.handle_request()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

        url = f"http://127.0.0.1:{port}/api/compile"
        request = Request(url, method="POST")
        request.add_header("Content-Type", "application/json")
        # Invalid UTF-8 sequence
        invalid_utf8 = b'\xff\xfe invalid utf8'
        request.add_header("Content-Length", str(len(invalid_utf8)))
        request.data = invalid_utf8

        try:
            response = urlopen(request)
            result = json.loads(response.read().decode("utf-8"))
        except HTTPError as e:
            result = json.loads(e.read().decode("utf-8"))

        # With non-UTF-8 bytes, body parsing returns {}, so compile gets empty content
        self.assertIn("error", result)


class TestFilesPathTraversal(unittest.TestCase):
    """Test the /files/ route for path traversal protection."""

    def setUp(self):
        """Create a temporary config with workspace and test files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        output_dir = self.workspace / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create a real file in output_dir
        self.test_file = output_dir / "test.txt"
        self.test_file.write_text("test content")

        # Create a file outside output_dir to test traversal
        self.external_file = Path(self.temp_dir.name) / "external.txt"
        self.external_file.write_text("external content")

        self.env_patch = mock.patch.dict(os.environ, {"TAPSCRIPT_WORKSPACE": str(self.workspace)})
        self.env_patch.start()
        self.config = Config(data={}, paths=Paths(project_root=None))

    def tearDown(self):
        """Clean up temp directory."""
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def _make_get_request(self, path: str) -> tuple[int, str]:
        """Helper to make a GET request and capture the response."""
        handler_class = build_handler(self.config)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        self.addCleanup(server.server_close)

        port = server.server_port

        def run_server():
            server.handle_request()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

        url = f"http://127.0.0.1:{port}{path}"
        request = Request(url, method="GET")

        try:
            response = urlopen(request)
            body = response.read()
            return response.status, body.decode("utf-8", errors="replace")
        except HTTPError as e:
            body = e.read()
            return e.code, body.decode("utf-8", errors="replace")

    def test_real_file_in_output_dir_is_served(self):
        """A real file in output_dir should be served with 200."""
        status, body = self._make_get_request("/files/test.txt")
        self.assertEqual(status, 200)
        self.assertIn("test content", body)

    def test_real_file_has_correct_content_type(self):
        """A served file should have the correct Content-Type."""
        handler_class = build_handler(self.config)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        self.addCleanup(server.server_close)

        port = server.server_port

        def run_server():
            server.handle_request()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

        url = f"http://127.0.0.1:{port}/files/test.txt"
        response = urlopen(url)

        content_type = response.headers.get("Content-Type")
        self.assertIsNotNone(content_type)
        self.assertIn("text", content_type.lower())

    def _raw_get(self, path: str) -> tuple[int, bytes]:
        """GET *path* exactly as written, without client-side normalisation.

        `urlopen` collapses `..` segments before the request leaves the process,
        so a traversal sent that way never reaches the handler at all and the 404
        it returns proves nothing. `http.client` sends the path verbatim.
        """
        handler_class = build_handler(self.config)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        self.addCleanup(server.server_close)
        port = server.server_port
        threading.Thread(target=server.handle_request, daemon=True).start()

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        self.addCleanup(connection.close)
        connection.putrequest("GET", path, skip_host=False, skip_accept_encoding=True)
        connection.putheader("Host", f"127.0.0.1:{port}")
        connection.endheaders()
        response = connection.getresponse()
        return response.status, response.read()

    def test_a_traversal_out_of_the_output_directory_is_refused(self):
        """`..` segments must not reach a file outside the output directory.

        Sent raw, so that removing the basename guard in `_serve_output` makes
        this fail. `self.external_file` sits one level above the output dir.
        """
        for path in (
            "/files/../external.txt",
            "/files/../../external.txt",
            "/files/%2e%2e/external.txt",
            "/files/..%2fexternal.txt",
        ):
            with self.subTest(path=path):
                status, body = self._raw_get(path)
                self.assertEqual(status, 404)
                self.assertNotIn(b"external content", body)

    def test_an_absolute_path_is_refused(self):
        """A rooted path must not escape the output directory either."""
        status, body = self._raw_get("/files//etc/passwd")
        self.assertEqual(status, 404)
        self.assertNotIn(b"root:", body)

    def test_a_name_that_needs_decoding_is_served(self):
        """`my song.wav` reaches the handler as `my%20song.wav` and must still resolve."""
        (self.workspace / "output" / "my song.wav").write_bytes(b"RIFFtest")
        status, body = self._raw_get("/files/my%20song.wav")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"RIFFtest")

    def test_a_null_byte_in_the_name_is_refused_without_raising(self):
        """A null byte makes pathlib raise; it must be a 404, not a 500."""
        status, _body = self._raw_get("/files/test%00.txt")
        self.assertEqual(status, 404)

    def test_nonexistent_file_returns_404(self):
        """A nonexistent file should return 404."""
        status, _body = self._make_get_request("/files/nonexistent.txt")
        self.assertEqual(status, 404)


class TestRoutes(unittest.TestCase):
    """Test HTTP routes and methods."""

    def setUp(self):
        """Create a temporary config with workspace."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.env_patch = mock.patch.dict(os.environ, {"TAPSCRIPT_WORKSPACE": str(self.workspace)})
        self.env_patch.start()
        self.config = Config(data={}, paths=Paths(project_root=None))

    def tearDown(self):
        """Clean up temp directory."""
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def _make_request(
        self, method: str, path: str, data: bytes | None = None
    ) -> tuple[int, dict[str, Any]]:
        """Helper to make an HTTP request and capture the JSON response."""
        handler_class = build_handler(self.config)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        self.addCleanup(server.server_close)

        port = server.server_port

        def run_server():
            server.handle_request()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

        url = f"http://127.0.0.1:{port}{path}"
        request = Request(url, method=method)
        if data:
            request.add_header("Content-Type", "application/json")
            request.data = data

        try:
            response = urlopen(request)
            body = json.loads(response.read().decode("utf-8"))
            return response.status, body
        except HTTPError as e:
            body = json.loads(e.read().decode("utf-8"))
            return e.code, body

    def test_unknown_get_route_returns_404(self):
        """A GET to an unknown route should return 404 with JSON body."""
        status, response = self._make_request("GET", "/api/unknown")
        self.assertEqual(status, 404)
        self.assertIn("error", response)

    def test_unknown_post_route_returns_404(self):
        """A POST to an unknown route should return 404 with JSON body."""
        data = json.dumps({"test": "data"}).encode("utf-8")
        status, response = self._make_request("POST", "/api/unknown", data)
        self.assertEqual(status, 404)
        self.assertIn("error", response)

    def test_head_request_sends_headers_no_body(self):
        """A HEAD request should return status but no body."""
        handler_class = build_handler(self.config)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        self.addCleanup(server.server_close)

        port = server.server_port

        def run_server():
            server.handle_request()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

        url = f"http://127.0.0.1:{port}/"
        request = Request(url, method="HEAD")

        response = urlopen(request)
        self.assertEqual(response.status, 200)
        # HEAD should not have a body, but headers should be sent
        self.assertIsNotNone(response.headers.get("Content-Type"))


class TestConcurrency(unittest.TestCase):
    """Test concurrent API calls with thread safety."""

    def setUp(self):
        """Create a temporary config with workspace."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.env_patch = mock.patch.dict(os.environ, {"TAPSCRIPT_WORKSPACE": str(self.workspace)})
        self.env_patch.start()
        self.config = Config(data={}, paths=Paths(project_root=None))

    def tearDown(self):
        """Clean up temp directory."""
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_concurrent_compile_calls_return_coherent_results(self):
        """Multiple concurrent compile calls should each return valid results."""
        api = Api(self.config)
        results = []
        errors = []

        def compile_in_thread(notation: str):
            try:
                result = api.compile({"content": notation})
                results.append(result)
            except Exception as exc:
                errors.append(exc)

        # Fire multiple threads compiling at the same time
        threads = []
        for _i in range(3):
            thread = threading.Thread(
                target=compile_in_thread,
                args=(MINIMAL_NOTATION,),
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All should complete without error
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(results), 3)

        # Each result should be coherent (have either error or ok+midi_url)
        for result in results:
            if "error" in result:
                self.assertNotIn("ok", result)
            else:
                self.assertTrue(result.get("ok"))
                self.assertIn("midi_url", result)


if __name__ == "__main__":
    unittest.main()
