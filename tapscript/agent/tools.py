"""Tools the agent can call.

Every tool is a plain function with a JSON schema and a one-line description.
File access is confined to a sandbox root -- by default the workspace, so an
agent cannot touch the rest of the disk while it is iterating on a piece.

Tools return strings. A tool that fails returns a description of the failure
rather than raising, because the model needs to read the failure and try
something else; an exception would end the loop instead.
"""

from __future__ import annotations

import json
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..llm.types import ToolSpec
from ..perform import tools as perform_tools
from ..runtime.config import Config, load_config

MAX_READ_BYTES = 200_000
MAX_RESULT_CHARS = 20_000


class SandboxError(Exception):
    """A path was outside the sandbox."""


@dataclass
class Sandbox:
    """A directory an agent is allowed to work in."""

    root: Path
    extra_readable: list[Path] = field(default_factory=list)
    writable: bool = True

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.extra_readable = [Path(path).resolve() for path in self.extra_readable]

    def resolve(self, relative: str, for_write: bool = False) -> Path:
        candidate = Path(relative).expanduser()
        target = (candidate if candidate.is_absolute() else self.root / candidate).resolve()

        if target == self.root or self.root in target.parents:
            if for_write and not self.writable:
                raise SandboxError("this session is read-only")
            return target

        if not for_write:
            for readable in self.extra_readable:
                if target == readable or readable in target.parents:
                    return target

        raise SandboxError(
            f"{relative!r} is outside the working directory ({self.root}); "
            "use a relative path inside it"
        )

    def relative(self, path: Path) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.root))
        except ValueError:
            return str(path)


