"""The terminal interface.

A browser for the library and a control panel for the compiler: pick a piece,
see what it is, compile it, play it, hand it to the agent. Built on ``curses``
from the standard library, so it runs over ssh and inside tmux without
installing anything.

It is deliberately not a text editor. Editing happens in your editor; this is
for moving between pieces and hearing them.
"""

from __future__ import annotations

import threading
from typing import Any

from ..runtime.config import Config, load_config

HELP = [
    ("up/down, j/k", "move"),
    ("pgup/pgdn", "page"),
    ("enter", "load the highlighted piece"),
    ("/", "filter the library"),
    ("c", "compile to MIDI"),
    ("w", "compile to audio"),
    ("p", "play"),
    ("t", "transpose"),
    ("a", "ask the agent"),
    ("r", "refresh the library"),
    ("?", "this help"),
    ("q", "quit"),
]


def check_importable() -> tuple[bool, str]:
    """Spec check: the TUI can be loaded and has a terminal library."""
    try:
        import curses  # noqa: F401
    except ImportError as exc:
        return False, f"curses is unavailable: {exc}"
    return True, "curses available"


class TuiState:
    """Everything the screen draws from."""

    def __init__(self, config: Config) -> None:
        from ..library import Library

        self.config = config
        self.library = Library(paths=config.paths)
        self.filter = ""
        self.entries = self.library.entries(limit=0)
        self.selected = 0
        self.offset = 0
        self.status = "ready"
        self.busy = False
        self.detail: dict[str, Any] = {}
        self.preview: list[str] = []
        self.message_lines: list[str] = []

    def visible(self) -> list:
        if not self.filter:
            return self.entries
        return self.library.search(self.filter, limit=500)

    def current(self):
        items = self.visible()
        if not items:
            return None
        return items[min(self.selected, len(items) - 1)]

    def load_current(self) -> None:
        entry = self.current()
        if entry is None:
            return
        from ..transform import describe

        try:
            text = entry.read()
        except OSError as exc:
            self.status = f"could not read {entry.name}: {exc}"
            return
        self.preview = text.splitlines()[:400]
        try:
            self.detail = describe(text)
            arrangement = self.detail.get("arrangement", {})
            self.status = (
                f"{self.detail['title']} -- {self.detail['key']}, {self.detail['tempo']:g} bpm, "
                f"{arrangement.get('notes', 0)} notes"
            )
        except Exception as exc:
            self.detail = {}
            self.status = f"could not read the notation: {exc}"


def run_tui(config: Config | None = None, path: str = "") -> int:
    """Start the terminal interface."""
    try:
        import curses
    except ImportError:
        print("The terminal interface needs the curses module, which is not available here.")
        print("Use `tapscript serve` for the web interface instead.")
        return 1

    config = config or load_config()
    state = TuiState(config)

    if path:
        entry = state.library.find(path)
        if entry is not None:
            visible = state.visible()
            if entry in visible:
                state.selected = visible.index(entry)
            state.load_current()

    try:
        return curses.wrapper(_main_loop, state)
    except KeyboardInterrupt:
        return 130


def _main_loop(screen, state: TuiState) -> int:
    import curses

    curses.curs_set(0)
    screen.nodelay(False)
    screen.keypad(True)
    _init_colours()

    show_help = False
    while True:
        _draw(screen, state, show_help)
        try:
            key = screen.getch()
        except KeyboardInterrupt:
            return 130

        items = state.visible()
        height = max(1, screen.getmaxyx()[0] - 6)

        if key in (ord("q"), 27):
            return 0
        if key in (ord("?"), curses.KEY_F1):
            show_help = not show_help
            continue
        if show_help:
            show_help = False
            continue

        if key in (curses.KEY_DOWN, ord("j")):
            state.selected = min(state.selected + 1, max(0, len(items) - 1))
        elif key in (curses.KEY_UP, ord("k")):
            state.selected = max(0, state.selected - 1)
        elif key == curses.KEY_NPAGE:
            state.selected = min(state.selected + height, max(0, len(items) - 1))
        elif key == curses.KEY_PPAGE:
            state.selected = max(0, state.selected - height)
        elif key in (curses.KEY_HOME, ord("g")):
            state.selected = 0
        elif key in (curses.KEY_END, ord("G")):
            state.selected = max(0, len(items) - 1)
        elif key in (curses.KEY_ENTER, 10, 13):
            state.load_current()
        elif key == ord("/"):
            state.filter = _prompt(screen, "filter: ", state.filter)
            state.selected = 0
        elif key == ord("r"):
            state.library.refresh()
            state.entries = state.library.entries(limit=0)
            state.status = f"library refreshed -- {len(state.entries)} pieces"
        elif key == ord("c"):
            _compile(screen, state, audio=False)
        elif key == ord("w"):
            _compile(screen, state, audio=True)
        elif key == ord("p"):
            _play(screen, state)
        elif key == ord("t"):
            _transpose(screen, state)
        elif key == ord("a"):
            _agent(screen, state)


