"""HTTP for provider adapters.

``urllib`` from the standard library, with retries, timeouts and server-sent
event parsing. No ``requests``, no ``httpx`` -- a fresh clone can talk to a
model API without installing anything.

Proxy settings are picked up from the usual environment variables because
``urllib`` honours them natively.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

from .types import ProviderError

USER_AGENT = "plainsong/1.0 (+https://github.com/SuperInstance/plainsong)"

RETRY_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504, 529}


def _classify(status: int, body: str, provider: str) -> ProviderError:
    hint = ""
    if status in (401, 403):
        hint = f"check the API key for {provider} (`plainsong providers --check`)"
    elif status == 404:
        hint = "the model name may not exist for this provider (`plainsong providers --models`)"
    elif status == 429:
        hint = "rate limited -- the request will be retried, or try a smaller model"
    elif status >= 500:
        hint = "the provider is having trouble; this will be retried"
    message = body.strip()
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            error = parsed.get("error")
            if isinstance(error, dict):
                message = error.get("message") or message
            elif isinstance(error, str):
                message = error
            elif "message" in parsed:
                message = str(parsed["message"])
    except (json.JSONDecodeError, TypeError):
        pass
    return ProviderError(
        f"HTTP {status}: {message[:500]}",
        provider=provider,
        status=status,
        retryable=status in RETRY_STATUSES,
        hint=hint,
    )


def request_json(
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    method: str = "POST",
    timeout: int = 120,
    max_retries: int = 3,
    provider: str = "",
) -> dict[str, Any]:
    """Make a JSON request and return the decoded body."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    all_headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT, **(headers or {})}
    last_error: ProviderError | None = None

    for attempt in range(max_retries + 1):
        request = urllib.request.Request(url, data=body, headers=all_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            error = _classify(exc.code, detail, provider)
            last_error = error
            if not error.retryable or attempt == max_retries:
                raise error from exc
        except urllib.error.URLError as exc:
            last_error = ProviderError(
                f"could not reach {url}: {exc.reason}",
                provider=provider,
                retryable=True,
                hint="check network access, or use a local provider such as ollama",
            )
            if attempt == max_retries:
                raise last_error from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"provider returned a response that is not JSON: {exc}", provider=provider
            ) from exc
        except TimeoutError as exc:
            last_error = ProviderError(
                f"request timed out after {timeout}s", provider=provider, retryable=True
            )
            if attempt == max_retries:
                raise last_error from exc

        # Exponential backoff with jitter, so parallel agents do not sync up.
        time.sleep(min(2**attempt + random.random(), 20.0))

    raise last_error or ProviderError("request failed", provider=provider)


def request_stream(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: int = 300,
    provider: str = "",
) -> Iterator[dict[str, Any]]:
    """Yield decoded server-sent events from a streaming endpoint."""
    body = json.dumps(payload).encode("utf-8")
    all_headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "User-Agent": USER_AGENT,
        **(headers or {}),
    }
    request = urllib.request.Request(url, data=body, headers=all_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    continue
    except urllib.error.HTTPError as exc:
        raise _classify(exc.code, exc.read().decode("utf-8", errors="replace"), provider) from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"could not reach {url}: {exc.reason}", provider=provider, retryable=True) from exc