@dataclass
class Tool:
    """One callable tool."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., str]
    dangerous: bool = False

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, parameters=self.parameters)


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }


def _string(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


class ToolRegistry:
    """The set of tools available to one agent session."""

    def __init__(
        self,
        sandbox: Sandbox | None = None,
        config: Config | None = None,
        allow_dangerous: bool = False,
    ) -> None:
        self.config = config or load_config()
        self.sandbox = sandbox or Sandbox(
            root=self.config.paths.workspace,
            extra_readable=[p for p in [self.config.paths.project_root] if p],
        )
        self.allow_dangerous = allow_dangerous
        self.tools: dict[str, Tool] = {}
        self.journal: list[str] = []
        self._register_builtins()

    # -- registry ------------------------------------------------------------

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def add(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable[..., str],
        dangerous: bool = False,
    ) -> None:
        self.register(Tool(name, description, parameters, handler, dangerous))

    def specs(self) -> list[ToolSpec]:
        return [
            tool.spec()
            for tool in self.tools.values()
            if self.allow_dangerous or not tool.dangerous
        ]

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self.tools.get(name)
        if tool is None:
            available = ", ".join(sorted(self.tools))
            return f"error: no tool named {name!r}. Available tools: {available}"
        if tool.dangerous and not self.allow_dangerous:
            return f"error: {name} needs approval and this session is running unattended"
        try:
            result = tool.handler(**arguments)
        except TypeError as exc:
            return f"error: wrong arguments for {name}: {exc}"
        except SandboxError as exc:
            return f"error: {exc}"
        except Exception as exc:
            detail = traceback.format_exc(limit=3)
            return f"error: {name} failed: {type(exc).__name__}: {exc}\n{detail}"
        text = result if isinstance(result, str) else json.dumps(result, indent=2, default=str)
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + f"\n... (truncated, {len(text)} characters total)"
        return text

    # -- built-in tools ------------------------------------------------------

    def _register_builtins(self) -> None:
        self.add(
            "notation_reference",
            "Read the TapScript notation reference. Call this before writing notation for the "
            "first time in a session.",
            _schema({}),
            self._notation_reference,
        )
        self.add(
            "probe_host",
            "Report what this machine can do: platform, optional libraries, soundfonts, MIDI "
            "ports, audio playback, network. Use it before choosing how to render or connect.",
            _schema({}),
            self._probe_host,
        )
        self.add(
            "list_files",
            "List files in the working directory.",
            _schema({"path": _string("Directory relative to the working directory. Defaults to the root.")}),
            self._list_files,
        )
        self.add(
            "read_file",
            "Read a text file from the working directory or the project.",
            _schema({"path": _string("Path to read.")}, ["path"]),
            self._read_file,
        )
        self.add(
            "write_file",
            "Write a text file into the working directory, creating parent directories.",
            _schema(
                {
                    "path": _string("Path to write, relative to the working directory."),
                    "content": _string("Full file contents."),
                },
                ["path", "content"],
            ),
            self._write_file,
        )
        self.add(
            "write_score",
            "Write TapScript notation to a .tap file. The notation is parsed first and the "
            "result reports any problems, so use this rather than write_file for music.",
            _schema(
                {
                    "path": _string("File to write, ending in .tap"),
                    "content": _string("The notation."),
                },
                ["path", "content"],
            ),
            self._write_score,
        )
        self.add(
            "compile_score",
            "Compile notation to MIDI and audio, returning the arrangement summary and any "
            "diagnostics. Pass either a path or inline content.",
            _schema(
                {
                    "path": _string("A .tap file to compile."),
                    "content": _string("Notation to compile instead of a path."),
                    "audio": {
                        "type": "boolean",
                        "description": "Also render audio. Slower; off by default.",
                    },
                }
            ),
            self._compile_score,
        )
        self.add(
            "transpose_score",
            "Transpose a notation file to another key, writing the result next to it.",
            _schema(
                {
                    "path": _string("The .tap file to transpose."),
                    "key": _string("Target key, such as 'Dm' or 'F#'."),
                },
                ["path", "key"],
            ),
            self._transpose_score,
        )
        self.add(
            "search_library",
            "Search the bundled notation library for reference material by title, key or style.",
            _schema(
                {
                    "query": _string("What to look for."),
                    "limit": {"type": "integer", "description": "Maximum results (default 10)."},
                },
                ["query"],
            ),
            self._search_library,
        )
        self.add(
            "read_library",
            "Read one file from the bundled notation library, by name or title.",
            _schema({"name": _string("Library entry name or title.")}, ["name"]),
            self._read_library,
        )
        self.add(
            "verify_specs",
            "Run the project's specs and report what passes and what fails. Use this after "
            "making a change to check whether it worked.",
            _schema({"tag": _string("Only run specs carrying this tag.")}),
            self._verify_specs,
        )
        self.add(
            "record_decision",
            "Append a line to the build journal, recording a decision and why it was made.",
            _schema({"note": _string("What was decided and the reason.")}, ["note"]),
            self._record_decision,
        )
        perform_tools.register(self)

    # -- handlers ------------------------------------------------------------

    def _notation_reference(self) -> str:
        reference = Path(__file__).parent / "prompts" / "notation.md"
        try:
            return reference.read_text(encoding="utf-8")
        except OSError:
            return "error: the notation reference is missing from this install"

    def _probe_host(self) -> str:
        from ..runtime.capabilities import probe

        report = probe(refresh=True)
        lines = [report.summary(), ""]
        for capability in report:
            mark = "yes" if capability.present else "no "
            detail = f" -- {capability.detail}" if capability.detail else ""
            lines.append(f"[{mark}] {capability.name}{detail}")
            if not capability.present and capability.remedy:
                lines.append(f"      to enable: {capability.remedy}")
        return "\n".join(lines)

    def _list_files(self, path: str = ".") -> str:
        target = self.sandbox.resolve(path)
        if not target.exists():
            return f"error: {path} does not exist"
        if target.is_file():
            return f"{self.sandbox.relative(target)} ({target.stat().st_size} bytes)"
        rows = []
        for entry in sorted(target.iterdir()):
            if entry.name.startswith("."):
                continue
            marker = "/" if entry.is_dir() else ""
            size = "" if entry.is_dir() else f"  {entry.stat().st_size} bytes"
            rows.append(f"{self.sandbox.relative(entry)}{marker}{size}")
        return "\n".join(rows) if rows else "(empty)"

    def _read_file(self, path: str) -> str:
        target = self.sandbox.resolve(path)
        if not target.is_file():
            return f"error: {path} is not a file"
        if target.stat().st_size > MAX_READ_BYTES:
            return f"error: {path} is larger than {MAX_READ_BYTES} bytes"
        return target.read_text(encoding="utf-8", errors="replace")

    def _write_file(self, path: str, content: str) -> str:
        target = self.sandbox.resolve(path, for_write=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"wrote {self.sandbox.relative(target)} ({len(content)} characters)"

    def _write_score(self, path: str, content: str) -> str:
        from ..notation import arrange, parse

        if not path.endswith(".tap"):
            path = f"{path}.tap"
        score = parse(content)
        lines = []
        if score.has_errors:
            lines.append("not written -- the notation has errors:")
            lines.extend(f"  {diag.format()}" for diag in score.errors())
            return "\n".join(lines)

        target = self.sandbox.resolve(path, for_write=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        arrangement = arrange(score)
        lines.append(f"wrote {self.sandbox.relative(target)}")
        lines.append(json.dumps(score.summary()))
        lines.append(json.dumps(arrangement.summary()))
        if arrangement.note_count == 0:
            lines.append("warning: this arrangement contains no notes")
        for diag in score.warnings()[:8]:
            lines.append(f"  {diag.format()}")
        return "\n".join(lines)

    def _compile_score(self, path: str = "", content: str = "", audio: bool = False) -> str:
        from ..pipeline import compile_text

        if not content and not path:
            return "error: pass either a path or inline content"
        if path and not content:
            source = self.sandbox.resolve(path)
            if not source.is_file():
                return f"error: {path} does not exist"
            content = source.read_text(encoding="utf-8", errors="replace")
            stem = source.stem
        else:
            stem = "inline"

        output_dir = self.sandbox.resolve("output", for_write=True)
        result = compile_text(
            content,
            midi=output_dir / f"{stem}.mid",
            audio=(output_dir / f"{stem}.wav") if audio else None,
            config=self.config,
            path=path,
        )
        lines = [result.describe()]
        for message in result.messages:
            lines.append(f"note: {message}")
        problems = [diag for diag in result.diagnostics if diag.severity in ("error", "warning")]
        if problems:
            lines.append(f"{len(problems)} diagnostic(s):")
            lines.extend(f"  {diag.format()}" for diag in problems[:12])
        return "\n".join(lines)

    def _transpose_score(self, path: str, key: str) -> str:
        from ..transform import transpose

        source = self.sandbox.resolve(path)
        if not source.is_file():
            return f"error: {path} does not exist"
        moved = transpose(source.read_text(encoding="utf-8"), key)
        target = self.sandbox.resolve(
            f"{Path(path).stem}-{key.replace('#', 'sharp')}.tap", for_write=True
        )
        target.write_text(moved, encoding="utf-8")
        return f"wrote {self.sandbox.relative(target)}\n\n{moved[:1500]}"

    def _search_library(self, query: str, limit: int = 10) -> str:
        from ..library import Library

        entries = Library(paths=self.config.paths).search(query, limit=max(1, min(limit, 40)))
        if not entries:
            return f"nothing in the library matches {query!r}"
        return "\n".join(
            f"{entry.name}  --  {entry.title} [{entry.key or '?'}, {entry.tempo or '?'} bpm]  ({entry.collection})"
            for entry in entries
        )

    def _read_library(self, name: str) -> str:
        from ..library import Library

        entry = Library(paths=self.config.paths).find(name)
        if entry is None:
            return f"no library entry called {name!r}"
        return f"# {entry.path}\n\n{entry.read()}"

    def _verify_specs(self, tag: str = "") -> str:
        from ..specs import format_results, verify_all

        results = verify_all(paths=self.config.paths, tag=tag)
        if not results:
            return "no specs found"
        return format_results(results, verbose=False)

    def _record_decision(self, note: str) -> str:
        self.journal.append(note)
        journal_path = self.sandbox.resolve("BUILD-JOURNAL.md", for_write=True)
        existing = journal_path.read_text(encoding="utf-8") if journal_path.exists() else "# Build journal\n"
        journal_path.write_text(f"{existing.rstrip()}\n- {note}\n", encoding="utf-8")
        return f"recorded in {self.sandbox.relative(journal_path)}"
