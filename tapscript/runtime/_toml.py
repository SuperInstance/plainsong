"""A TOML reader for Python 3.10.

``tomllib`` arrived in the standard library in 3.11. This package supports 3.10
and refuses to take a dependency, so on 3.10 configuration would otherwise be
unreadable and the CLI would not even import.

This is a reader for the subset of TOML this project actually uses: tables,
arrays of tables, the four string forms, integers, floats, booleans, arrays and
inline tables. It does **not** implement dates, times, or dotted keys inside
inline tables. Anything it does not understand raises
:class:`TOMLDecodeError` with the line number rather than guessing, because a
configuration file that is silently misread is worse than one that fails loudly.

On 3.11 and later the real ``tomllib`` is used instead and this module is only
exercised by its own equivalence test, which parses every TOML file in the
repository with both and compares the results.
"""

from __future__ import annotations

from typing import Any, BinaryIO

__all__ = ["TOMLDecodeError", "load", "loads"]

BARE_KEY_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")

ESCAPES = {
    '"': '"', "\\": "\\", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
}


class TOMLDecodeError(ValueError):
    """Raised when the document is not valid TOML this reader understands."""


class _Reader:
    """A cursor over the document text."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.index = 0
        self.length = len(text)

    # -- position ------------------------------------------------------------

    @property
    def line(self) -> int:
        return self.text.count("\n", 0, self.index) + 1

    def fail(self, message: str) -> TOMLDecodeError:
        return TOMLDecodeError(f"line {self.line}: {message}")

    def peek(self, offset: int = 0) -> str:
        position = self.index + offset
        return self.text[position] if position < self.length else ""

    def starts_with(self, prefix: str) -> bool:
        return self.text.startswith(prefix, self.index)

    def eat(self, prefix: str) -> bool:
        if self.starts_with(prefix):
            self.index += len(prefix)
            return True
        return False

    # -- whitespace ----------------------------------------------------------

    def skip_inline(self) -> None:
        """Spaces, tabs and a trailing comment, but not the newline."""
        while self.index < self.length:
            char = self.text[self.index]
            if char in " \t":
                self.index += 1
            elif char == "#":
                while self.index < self.length and self.text[self.index] != "\n":
                    self.index += 1
            else:
                return

    def skip_blank(self) -> None:
        """Everything with no meaning: whitespace, newlines and comments."""
        while self.index < self.length:
            char = self.text[self.index]
            if char in " \t\r\n":
                self.index += 1
            elif char == "#":
                while self.index < self.length and self.text[self.index] != "\n":
                    self.index += 1
            else:
                return

    def require_newline(self) -> None:
        self.skip_inline()
        if self.index >= self.length:
            return
        if self.text[self.index] == "\r":
            self.index += 1
        if self.index < self.length:
            if self.text[self.index] != "\n":
                raise self.fail(f"unexpected {self.text[self.index]!r} after a value")
            self.index += 1

    # -- keys ----------------------------------------------------------------

    def read_key(self) -> list[str]:
        """A key, possibly dotted. Returns the path as a list of parts."""
        parts: list[str] = []
        while True:
            self.skip_inline()
            char = self.peek()
            if char in "\"'":
                parts.append(self.read_string())
            else:
                start = self.index
                while self.index < self.length and self.text[self.index] in BARE_KEY_CHARS:
                    self.index += 1
                if self.index == start:
                    raise self.fail("expected a key")
                parts.append(self.text[start : self.index])
            self.skip_inline()
            if not self.eat("."):
                return parts

    # -- values --------------------------------------------------------------

    def read_string(self) -> str:
        if self.eat('"""'):
            return self._read_multiline('"""', escaped=True)
        if self.eat("'''"):
            return self._read_multiline("'''", escaped=False)
        if self.eat('"'):
            return self._read_basic()
        if self.eat("'"):
            end = self.text.find("'", self.index)
            if end == -1:
                raise self.fail("unterminated literal string")
            value = self.text[self.index : end]
            self.index = end + 1
            return value
        raise self.fail("expected a string")

    def _read_basic(self) -> str:
        out: list[str] = []
        while True:
            if self.index >= self.length:
                raise self.fail("unterminated string")
            char = self.text[self.index]
            if char == '"':
                self.index += 1
                return "".join(out)
            if char == "\n":
                raise self.fail("unterminated string")
            if char == "\\":
                self.index += 1
                out.append(self._read_escape())
                continue
            out.append(char)
            self.index += 1

    def _read_escape(self) -> str:
        char = self.peek()
        if char in ESCAPES:
            self.index += 1
            return ESCAPES[char]
        if char in "uU":
            width = 4 if char == "u" else 8
            self.index += 1
            digits = self.text[self.index : self.index + width]
            if len(digits) < width:
                raise self.fail("truncated unicode escape")
            try:
                code = int(digits, 16)
            except ValueError as exc:
                raise self.fail(f"bad unicode escape {digits!r}") from exc
            self.index += width
            return chr(code)
        raise self.fail(f"unknown escape \\{char}")

    def _read_multiline(self, quote: str, escaped: bool) -> str:
        # A newline immediately after the opening delimiter is not content.
        if self.starts_with("\r\n"):
            self.index += 2
        elif self.peek() == "\n":
            self.index += 1

        out: list[str] = []
        while True:
            if self.index >= self.length:
                raise self.fail("unterminated multi-line string")
            if self.starts_with(quote):
                self.index += len(quote)
                # TOML allows up to two extra quotes before the delimiter.
                extra = 0
                while extra < 2 and self.peek() == quote[0]:
                    out.append(quote[0])
                    self.index += 1
                    extra += 1
                return "".join(out)
            char = self.text[self.index]
            if escaped and char == "\\":
                nxt = self.peek(1)
                if nxt == "\n" or (nxt == "\r" and self.peek(2) == "\n"):
                    # Line-ending backslash swallows the newline and any
                    # leading whitespace on the next line.
                    self.index += 1
                    while self.index < self.length and self.text[self.index] in " \t\r\n":
                        self.index += 1
                    continue
                self.index += 1
                out.append(self._read_escape())
                continue
            out.append(char)
            self.index += 1

    def read_value(self) -> Any:
        self.skip_inline()
        char = self.peek()
        if char in "\"'":
            return self.read_string()
        if char == "[":
            return self._read_array()
        if char == "{":
            return self._read_inline_table()
        if self.starts_with("true"):
            self.index += 4
            return True
        if self.starts_with("false"):
            self.index += 5
            return False
        return self._read_number()

    def _read_array(self) -> list[Any]:
        self.index += 1  # consume [
        values: list[Any] = []
        while True:
            self.skip_blank()
            if self.index >= self.length:
                raise self.fail("unterminated array")
            if self.eat("]"):
                return values
            values.append(self.read_value())
            self.skip_blank()
            if self.eat(","):
                continue
            self.skip_blank()
            if self.eat("]"):
                return values
            raise self.fail("expected ',' or ']' in array")

    def _read_inline_table(self) -> dict[str, Any]:
        self.index += 1  # consume {
        table: dict[str, Any] = {}
        self.skip_inline()
        if self.eat("}"):
            return table
        while True:
            path = self.read_key()
            if len(path) != 1:
                raise self.fail("dotted keys inside inline tables are not supported")
            self.skip_inline()
            if not self.eat("="):
                raise self.fail("expected '=' in inline table")
            table[path[0]] = self.read_value()
            self.skip_inline()
            if self.eat(","):
                self.skip_inline()
                continue
            if self.eat("}"):
                return table
            raise self.fail("expected ',' or '}' in inline table")

    def _read_number(self) -> Any:
        start = self.index
        while self.index < self.length and self.text[self.index] not in ",]}\n\r#":
            self.index += 1
        raw = self.text[start : self.index].strip()
        if not raw:
            raise self.fail("expected a value")
        if any(char in raw for char in ":") or raw.count("-") > 1:
            # Dates and times parse as neither int nor float; say so clearly
            # rather than returning a string that looks almost right.
            raise self.fail(f"unsupported value {raw!r} (dates and times are not implemented)")
        cleaned = raw.replace("_", "")
        try:
            if any(char in cleaned for char in ".eE") and not cleaned.lower().startswith("0x"):
                return float(cleaned)
            if cleaned.lower().startswith(("0x", "-0x", "+0x")):
                return int(cleaned, 16)
            if cleaned.lower().startswith(("0o", "-0o", "+0o")):
                return int(cleaned, 8)
            if cleaned.lower().startswith(("0b", "-0b", "+0b")):
                return int(cleaned, 2)
            if cleaned in ("inf", "+inf", "-inf", "nan", "+nan", "-nan"):
                return float(cleaned)
            return int(cleaned)
        except ValueError as exc:
            raise self.fail(f"could not read {raw!r} as a value") from exc


