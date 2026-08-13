"""Text to :class:`Score`.

The parser is deliberately forgiving. Real notation in the wild is written by
hand and by language models, and it drifts: some files label every row, some
lead with a pipe and some do not, some carry parenthetical stage directions
where a note should be. Anything ambiguous becomes a diagnostic rather than an
exception, so a file always compiles to *something* and the author is told what
was unclear.

Two dialects share this parser:

``absolute``
    Rows are labelled (``Chords:``, ``Melody:``, ``Lyrics:``, ``@player``) and
    pitches are written in scientific notation (``C4``, ``a2-e3-a3``).

``relative``
    Rows are unlabelled pipe tables and pitch is expressed against the key --
    roman numerals for harmony (``i``, ``bVII``, ``V7``), scale degrees for
    melody (``1``, ``5^``, ``b3_``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import theory
from .ir import (
    ROLE_CHORDS,
    ROLE_LYRICS,
    ROLE_MELODY,
    ROLE_NOTE,
    ROLE_PLAYER,
    Cell,
    Diagnostic,
    Line,
    Meter,
    Metadata,
    Score,
    Section,
)

FENCE_RE = re.compile(r"^\s*```+\s*(\w+)?\s*$")
TITLE_RE = re.compile(r"^\s*(?:\*\*)?TRACK\s*:\s*(.+?)(?:\*\*)?\s*$", re.IGNORECASE)
MD_TITLE_RE = re.compile(r"^\s*#\s+(.+?)\s*$")
SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(?:\(([^)]*)\))?\s*$")
LABEL_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _-]{0,20})\s*:\s*(.*)$")
OPTION_RE = re.compile(r"^\s*(vel|velocity|inst|instrument|program|pan|oct|octave)\s*[:=]\s*(.+?)\s*$", re.IGNORECASE)
# Stage options may also be written at the end of a player's note row. They are
# only taken as options when the value reads as one, so a bar that happens to
# start with the word stays a bar.
STAGE_OPTION_RE = re.compile(r"^\s*(pos|position|speech|feel)\s*[:=]\s*(.+?)\s*$", re.IGNORECASE)

METADATA_KEYS = {
    "key", "tempo", "bpm", "swing", "subdivision", "time", "meter", "mood",
    "style", "feel", "artist", "composer", "source", "capo", "genre", "year",
    "arranger", "difficulty", "notes",
}

ROLE_LABELS = {
    "chords": ROLE_CHORDS,
    "chord": ROLE_CHORDS,
    "harmony": ROLE_CHORDS,
    "melody": ROLE_MELODY,
    "lead": ROLE_MELODY,
    "tune": ROLE_MELODY,
    "lyrics": ROLE_LYRICS,
    "lyric": ROLE_LYRICS,
    "words": ROLE_LYRICS,
    "text": ROLE_LYRICS,
}

# Tokens that mean "keep sounding the previous note".
SUSTAIN_TOKENS = {".", "..", "(hold)", "hold", "-", "~", "(sustain)", "(let ring)", "(ring)"}
# Tokens that mean "silence here".
REST_TOKENS = {"(rest)", "rest", "r", "_", "0", "(silence)", "x", "(x)", "--"}

SUSTAIN_CHARS = "~"


@dataclass
class Slot:
    """One rhythmic position within a bar."""

    kind: str  # note | chord | sustain | rest | text
    weight: float = 1.0
    pitches: tuple[int, ...] = ()
    chord: theory.Chord | None = None
    text: str = ""

    @property
    def sounds(self) -> bool:
        return self.kind in {"note", "chord"}


def strip_fences(text: str) -> str:
    """Remove markdown code fences so embedded notation parses directly."""
    lines = text.splitlines()
    if not any(FENCE_RE.match(line) for line in lines):
        return text
    out: list[str] = []
    inside = False
    saw_fence = False
    for line in lines:
        match = FENCE_RE.match(line)
        if match:
            saw_fence = True
            inside = not inside
            continue
        if inside or not saw_fence:
            out.append(line)
    return "\n".join(out) if out else text


def split_cells(payload: str) -> list[str]:
    """Split a row into per-bar cells on the pipe character."""
    text = payload.strip()
    if not text:
        return []
    if "|" not in text:
        return [text]
    parts = [part.strip() for part in text.split("|")]
    while parts and not parts[0]:
        parts.pop(0)
    while parts and not parts[-1]:
        parts.pop()
    return parts


def token_weight(token: str) -> tuple[str, float]:
    """Split trailing sustain characters off a token.

    ``C4~~~`` is one attack that lasts four grid units; the tildes are not
    separate events. Returns the bare token and its weight in units.
    """
    stripped = token.rstrip(SUSTAIN_CHARS)
    extra = len(token) - len(stripped)
    return (stripped or token), 1.0 + extra


def split_player_line(line: str) -> tuple[str, bool, str]:
    """Split ``@name ...`` into (name, is_declaration, remainder).

    The name runs to the first pipe or colon, whichever comes first. A colon
    first means the row declares an instrument (``@bass: upright, walk it``);
    a pipe first means the row carries notes (``@bass | e2 . g2 . |``).
    """
    body = line.lstrip()[1:]
    pipe = body.find("|")
    colon = body.find(":")
    if colon != -1 and (pipe == -1 or colon < pipe):
        return body[:colon].strip(), True, body[colon + 1 :].strip()
    if pipe != -1:
        return body[:pipe].strip(), False, body[pipe:].strip()
    return body.strip(), True, ""


def detect_dialect(text: str) -> str:
    """Choose a dialect by looking at how the rows are written."""
    labelled = 0
    relative_rows = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        label = LABEL_RE.match(line)
        if label and label.group(1).strip().lower() in ROLE_LABELS:
            labelled += 1
            continue
        if line.startswith("@"):
            labelled += 1
            continue
        if line.startswith("|"):
            tokens = [
                tok
                for tok in re.split(r"[|\s]+", line)
                if tok and tok.lower() not in SUSTAIN_TOKENS and tok.lower() not in REST_TOKENS
            ]
            if not tokens:
                continue
            relative = sum(
                1
                for tok in tokens
                if theory.is_roman(tok) or re.match(r"^[b#]?[1-7][\^_',:]*$", tok)
            )
            if relative >= len(tokens) * 0.5:
                relative_rows += 1
    if relative_rows > labelled:
        return "relative"
    return "absolute"


class Parser:
    """Turn notation text into a :class:`Score`."""

    def __init__(self, text: str, dialect: str = "auto", path: str = "") -> None:
        self.raw_text = text
        self.text = strip_fences(text)
        self.path = path
        self.dialect = detect_dialect(self.text) if dialect in ("auto", "", None) else dialect
        self.diagnostics: list[Diagnostic] = []
        self.meta = Metadata()
        self.sections: list[Section] = []
        self._current: Section | None = None
        self._saw_metadata_marker = False
        self._in_stage = False

    # -- diagnostics ---------------------------------------------------------

    def _note(self, severity: str, message: str, line: int, hint: str = "", source: str = "") -> None:
        self.diagnostics.append(
            Diagnostic(severity=severity, message=message, line=line, hint=hint, source=source.strip()[:120])
        )

    # -- entry point ---------------------------------------------------------

    def parse(self) -> Score:
        for index, raw in enumerate(self.text.splitlines(), start=1):
            self._handle_line(raw, index)
        self._finish_section()
        self._validate()
        return Score(
            meta=self.meta,
            sections=self.sections,
            diagnostics=self.diagnostics,
            dialect=self.dialect,
            source=self.raw_text,
            path=self.path,
        )

    # -- line dispatch -------------------------------------------------------

    def _handle_line(self, raw: str, index: int) -> None:
        line = raw.strip()
        if not line or line.startswith("#") and not MD_TITLE_RE.match(line):
            return
        if line.startswith("//"):
            return

        title = TITLE_RE.match(line)
        if title:
            self.meta.title = title.group(1).strip()
            return

        md_title = MD_TITLE_RE.match(line)
        if md_title and not self.meta.title and not self.sections:
            self.meta.title = md_title.group(1).strip()
            return

        section = SECTION_RE.match(line)
        if section:
            name = section.group(1).strip()
            self._in_stage = False
            if name.lower() in {"metadata", "meta", "header"}:
                self._saw_metadata_marker = True
                return
            if name.lower() in {"stage", "hall", "room"}:
                self._begin_stage()
                return
            self._start_section(name, (section.group(2) or "").strip(), index)
            return

        # A [Stage] block runs until the next header, the way [MetaData] does.
        # Its lines are geometry, not music, so they never reach the arranger.
        if self._in_stage:
            self._handle_stage(line, index)
            return

        if line.startswith("@"):
            self._handle_player(line, index)
            return

        label = LABEL_RE.match(line)
        if label:
            name = label.group(1).strip().lower()
            payload = label.group(2)
            if name in ROLE_LABELS:
                self._handle_role(ROLE_LABELS[name], payload, index, raw)
                return
            if name in METADATA_KEYS or "|" in payload and self._looks_like_metadata(payload):
                self._handle_metadata(line, index)
                return
            self._note(
                "info",
                f"unrecognised row label {label.group(1).strip()!r}, kept as an annotation",
                index,
                hint="rows the compiler plays are Chords:, Melody:, Lyrics: or @player",
                source=raw,
            )
            self._append_line(Line(role=ROLE_NOTE, name=name, line_number=index, raw=raw))
            return

        if "|" in line:
            self._handle_bare_table(line, index, raw)
            return

        if self._current is None and not self.sections:
            # Free text before any section: treat as a subtitle-ish annotation.
            self.meta.extra.setdefault("note", line)
            return

        # Inside a section, an unlabelled row of nothing but notes is notation
        # written without bar lines -- duration-by-spacing. Anything less
        # clear-cut stays an annotation rather than being guessed at.
        if self._current is not None and self._classify_bare(line.split(), strict=True):
            self._handle_bare_table(line, index, raw)
            return

        self._append_line(Line(role=ROLE_NOTE, name="", line_number=index, raw=raw))

    # -- handlers ------------------------------------------------------------

    def _looks_like_metadata(self, payload: str) -> bool:
        parts = [part for part in payload.split("|") if ":" in part]
        return len(parts) >= 1 and all(
            part.split(":", 1)[0].strip().lower() in METADATA_KEYS for part in parts
        )

    def _handle_metadata(self, line: str, index: int) -> None:
        for chunk in line.split("|"):
            if ":" not in chunk:
                continue
            raw_key, _, raw_value = chunk.partition(":")
            key = raw_key.strip().lower()
            value = raw_value.strip()
            if not value:
                continue
            try:
                self._apply_metadata(key, value)
            except Exception as exc:  # never let a header field abort a parse
                self._note("warning", f"could not read {key} = {value!r} ({exc})", index)

    def _apply_metadata(self, key: str, value: str) -> None:
        if key == "key":
            self.meta.key = theory.parse_key(value)
        elif key in {"tempo", "bpm"}:
            number = re.search(r"-?\d+(?:\.\d+)?", value)
            if number:
                tempo = float(number.group(0))
                self.meta.tempo = min(max(tempo, 20.0), 400.0)
        elif key == "swing":
            number = re.search(r"-?\d+(?:\.\d+)?", value)
            if number:
                swing = float(number.group(0))
                self.meta.swing = swing / 100.0 if swing > 1 else swing
        elif key == "subdivision":
            self.meta.subdivision = value
        elif key in {"time", "meter"}:
            self.meta.meter = Meter.parse(value)
        else:
            self.meta.extra[key] = value

    def _begin_stage(self) -> None:
        """Start a ``[Stage]`` block, creating the stage the first time."""
        from ..perform.stage import Stage

        self._in_stage = True
        self._finish_section()
        if self.meta.stage is None:
            self.meta.stage = Stage()

    def _handle_stage(self, line: str, index: int) -> None:
        from ..perform.stage import read_stage_line

        stage = self.meta.stage
        if stage is None:  # only reachable if _in_stage was set without a stage
            return
        before = len(stage.problems)
        read_stage_line(stage, line, index)
        for _line_number, message in stage.problems[before:]:
            self._note(
                "warning",
                f"stage: {message}",
                index,
                hint="a stage row is `@name: pos 4,-6 | speech: brass | feel: -6ms`",
                source=line,
            )

    def _stage_options(self, text: str) -> tuple[str, object] | None:
        """Read a trailing ``pos: 4,-6`` cell, or return None to leave it alone."""
        from ..perform.profiles import profile_for_name
        from ..perform.stage import parse_duration, parse_position

        option = STAGE_OPTION_RE.match(text)
        if not option:
            return None
        key, value = option.group(1).lower(), option.group(2).strip()
        if key in {"pos", "position"}:
            point = parse_position(value)
            return ("pos", point) if point else None
        if key == "speech":
            if profile_for_name(value) is not None:
                return ("speech", value.strip().lower())
            seconds = parse_duration(value)
            return ("speech_seconds", seconds) if seconds is not None else None
        seconds = parse_duration(value)
        return ("feel", seconds) if seconds is not None else None

    def _place_from_options(self, name: str, options: dict[str, object]) -> None:
        """Fold inline stage options on a player row into the stage."""
        from ..perform.stage import Placement, Stage

        keys = {"pos", "speech", "speech_seconds", "feel"}
        if not keys & set(options):
            return
        if self.meta.stage is None:
            self.meta.stage = Stage()
        key = name.strip().lower()
        existing = self.meta.stage.placements.get(key)
        position = options.get("pos") or (existing.position if existing else (0.0, 0.0))
        self.meta.stage.placements[key] = Placement(
            name=key,
            position=position,  # type: ignore[arg-type]
            speech_name=str(options.get("speech") or (existing.speech_name if existing else "")),
            speech_override=options.get("speech_seconds")  # type: ignore[arg-type]
            or (existing.speech_override if existing else None),
            p_center_override=existing.p_center_override if existing else None,
            feel=float(options.get("feel") or (existing.feel if existing else 0.0)),
        )

    def _handle_role(self, role: str, payload: str, index: int, raw: str) -> None:
        self._ensure_section(index)
        cells = [Cell(tokens=self._tokenise(text, role), line=index) for text in split_cells(payload)]
        if not cells:
            self._note("info", f"empty {role} row", index, source=raw)
            return
        self._append_line(
            Line(role=role, cells=cells, line_number=index, raw=raw, barred="|" in payload)
        )

    def _handle_player(self, line: str, index: int) -> None:
        name, is_declaration, remainder = split_player_line(line)
        if not name:
            self._note("warning", "player row has no name", index, source=line)
            return

        # `@name: piano, arpeggiate softly` -- a declaration, not note data.
        if is_declaration:
            self._ensure_section(index)
            instrument = remainder.split(",")[0].strip()
            self._append_line(
                Line(
                    role=ROLE_NOTE,
                    name=name,
                    options={"instrument": instrument, "direction": remainder.strip()},
                    line_number=index,
                    raw=line,
                )
            )
            return

        self._ensure_section(index)
        barred = "|" in remainder
        cells_text = split_cells(remainder)
        options: dict[str, object] = {}
        while cells_text:
            staged = self._stage_options(cells_text[-1])
            if staged is not None:
                options[staged[0]] = staged[1]
                cells_text.pop()
                continue
            option = OPTION_RE.match(cells_text[-1])
            if not option:
                break
            key, value = option.group(1).lower(), option.group(2).strip()
            if key in {"vel", "velocity"}:
                try:
                    options["velocity"] = max(1, min(127, int(float(value))))
                except ValueError:
                    self._note("warning", f"velocity {value!r} is not a number", index)
            elif key in {"inst", "instrument"}:
                options["instrument"] = value
            elif key in {"oct", "octave"}:
                try:
                    options["octave"] = int(value)
                except ValueError:
                    pass
            else:
                options[key] = value
            cells_text.pop()

        self._place_from_options(name, options)

        if not cells_text:
            self._append_line(
                Line(role=ROLE_NOTE, name=name, options=options, line_number=index, raw=line)
            )
            return

        cells = [Cell(tokens=self._tokenise(text, ROLE_PLAYER), line=index) for text in cells_text]
        self._append_line(
            Line(
                role=ROLE_PLAYER,
                name=name,
                cells=cells,
                options=options,
                line_number=index,
                raw=line,
                barred=barred,
            )
        )

    def _handle_bare_table(self, line: str, index: int, raw: str) -> None:
        """An unlabelled row. The relative dialect's normal form."""
        self._ensure_section(index)
        cells_text = split_cells(line)
        tokens = [tok for text in cells_text for tok in text.split()]
        if not tokens:
            return
        role = self._classify_bare(tokens)
        if role is None:
            self._note(
                "warning",
                "row has bars but no recognisable chords or notes, skipped",
                index,
                hint="label it with Chords:, Melody: or @player so it is not guessed at",
                source=raw,
            )
            self._append_line(Line(role=ROLE_NOTE, cells=[], line_number=index, raw=raw))
            return
        cells = [Cell(tokens=self._tokenise(text, role), line=index) for text in cells_text]
        self._append_line(
            Line(role=role, cells=cells, line_number=index, raw=raw, barred="|" in line)
        )

    def _classify_bare(self, tokens: list[str], strict: bool = False) -> str | None:
        """Decide whether an unlabelled row is harmony or melody.

        Rows without a label have to be classified by shape. Guessing wrong
        silently is how the previous engine lost notes, so the bar is set high:
        in *strict* mode -- a row with no bar lines at all, which could just as
        easily be prose -- every token must be musical and pitches must carry
        an octave, or the row is left as an annotation.
        """
        bare = [token_weight(tok)[0] for tok in tokens]
        meaningful = [
            tok for tok in bare if tok.lower() not in SUSTAIN_TOKENS and tok.lower() not in REST_TOKENS
        ]
        if not meaningful or (strict and len(meaningful) < 2):
            return None

        def is_melodic(token: str) -> bool:
            if strict:
                return bool(re.match(r"^[A-Ga-g][#b♯♭]*-?\d+$", token)) or bool(
                    re.match(r"^[b#♭♯]?[1-7][\^_',:]+$", token)
                )
            return theory.is_pitch(token) or bool(re.match(r"^[b#♭♯]?[1-7][\^_',:]*$", token))

        def is_harmonic(token: str) -> bool:
            if theory.is_roman(token):
                return True
            if strict:
                # A bare letter is a word as often as it is a chord.
                return theory.is_chord(token) and len(token) > 1 and not token[-1].isdigit()
            return theory.is_chord(token)

        melodic = sum(1 for tok in meaningful if is_melodic(tok))
        harmony = sum(1 for tok in meaningful if not is_melodic(tok) and is_harmonic(tok))
        recognised = melodic + harmony
        if recognised == 0:
            return None
        if strict and recognised < len(meaningful):
            return None
        if not strict and recognised < len(meaningful) * 0.5:
            return None
        return ROLE_CHORDS if harmony > melodic else ROLE_MELODY

    # -- tokenising ----------------------------------------------------------

    def _tokenise(self, text: str, role: str) -> list[str]:
        if role == ROLE_LYRICS:
            return text.split()
        # Keep parenthesised directions such as `(hold 4 beats)` as one token.
        tokens: list[str] = []
        buffer: list[str] = []
        depth = 0
        for char in text:
            if char == "(":
                depth += 1
                buffer.append(char)
            elif char == ")":
                depth = max(0, depth - 1)
                buffer.append(char)
            elif char.isspace() and depth == 0:
                if buffer:
                    tokens.append("".join(buffer))
                    buffer = []
            else:
                buffer.append(char)
        if buffer:
            tokens.append("".join(buffer))
        return tokens

    # -- section bookkeeping -------------------------------------------------

    def _start_section(self, name: str, description: str, index: int) -> None:
        self._finish_section()
        self._current = Section(name=name, description=description, line_number=index)

    def _ensure_section(self, index: int) -> None:
        if self._current is None:
            self._current = Section(name="Main", line_number=index)

    def _append_line(self, line: Line) -> None:
        self._ensure_section(line.line_number)
        assert self._current is not None
        self._current.lines.append(line)

    def _finish_section(self) -> None:
        if self._current is not None:
            self.sections.append(self._current)
            self._current = None

    # -- validation ----------------------------------------------------------

    def _validate(self) -> None:
        if not self.sections:
            self._note("error", "no sections found", 1, hint="start a section with a header such as [Verse]")
            return
        playable = 0
        for section in self.sections:
            # Rows repeated within a section run one after another, so compare
            # each voice's total against the longest voice, not row by row.
            groups: dict[str, list[Line]] = {}
            for line in section.lines:
                if not line.cells or line.role == ROLE_NOTE:
                    continue
                key = f"{line.role}:{line.name}" if line.role == ROLE_PLAYER else line.role
                groups.setdefault(key, []).append(line)
            totals = {key: sum(line.bar_count for line in group) for key, group in groups.items()}
            if len(set(totals.values())) > 1:
                widest = max(totals.values())
                for key, total in totals.items():
                    if total == widest:
                        continue
                    first = groups[key][0]
                    self._note(
                        "warning",
                        f"[{section.name}] {key} covers {total} bar(s), the section runs {widest}",
                        first.line_number,
                        hint="short rows stop early rather than stretching to fill the section",
                        source=first.raw,
                    )
            playable += sum(
                1 for line in section.lines if line.cells and line.role in {ROLE_CHORDS, ROLE_MELODY, ROLE_PLAYER}
            )
        if playable == 0:
            self._note(
                "error",
                "nothing to play: no chord, melody or player rows",
                1,
                hint="add a row such as `Chords: | Am | F |`",
            )


def parse(text: str, dialect: str = "auto", path: str = "") -> Score:
    """Parse notation text into a :class:`Score`."""
    return Parser(text, dialect=dialect, path=path).parse()


def parse_file(path: str, dialect: str = "auto") -> Score:
    with open(path, "r", encoding="utf-8") as handle:
        return parse(handle.read(), dialect=dialect, path=path)
