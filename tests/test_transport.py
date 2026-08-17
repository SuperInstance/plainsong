"""HTTP transport with retries, backoff, error classification, and streaming.

Tests for the urllib-based request layer that handles provider adapters,
server-sent events, retries with exponential backoff, and error classification.
"""

from __future__ import annotations

import io
import json
import unittest
import urllib.error
from unittest import mock

from plainsong.llm.transport import (
    USER_AGENT,
    _classify,
    request_json,
    request_stream,
)
from plainsong.llm.types import ProviderError


class TestClassify(unittest.TestCase):
    """Error classification: status codes, hints, retryability, message extraction."""

    def test_classify_401_has_api_key_hint(self):
        """Status 401 should suggest checking the API key."""
        error = _classify(401, "Unauthorized", "openai")
        self.assertIn("API key", error.hint)
        self.assertIn("openai", error.hint)
        self.assertIn("401", str(error))
        self.assertFalse(error.retryable)

    def test_classify_403_has_api_key_hint(self):
        """Status 403 should suggest checking the API key."""
        error = _classify(403, "Forbidden", "anthropic")
        self.assertIn("API key", error.hint)
        self.assertIn("anthropic", error.hint)
        self.assertFalse(error.retryable)

    def test_classify_404_has_model_name_hint(self):
        """Status 404 should suggest checking the model name."""
        error = _classify(404, "Not found", "gemini")
        self.assertIn("model name", error.hint)
        self.assertFalse(error.retryable)

    def test_classify_429_is_retryable(self):
        """Status 429 should be marked retryable and hint to retry."""
        error = _classify(429, "Rate limited", "openai")
        self.assertTrue(error.retryable)
        self.assertIn("rate limited", error.hint.lower())

    def test_classify_500_is_retryable(self):
        """Status 500 should be marked retryable and mention retry."""
        error = _classify(500, "Internal server error", "anthropic")
        self.assertTrue(error.retryable)
        self.assertIn("retried", error.hint.lower())

    def test_classify_400_is_not_retryable(self):
        """Status 400 should not be retryable."""
        error = _classify(400, "Bad request", "openai")
        self.assertFalse(error.retryable)
        self.assertNotIn("retried", error.hint.lower())

    def test_classify_extracts_nested_error_message(self):
        """Extract message from {"error": {"message": "x"}}."""
        body = json.dumps({"error": {"message": "API quota exceeded"}})
        error = _classify(429, body, "openai")
        self.assertIn("API quota exceeded", str(error))

    def test_classify_extracts_error_string(self):
        """Extract message from {"error": "x"}."""
        body = json.dumps({"error": "Invalid token"})
        error = _classify(401, body, "anthropic")
        self.assertIn("Invalid token", str(error))

    def test_classify_extracts_message_key(self):
        """Extract message from {"message": "x"}."""
        body = json.dumps({"message": "Something went wrong"})
        error = _classify(500, body, "openai")
        self.assertIn("Something went wrong", str(error))

    def test_classify_falls_back_to_raw_body_on_non_json(self):
        """Non-JSON body is used as-is after stripping."""
        error = _classify(500, "  Plain text error  ", "openai")
        self.assertIn("Plain text error", str(error))

    def test_classify_truncates_very_long_message_to_500_chars(self):
        """Messages longer than 500 chars are truncated to 500 in the error message."""
        long_message = "x" * 1000
        error = _classify(500, long_message, "openai")
        # The message part inside ProviderError should be truncated to 500 chars
        # The full string representation includes provider and hint, so check args[0]
        base_message = error.args[0]
        # "HTTP 500: " is 10 chars + 500 truncated message = 510 max
        self.assertLessEqual(len(base_message), 520)
        self.assertIn("xxx", base_message)  # Should contain many x's but not all 1000

    def test_classify_retryable_statuses_match_retry_statuses_constant(self):
        """Retryable classification matches RETRY_STATUSES."""
        for status in [408, 409, 425, 429, 500, 502, 503, 504, 529]:
            error = _classify(status, "error", "test")
            self.assertTrue(error.retryable, f"Status {status} should be retryable")

    def test_classify_non_retryable_statuses(self):
        """Non-retry statuses are not marked retryable."""
        for status in [400, 401, 403, 404]:
            error = _classify(status, "error", "test")
            self.assertFalse(error.retryable, f"Status {status} should not be retryable")