def _init_colours() -> None:
    import curses

    if not curses.has_colors():
        return
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_CYAN, -1)     # headings
    curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)  # selection
    curses.init_pair(3, curses.COLOR_YELLOW, -1)   # status
    curses.init_pair(4, curses.COLOR_GREEN, -1)    # good
    curses.init_pair(5, curses.COLOR_RED, -1)      # bad


def _pair(index: int):
    import curses

    return curses.color_pair(index) if curses.has_colors() else 0


def _safe_add(screen, row: int, column: int, text: str, attr: int = 0) -> None:
    height, width = screen.getmaxyx()
    if row < 0 or row >= height:
        return
    available = width - column - 1
    if available <= 0:
        return
    try:
        screen.addnstr(row, column, text, available, attr)
    except Exception:
        pass


def _draw(screen, state: TuiState, show_help: bool) -> None:
    import curses

    screen.erase()
    height, width = screen.getmaxyx()
    split = max(28, min(46, width // 3))

    title = f" tapscript  --  {len(state.visible())} pieces "
    _safe_add(screen, 0, 0, title.ljust(width - 1), _pair(1) | curses.A_BOLD)

    if show_help:
        _draw_help(screen)
        screen.refresh()
        return

    items = state.visible()
    list_height = height - 4
    if state.selected < state.offset:
        state.offset = state.selected
    elif state.selected >= state.offset + list_height:
        state.offset = state.selected - list_height + 1

    for row, entry in enumerate(items[state.offset : state.offset + list_height]):
        index = state.offset + row
        label = f"{entry.title[:split - 12]:<{max(1, split - 12)}} {entry.key or '-':>4}"
        attr = _pair(2) if index == state.selected else 0
        _safe_add(screen, row + 2, 1, label.ljust(split - 2), attr)

    for row in range(2, height - 2):
        _safe_add(screen, row, split, "|", _pair(1))

    _draw_detail(screen, state, split + 2, width - split - 3)

    status = state.status[: width - 2]
    _safe_add(screen, height - 2, 1, status, _pair(3))
    keys = "enter load   c compile   w audio   p play   t transpose   a agent   / filter   ? help   q quit"
    _safe_add(screen, height - 1, 1, keys[: width - 2], curses.A_DIM)
    screen.refresh()


def _draw_detail(screen, state: TuiState, column: int, span: int) -> None:
    import curses

    row = 2
    entry = state.current()
    if entry is None:
        _safe_add(screen, row, column, "nothing here", curses.A_DIM)
        return

    _safe_add(screen, row, column, entry.title[:span], _pair(1) | curses.A_BOLD)
    row += 1
    _safe_add(screen, row, column, str(entry.path)[:span], curses.A_DIM)
    row += 2

    if state.detail:
        arrangement = state.detail.get("arrangement", {})
        facts = [
            f"key {state.detail['key']}    tempo {state.detail['tempo']:g}    {state.detail['meter']}",
            f"{state.detail['sections']} sections    {state.detail['bars']} bars    "
            f"{arrangement.get('notes', 0)} notes    {arrangement.get('seconds', 0)}s",
        ]
        for fact in facts:
            _safe_add(screen, row, column, fact[:span])
            row += 1
        voices = ", ".join(
            f"{track['name']}({track['notes']})" for track in arrangement.get("tracks", [])
        )
        if voices:
            _safe_add(screen, row, column, f"voices: {voices}"[:span])
            row += 1
        row += 1

    height = screen.getmaxyx()[0]
    for line in state.message_lines[: max(0, height - row - 3)]:
        _safe_add(screen, row, column, line[:span], _pair(4))
        row += 1
    if state.message_lines:
        row += 1

    for line in state.preview:
        if row >= height - 3:
            break
        _safe_add(screen, row, column, line[:span])
        row += 1


def _draw_help(screen) -> None:
    import curses

    _safe_add(screen, 2, 2, "keys", _pair(1) | curses.A_BOLD)
    for index, (key, description) in enumerate(HELP):
        _safe_add(screen, 4 + index, 4, f"{key:<16} {description}")
    _safe_add(screen, 6 + len(HELP), 4, "press any key to go back", curses.A_DIM)


def _prompt(screen, label: str, initial: str = "") -> str:
    import curses

    height, width = screen.getmaxyx()
    curses.echo()
    curses.curs_set(1)
    _safe_add(screen, height - 2, 1, " " * (width - 2))
    _safe_add(screen, height - 2, 1, label, _pair(3))
    try:
        raw = screen.getstr(height - 2, 1 + len(label), max(4, width - len(label) - 4))
        answer = raw.decode("utf-8", "replace").strip()
    except Exception:
        answer = initial
    finally:
        curses.noecho()
        curses.curs_set(0)
    return answer


def _busy(screen, message: str) -> None:
    height, width = screen.getmaxyx()
    _safe_add(screen, height - 2, 1, " " * (width - 2))
    _safe_add(screen, height - 2, 1, message, _pair(3))
    screen.refresh()


def _compile(screen, state: TuiState, audio: bool) -> None:
    entry = state.current()
    if entry is None:
        return
    from ..pipeline import compile_file

    _busy(screen, "compiling ...")
    output = state.config.paths.output_dir
    try:
        result = compile_file(
            entry.path,
            midi=output / f"{entry.name}.mid",
            audio=(output / f"{entry.name}.wav") if audio else None,
            config=state.config,
        )
    except Exception as exc:
        state.status = f"compile failed: {exc}"
        return
    if not result.ok:
        state.status = f"errors: {result.score.errors()[0].message}"
        return
    state.message_lines = result.describe().splitlines()
    state.status = f"wrote {result.audio_path or result.midi_path}"


def _play(screen, state: TuiState) -> None:
    entry = state.current()
    if entry is None:
        return
    from ..pipeline import compile_file
    from ..render.backends import play_audio

    _busy(screen, "rendering ...")
    target = state.config.paths.output_dir / f"{entry.name}.wav"
    try:
        result = compile_file(entry.path, audio=target, config=state.config)
    except Exception as exc:
        state.status = f"render failed: {exc}"
        return
    if not result.ok or not result.audio_path:
        state.status = "nothing to play"
        return

    state.status = f"playing {result.audio_path.name}"
    thread = threading.Thread(target=play_audio, args=(result.audio_path,), daemon=True)
    thread.start()


def _transpose(screen, state: TuiState) -> None:
    entry = state.current()
    if entry is None:
        return
    key = _prompt(screen, "transpose to: ")
    if not key:
        return
    from ..transform import transpose

    try:
        moved = transpose(entry.read(), key)
    except Exception as exc:
        state.status = f"could not transpose: {exc}"
        return
    target = state.config.paths.output_dir / f"{entry.name}-{key}.tap"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(moved, encoding="utf-8")
    state.preview = moved.splitlines()[:400]
    state.status = f"wrote {target}"


def _agent(screen, state: TuiState) -> None:
    prompt = _prompt(screen, "agent: ")
    if not prompt:
        return
    from ..agent.kernel import Agent
    from ..agent.tools import ToolRegistry
    from ..llm.registry import get_provider

    _busy(screen, "thinking ...")
    try:
        provider = get_provider(state.config)
        agent = Agent(provider=provider, tools=ToolRegistry(config=state.config), config=state.config)
        result = agent.run(prompt)
    except Exception as exc:
        state.status = f"agent failed: {exc}"
        return
    if result.error:
        state.status = result.error[:200]
        return
    state.message_lines = result.reply.splitlines()[:20]
    state.status = f"agent finished in {result.steps} step(s)"
    state.library.refresh()
    state.entries = state.library.entries(limit=0)