def _descend(root: dict[str, Any], path: list[str], reader: _Reader) -> dict[str, Any]:
    """Walk to the table at *path*, creating tables on the way."""
    node: Any = root
    for part in path:
        existing = node.get(part)
        if existing is None:
            existing = {}
            node[part] = existing
        elif isinstance(existing, list):
            if not existing or not isinstance(existing[-1], dict):
                raise reader.fail(f"cannot descend into {part!r}")
            existing = existing[-1]
        elif not isinstance(existing, dict):
            raise reader.fail(f"cannot redefine {part!r}")
        node = existing
    return node


def loads(text: str) -> dict[str, Any]:
    """Parse a TOML document from a string."""
    if text.startswith("﻿"):
        text = text[1:]
    reader = _Reader(text.replace("\r\n", "\n"))
    root: dict[str, Any] = {}
    current = root

    while True:
        reader.skip_blank()
        if reader.index >= reader.length:
            return root

        if reader.starts_with("[["):
            reader.index += 2
            path = reader.read_key()
            reader.skip_inline()
            if not reader.eat("]]"):
                raise reader.fail("expected ']]'")
            parent = _descend(root, path[:-1], reader)
            name = path[-1]
            bucket = parent.setdefault(name, [])
            if not isinstance(bucket, list):
                raise reader.fail(f"{name!r} is already a table, not an array of tables")
            current = {}
            bucket.append(current)
            reader.require_newline()
            continue

        if reader.peek() == "[":
            reader.index += 1
            path = reader.read_key()
            reader.skip_inline()
            if not reader.eat("]"):
                raise reader.fail("expected ']'")
            current = _descend(root, path, reader)
            reader.require_newline()
            continue

        path = reader.read_key()
        reader.skip_inline()
        if not reader.eat("="):
            raise reader.fail("expected '=' after a key")
        value = reader.read_value()
        target = _descend(current, path[:-1], reader)
        if path[-1] in target:
            raise reader.fail(f"{path[-1]!r} is defined twice")
        target[path[-1]] = value
        reader.require_newline()


def load(handle: BinaryIO) -> dict[str, Any]:
    """Parse a TOML document from a binary file, as ``tomllib.load`` does."""
    data = handle.read()
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return loads(data)