class TestRequestJSON(unittest.TestCase):
    """JSON request function: happy path, headers, empty responses, retries, backoff."""

    def _mock_urlopen(self, status: int = 200, body: str = "", exc=None):
        """Helper to create a mock urlopen that returns an HTTPResponse."""
        if exc:
            raise exc
        response = mock.MagicMock()
        response.read.return_value = body.encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = None
        return response

    def test_request_json_happy_path_returns_decoded_dict(self):
        """Successful request returns decoded JSON dict."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            response_body = json.dumps({"id": "123", "text": "hello"})
            mock_urlopen.return_value = self._mock_urlopen(body=response_body)
            result = request_json("https://api.example.com/chat", {"prompt": "hi"})
            self.assertEqual(result, {"id": "123", "text": "hello"})

    def test_request_json_empty_response_returns_empty_dict(self):
        """Empty response body returns {} rather than raising."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._mock_urlopen(body="")
            result = request_json("https://api.example.com/chat")
            self.assertEqual(result, {})

    def test_request_json_sends_user_agent_header(self):
        """Request includes the User-Agent header."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._mock_urlopen(body="{}")
            request_json("https://api.example.com/chat", {"prompt": "hi"})
            call_args = mock_urlopen.call_args
            request_obj = call_args[0][0]
            self.assertEqual(request_obj.headers["User-agent"], USER_AGENT)

    def test_request_json_sends_content_type_application_json(self):
        """Request includes Content-Type: application/json."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._mock_urlopen(body="{}")
            request_json("https://api.example.com/chat", {"prompt": "hi"})
            call_args = mock_urlopen.call_args
            request_obj = call_args[0][0]
            self.assertEqual(request_obj.headers["Content-type"], "application/json")

    def test_request_json_merges_caller_headers_over_defaults(self):
        """Caller-provided headers override defaults."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._mock_urlopen(body="{}")
            request_json(
                "https://api.example.com/chat",
                {"prompt": "hi"},
                headers={"Authorization": "Bearer token123", "X-Custom": "value"},
            )
            call_args = mock_urlopen.call_args
            request_obj = call_args[0][0]
            self.assertEqual(request_obj.headers["Authorization"], "Bearer token123")
            self.assertEqual(request_obj.headers["X-custom"], "value")
            # Defaults should still be present
            self.assertEqual(request_obj.headers["User-agent"], USER_AGENT)

    def test_request_json_500_then_200_returns_good_result(self):
        """Retries on 500 and returns the successful response."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            with mock.patch("plainsong.llm.transport.time.sleep"):
                # First call raises 500, second call succeeds
                exc = urllib.error.HTTPError("url", 500, "error", {}, io.BytesIO(b"Server error"))
                mock_urlopen.side_effect = [
                    exc,
                    self._mock_urlopen(body='{"result": "success"}'),
                ]
                result = request_json("https://api.example.com/chat", max_retries=3)
                self.assertEqual(result, {"result": "success"})
                self.assertEqual(mock_urlopen.call_count, 2)

    def test_request_json_400_raises_immediately_no_retry(self):
        """Non-retryable 400 error raises immediately without retry."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            exc = urllib.error.HTTPError("url", 400, "error", {}, io.BytesIO(b"Bad request"))
            mock_urlopen.side_effect = exc
            with self.assertRaises(ProviderError) as caught:
                request_json("https://api.example.com/chat")
            self.assertEqual(mock_urlopen.call_count, 1)
            self.assertFalse(caught.exception.retryable)

    def test_request_json_500_every_time_raises_after_max_retries_plus_one_attempts(self):
        """All retries fail, raises after exactly max_retries + 1 attempts."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            with mock.patch("plainsong.llm.transport.time.sleep"):
                exc = urllib.error.HTTPError("url", 500, "error", {}, io.BytesIO(b"Always fails"))
                mock_urlopen.side_effect = exc
                max_retries = 2
                with self.assertRaises(ProviderError):
                    request_json("https://api.example.com/chat", max_retries=max_retries)
                # Should try once, then retry 2 times = 3 total
                self.assertEqual(mock_urlopen.call_count, max_retries + 1)

    def test_request_json_max_retries_zero_makes_exactly_one_attempt(self):
        """With max_retries=0, exactly one attempt is made."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            exc = urllib.error.HTTPError("url", 500, "error", {}, io.BytesIO(b"Fail"))
            mock_urlopen.side_effect = exc
            with self.assertRaises(ProviderError):
                request_json("https://api.example.com/chat", max_retries=0)
            self.assertEqual(mock_urlopen.call_count, 1)

    def test_request_json_urlerror_retries_and_mentions_url(self):
        """URLError is retryable; final error mentions the URL."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            with mock.patch("plainsong.llm.transport.time.sleep"):
                url = "https://api.example.com/chat"
                exc = urllib.error.URLError("Connection refused")
                mock_urlopen.side_effect = exc
                with self.assertRaises(ProviderError) as caught:
                    request_json(url, max_retries=1)
                self.assertTrue(caught.exception.retryable)
                self.assertIn(url, str(caught.exception))

    def test_request_json_timeouterror_retries_and_names_timeout(self):
        """TimeoutError is retryable; error mentions the timeout value."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            with mock.patch("plainsong.llm.transport.time.sleep"):
                timeout_val = 45
                mock_urlopen.side_effect = TimeoutError("timed out")
                with self.assertRaises(ProviderError) as caught:
                    request_json("https://api.example.com/chat", timeout=timeout_val, max_retries=1)
                self.assertTrue(caught.exception.retryable)
                self.assertIn(str(timeout_val), str(caught.exception))

    def test_request_json_non_json_response_raises_provider_error(self):
        """Response that is valid HTTP but not JSON raises ProviderError."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._mock_urlopen(body="<html>Not JSON</html>")
            with self.assertRaises(ProviderError) as caught:
                request_json("https://api.example.com/chat")
            self.assertIn("not JSON", str(caught.exception))


