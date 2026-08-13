"""JSON-RPC 2.0, as the Model Context Protocol speaks it.

One message per line of JSON, requests answered in place, notifications
answered with silence. Nothing here knows what a tool or a resource is: it
takes a method name, finds a handler, and turns whatever comes back into a
well-formed reply.

The distinction that matters is between a protocol error and a tool failure. A
malformed request is a protocol error and gets an error object. A tool that
could not do what was asked is a *result* -- the model has to read it and try
something else, and an error object would tell it the server is broken instead.
Only :class:`RpcError` produces the former.

A handler that raises anything else becomes ``-32603 internal error``, and the
loop carries on. A server that exits because one request was strange is a
server that loses the session.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

VERSION = "2.0"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

Handler = Callable[[dict[str, Any]], Any]


class RpcError(Exception):
    """A protocol-level failure, with the code the client should see."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def as_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        return error


def invalid_params(message: str, data: Any = None) -> RpcError:
    return RpcError(INVALID_PARAMS, message, data)


@dataclass
class Request:
    """One parsed call. ``id`` is ``None`` for a notification."""

    method: str
    params: dict[str, Any]
    id: Any = None
    is_notification: bool = False


def parse_message(payload: Any) -> Request:
    """Validate one decoded JSON-RPC object, or raise :class:`RpcError`."""
    if not isinstance(payload, dict):
        raise RpcError(INVALID_REQUEST, "a request must be a JSON object")
    if payload.get("jsonrpc") != VERSION:
        raise RpcError(INVALID_REQUEST, f"jsonrpc must be {VERSION!r}")
    method = payload.get("method")
    if not isinstance(method, str) or not method:
        raise RpcError(INVALID_REQUEST, "method must be a non-empty string")
    params = payload.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        # Positional parameters are legal JSON-RPC but MCP never uses them, and
        # accepting them would mean guessing at names.
        raise RpcError(INVALID_PARAMS, "params must be an object")
    identifier = payload.get("id")
    if identifier is not None and not isinstance(identifier, (str, int, float)):
        raise RpcError(INVALID_REQUEST, "id must be a string or a number")
    return Request(
        method=method,
        params=params,
        id=identifier,
        is_notification="id" not in payload or identifier is None,
    )


def success(identifier: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": VERSION, "id": identifier, "result": result}


def failure(identifier: Any, error: RpcError) -> dict[str, Any]:
    return {"jsonrpc": VERSION, "id": identifier, "error": error.as_dict()}


class Dispatcher:
    """Method name to handler, with the error handling written once."""

    def __init__(self) -> None:
        self.handlers: dict[str, Handler] = {}

    def register(self, method: str, handler: Handler) -> None:
        self.handlers[method] = handler

    def method_names(self) -> list[str]:
        return sorted(self.handlers)

    def handle(self, payload: Any) -> dict[str, Any] | None:
        """Answer one decoded message. ``None`` means "say nothing"."""
        try:
            request = parse_message(payload)
        except RpcError as error:
            identifier = payload.get("id") if isinstance(payload, dict) else None
            return None if identifier is None else failure(identifier, error)

        handler = self.handlers.get(request.method)
        if handler is None:
            if request.is_notification:
                return None  # an unknown notification is not ours to complain about
            return failure(
                request.id,
                RpcError(
                    METHOD_NOT_FOUND,
                    f"unknown method: {request.method}",
                    {"known": self.method_names()},
                ),
            )

        try:
            result = handler(request.params)
        except RpcError as error:
            return None if request.is_notification else failure(request.id, error)
        except Exception as exc:
            error = RpcError(INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")
            return None if request.is_notification else failure(request.id, error)

        if request.is_notification:
            return None
        return success(request.id, {} if result is None else result)

    def handle_text(self, line: str) -> str | None:
        """Answer one line of JSON. Returns the line to write back, or ``None``."""
        text = line.strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            return json.dumps(failure(None, RpcError(PARSE_ERROR, f"invalid JSON: {exc}")))

        if isinstance(payload, list):
            # Batches are legal JSON-RPC and harmless to support; MCP itself
            # stopped using them.
            if not payload:
                return json.dumps(failure(None, RpcError(INVALID_REQUEST, "empty batch")))
            answers = [answer for answer in (self.handle(item) for item in payload) if answer]
            return json.dumps(answers) if answers else None

        answer = self.handle(payload)
        return None if answer is None else json.dumps(answer)


def serve_stdio(dispatcher: Dispatcher, reader: Iterable[str], writer: Any) -> int:
    """Read newline-delimited messages from *reader*, write replies to *writer*.

    Flushed per message: a client that is waiting for a reply before sending the
    next request would otherwise wait forever behind a buffer.
    """
    for line in reader:
        answer = dispatcher.handle_text(line)
        if answer is None:
            continue
        writer.write(answer + "\n")
        writer.flush()
    return 0