class TestBackoff(unittest.TestCase):
    """Exponential backoff with jitter: timing, no sleep after final failure."""

    def test_backoff_attempt_0_sleeps_between_1_and_2_seconds(self):
        """First retry sleeps min(2^0 + random, 20) = [1, 2)."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            with mock.patch("plainsong.llm.transport.time.sleep") as mock_sleep:
                with mock.patch("plainsong.llm.transport.random.random", return_value=0.5):
                    exc = urllib.error.HTTPError("url", 500, "error", {}, io.BytesIO(b"fail"))
                    mock_urlopen.side_effect = [
                        exc,
                        self._mock_urlopen(body="{}"),
                    ]
                    request_json("https://api.example.com/chat", max_retries=1)
                    # After first attempt (index 0), sleep should be called with 1 + 0.5 = 1.5
                    mock_sleep.assert_called_once()
                    sleep_arg = mock_sleep.call_args[0][0]
                    self.assertGreaterEqual(sleep_arg, 1.0)
                    self.assertLess(sleep_arg, 2.0)

    def test_backoff_attempt_1_sleeps_between_2_and_3_seconds(self):
        """Second retry sleeps min(2^1 + random, 20) = [2, 3)."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            with mock.patch("plainsong.llm.transport.time.sleep") as mock_sleep:
                with mock.patch("plainsong.llm.transport.random.random", return_value=0.5):
                    exc = urllib.error.HTTPError("url", 500, "error", {}, io.BytesIO(b"fail"))
                    mock_urlopen.side_effect = [exc, exc, self._mock_urlopen(body="{}")]
                    request_json("https://api.example.com/chat", max_retries=2)
                    # Should have called sleep twice
                    self.assertEqual(mock_sleep.call_count, 2)
                    # Second call should be [2, 3)
                    second_sleep_arg = mock_sleep.call_args_list[1][0][0]
                    self.assertGreaterEqual(second_sleep_arg, 2.0)
                    self.assertLess(second_sleep_arg, 3.0)

    def test_backoff_attempt_2_sleeps_between_4_and_5_seconds(self):
        """Third retry sleeps min(2^2 + random, 20) = [4, 5)."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            with mock.patch("plainsong.llm.transport.time.sleep") as mock_sleep:
                with mock.patch("plainsong.llm.transport.random.random", return_value=0.3):
                    exc = urllib.error.HTTPError("url", 500, "error", {}, io.BytesIO(b"fail"))
                    mock_urlopen.side_effect = [exc, exc, exc, self._mock_urlopen(body="{}")]
                    request_json("https://api.example.com/chat", max_retries=3)
                    # Third call should be [4, 5)
                    third_sleep_arg = mock_sleep.call_args_list[2][0][0]
                    self.assertGreaterEqual(third_sleep_arg, 4.0)
                    self.assertLess(third_sleep_arg, 5.0)

    def test_backoff_not_called_after_final_failed_attempt(self):
        """No sleep is called after the last failed attempt."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            with mock.patch("plainsong.llm.transport.time.sleep") as mock_sleep:
                exc = urllib.error.HTTPError("url", 500, "error", {}, io.BytesIO(b"fail"))
                mock_urlopen.side_effect = exc
                max_retries = 2
                with self.assertRaises(ProviderError):
                    request_json("https://api.example.com/chat", max_retries=max_retries)
                # With 3 total attempts (0, 1, 2), sleep is called 2 times (after 0 and 1)
                self.assertEqual(mock_sleep.call_count, max_retries)

    def _mock_urlopen(self, status: int = 200, body: str = "", exc=None):
        """Helper to create a mock urlopen that returns an HTTPResponse."""
        if exc:
            raise exc
        response = mock.MagicMock()
        response.read.return_value = body.encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = None
        return response


class TestRequestStream(unittest.TestCase):
    """Server-sent event parsing: data: lines, skipping, [DONE], malformed JSON."""

    def test_request_stream_parses_data_lines(self):
        """Parses lines starting with 'data:' as JSON."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            lines = [
                b'data: {"id": "1", "text": "hello"}\n',
                b'data: {"id": "2", "text": "world"}\n',
            ]
            response = mock.MagicMock()
            response.__iter__.return_value = iter(lines)
            response.__enter__.return_value = response
            response.__exit__.return_value = None
            mock_urlopen.return_value = response
            events = list(request_stream("https://api.example.com/stream", {"prompt": "hi"}))
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["id"], "1")
            self.assertEqual(events[1]["text"], "world")

    def test_request_stream_skips_blank_lines(self):
        """Blank lines are skipped."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            lines = [
                b'data: {"id": "1"}\n',
                b'\n',
                b'  \n',
                b'data: {"id": "2"}\n',
            ]
            response = mock.MagicMock()
            response.__iter__.return_value = iter(lines)
            response.__enter__.return_value = response
            response.__exit__.return_value = None
            mock_urlopen.return_value = response
            events = list(request_stream("https://api.example.com/stream", {"prompt": "hi"}))
            self.assertEqual(len(events), 2)

    def test_request_stream_skips_comment_lines_starting_with_colon(self):
        """Lines starting with ':' are skipped."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            lines = [
                b'data: {"id": "1"}\n',
                b': this is a comment\n',
                b'::: another comment\n',
                b'data: {"id": "2"}\n',
            ]
            response = mock.MagicMock()
            response.__iter__.return_value = iter(lines)
            response.__enter__.return_value = response
            response.__exit__.return_value = None
            mock_urlopen.return_value = response
            events = list(request_stream("https://api.example.com/stream", {"prompt": "hi"}))
            self.assertEqual(len(events), 2)

    def test_request_stream_skips_lines_without_data_prefix(self):
        """Lines without 'data:' prefix are skipped."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            lines = [
                b'data: {"id": "1"}\n',
                b'event: message\n',
                b'id: 123\n',
                b'data: {"id": "2"}\n',
            ]
            response = mock.MagicMock()
            response.__iter__.return_value = iter(lines)
            response.__enter__.return_value = response
            response.__exit__.return_value = None
            mock_urlopen.return_value = response
            events = list(request_stream("https://api.example.com/stream", {"prompt": "hi"}))
            self.assertEqual(len(events), 2)

    def test_request_stream_stops_at_done_marker(self):
        """Stream stops when [DONE] marker is encountered."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            lines = [
                b'data: {"id": "1"}\n',
                b'data: {"id": "2"}\n',
                b'data: [DONE]\n',
                b'data: {"id": "3"}\n',  # Should not be yielded
            ]
            response = mock.MagicMock()
            response.__iter__.return_value = iter(lines)
            response.__enter__.return_value = response
            response.__exit__.return_value = None
            mock_urlopen.return_value = response
            events = list(request_stream("https://api.example.com/stream", {"prompt": "hi"}))
            self.assertEqual(len(events), 2)
            self.assertEqual(events[-1]["id"], "2")

    def test_request_stream_skips_malformed_json_lines(self):
        """Malformed JSON lines are skipped, not raised."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            lines = [
                b'data: {"id": "1"}\n',
                b'data: {not valid json}\n',
                b'data: {"id": "2"}\n',
            ]
            response = mock.MagicMock()
            response.__iter__.return_value = iter(lines)
            response.__enter__.return_value = response
            response.__exit__.return_value = None
            mock_urlopen.return_value = response
            events = list(request_stream("https://api.example.com/stream", {"prompt": "hi"}))
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["id"], "1")
            self.assertEqual(events[1]["id"], "2")

    def test_request_stream_sets_accept_text_event_stream_header(self):
        """Request includes Accept: text/event-stream header."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            response = mock.MagicMock()
            response.__iter__.return_value = iter([])
            response.__enter__.return_value = response
            response.__exit__.return_value = None
            mock_urlopen.return_value = response
            list(request_stream("https://api.example.com/stream", {"prompt": "hi"}))
            call_args = mock_urlopen.call_args
            request_obj = call_args[0][0]
            self.assertEqual(request_obj.headers["Accept"], "text/event-stream")

    def test_request_stream_converts_httperror_to_classified_provider_error(self):
        """HTTPError is converted to a classified ProviderError."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            exc = urllib.error.HTTPError(
                "url", 401, "error", {}, io.BytesIO(b'{"error": {"message": "Invalid key"}}')
            )
            mock_urlopen.side_effect = exc
            with self.assertRaises(ProviderError) as caught:
                list(request_stream("https://api.example.com/stream", {"prompt": "hi"}))
            self.assertEqual(caught.exception.status, 401)
            self.assertIn("Invalid key", str(caught.exception))

    def test_request_stream_converts_urlerror_to_provider_error(self):
        """URLError is converted to a retryable ProviderError."""
        with mock.patch("plainsong.llm.transport.urllib.request.urlopen") as mock_urlopen:
            exc = urllib.error.URLError("Connection refused")
            mock_urlopen.side_effect = exc
            with self.assertRaises(ProviderError) as caught:
                list(request_stream("https://api.example.com/stream", {"prompt": "hi"}))
            self.assertTrue(caught.exception.retryable)
            self.assertIn("could not reach", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
