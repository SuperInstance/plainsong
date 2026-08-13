"""The tools this server adds to the registry.

The MCP server does not keep a list of tools of its own: it enumerates
``ToolRegistry.specs()``, so a tool added anywhere else in the codebase appears
over the protocol without anything here changing. What this module does is add
the ones that only make sense over a protocol -- the ensemble session, feature
extraction, and the bridge to the conductor -- in the same shape as every other
tool, so the CLI agent gets them too.

Tools return a value, never an exception. A failure is something the model has
to read and act on; an exception would end its turn instead.
"""

from __future__ import annotations

import json
from typing import Any

from . import ensemble as ens
from . import features as feat


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


def _string(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def _integer(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}


def _boolean(description: str) -> dict[str, str]:
    return {"type": "boolean", "description": description}


def looks_like_failure(text: str) -> bool:
    """Whether a tool result is a failure the model should recover from.

    Tools report trouble in the result rather than by raising, so the transport
    has to recognise it to set ``isError``. Two forms count: a line that starts
    with ``error:``, and a JSON object with an ``error`` key.
    """
    stripped = text.lstrip()
    if stripped[:6].lower() == "error:":
        return True
    if stripped[:1] != "{":
        return False
    try:
        decoded = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return False
    return isinstance(decoded, dict) and bool(decoded.get("error"))


def register(registry: Any, session_root: Any = None) -> None:
    """Add the protocol-facing tools to *registry*."""
    config = getattr(registry, "config", None)
    paths = getattr(config, "paths", None)

    def _session(name: str) -> ens.Session:
        return ens.find_session(name, root=session_root, paths=paths)

    def _notation(path: str, content: str) -> tuple[str, str]:
        """Notation from the sandbox or inline. Returns (text, problem)."""
        if content:
            return content, ""
        if not path:
            return "", "error: pass either a path or inline content"
        source = registry.sandbox.resolve(path)
        if not source.is_file():
            return "", f"error: {path} does not exist"
        return source.read_text(encoding="utf-8", errors="replace"), ""

    # -- the shared score ----------------------------------------------------

    def ensemble_open(
        session: str,
        title: str = "",
        key: str = "C",
        tempo: float = 100.0,
        meter: str = "4/4",
        bars: int = 8,
        subdivision: str = "8th",
        sections: list[Any] | None = None,
        voices: list[str] | None = None,
    ) -> Any:
        try:
            opened = ens.open_session(
                session,
                root=session_root,
                paths=paths,
                title=title,
                key=key,
                tempo=tempo,
                meter=meter,
                bars=bars,
                subdivision=subdivision,
                sections=sections,
                voices=voices,
            )
        except ens.EnsembleError as exc:
            return f"error: {exc}"
        state = opened.read()
        state["opened"] = True
        return state

    def ensemble_join(session: str, voice: str, agent: str, takeover: bool = False) -> Any:
        try:
            return _session(session).join(voice, agent, takeover=takeover)
        except ens.EnsembleError as exc:
            return f"error: {exc}"

    def ensemble_leave(session: str, voice: str, agent: str) -> Any:
        try:
            return _session(session).leave(voice, agent)
        except ens.EnsembleError as exc:
            return f"error: {exc}"

    def ensemble_read(
        session: str = "",
        voice: str = "",
        agent: str = "",
        bars: str = "",
        history: int = 8,
    ) -> Any:
        if not session:
            known = ens.list_sessions(session_root, paths)
            return {"sessions": known, "note": "pass a session name to read one"}
        try:
            return _session(session).read(
                voice=voice, agent=agent, bars=bars, history=history
            )
        except ens.EnsembleError as exc:
            return f"error: {exc}"

    def ensemble_write_part(
        session: str,
        voice: str,
        agent: str,
        content: str,
        base_version: int = -1,
        summary: str = "",
    ) -> Any:
        if base_version < 0:
            return (
                "error: pass base_version -- the version you read this voice at. Writing "
                "without one would overwrite whatever arrived in the meantime."
            )
        try:
            return _session(session).write_part(voice, agent, content, base_version, summary)
        except ens.Conflict as exc:
            return {"error": str(exc), "rebase": exc.state}
        except ens.EnsembleError as exc:
            return f"error: {exc}"

    def ensemble_render(session: str, audio: bool = False) -> Any:
        try:
            return _session(session).render(audio=audio, config=config)
        except ens.EnsembleError as exc:
            return f"error: {exc}"

    def ensemble_log(session: str, limit: int = 40) -> Any:
        try:
            entries = _session(session).entries(limit=max(1, min(int(limit), 500)))
        except ens.EnsembleError as exc:
            return f"error: {exc}"
        return {"session": session, "entries": entries}

    def ensemble_status(session: str = "") -> Any:
        if not session:
            return {"sessions": ens.list_sessions(session_root, paths)}
        try:
            return _session(session).status()
        except ens.EnsembleError as exc:
            return f"error: {exc}"

    # -- analysis ------------------------------------------------------------

    def analyze_features(
        path: str = "",
        content: str = "",
        session: str = "",
        voice: str = "",
        bars: str = "",
        table: bool = False,
    ) -> Any:
        from ..notation import arrange, parse

        if session:
            try:
                text, problem = _session(session).score(), ""
            except ens.EnsembleError as exc:
                return f"error: {exc}"
        else:
            text, problem = _notation(path, content)
        if problem:
            return problem
        score = parse(text)
        if score.has_errors:
            return "error: the notation has errors:\n" + "\n".join(
                f"  {diag.format()}" for diag in score.errors()
            )
        arrangement = arrange(score)
        found = feat.extract(arrangement, voice=voice)
        first, last = ens.parse_bar_range(bars, len(found))
        window = [entry for entry in found if first <= entry.bar <= last]
        report: dict[str, Any] = {
            "voice": voice or "(all)",
            "bars": len(found),
            "beats_per_bar": feat.bar_length(arrangement),
            "tempo": float(arrangement.meta.tempo),
            "feature_names": list(feat.FEATURE_NAMES),
            "mean": feat.summarise(window),
            "per_bar": [entry.as_dict() for entry in window],
        }
        if table:
            report["table"] = feat.format_table(window)
        return report

    # -- the conductor -------------------------------------------------------

    def apply_directives(
        directives: Any,
        path: str = "",
        content: str = "",
        session: str = "",
        frame: str = "",
        features: bool = True,
    ) -> Any:
        module, problem = _conductor()
        if problem:
            return problem
        from ..notation import arrange, parse
        from ..notation.arrange import ArrangeOptions

        if session:
            try:
                text, load_problem = _session(session).score(), ""
            except ens.EnsembleError as exc:
                return f"error: {exc}"
        else:
            text, load_problem = _notation(path, content)
        if load_problem:
            return load_problem

        score = parse(text)
        if score.has_errors:
            return "error: the notation has errors:\n" + "\n".join(
                f"  {diag.format()}" for diag in score.errors()
            )

        reading = module.read(directives)
        written = arrange(score, ArrangeOptions(frame=frame))
        conducted = module.apply(written, reading, frame=frame)
        report: dict[str, Any] = {
            "directives": _as_dict(reading),
            "frame": frame or getattr(conducted, "frame", ""),
            "before": written.summary(),
            "after": conducted.summary(),
            "staged": score.meta.stage is not None,
        }
        if features:
            report["feature_names"] = list(feat.FEATURE_NAMES)
            report["before_features"] = [entry.as_dict() for entry in feat.extract(written)]
            report["after_features"] = [entry.as_dict() for entry in feat.extract(conducted)]
        return report

    # -- registration --------------------------------------------------------

    registry.add(
        "ensemble_open",
        "Open a shared session several agents can write to, or reopen one that exists. "
        "Sets the key, tempo, metre and form every part is written against.",
        _schema(
            {
                "session": _string("Session name, letters and digits."),
                "title": _string("What the piece is called."),
                "key": _string("Key, such as 'Am' or 'F# dorian'."),
                "tempo": {"type": "number", "description": "Beats per minute."},
                "meter": _string("Time signature, such as '4/4'."),
                "bars": _integer("Bars per section."),
                "subdivision": _string("Written subdivision: 8th, 16th, triplet."),
                "sections": {
                    "type": "array",
                    "description": "The form: names, or objects with name, description and bars.",
                    "items": {"type": ["string", "object"]},
                },
                "voices": {
                    "type": "array",
                    "description": "Voices to advertise: @bass, @violin1, chords, melody, lyrics.",
                    "items": {"type": "string"},
                },
            },
            ["session"],
        ),
        ensemble_open,
    )
    registry.add(
        "ensemble_join",
        "Claim one voice of a session. A voice has one owner at a time, so claiming is how "
        "agents avoid choosing the same part. Returns everything needed to start writing.",
        _schema(
            {
                "session": _string("Session name."),
                "voice": _string("Voice to claim: @bass, @violin1, chords, melody, lyrics."),
                "agent": _string("Who you are."),
                "takeover": _boolean("Take a held voice. Only when its owner has stopped."),
            },
            ["session", "voice", "agent"],
        ),
        ensemble_join,
    )
    registry.add(
        "ensemble_leave",
        "Release a voice you hold so another agent can take it.",
        _schema(
            {
                "session": _string("Session name."),
                "voice": _string("The voice you hold."),
                "agent": _string("Who you are."),
            },
            ["session", "voice", "agent"],
        ),
        ensemble_leave,
    )
    registry.add(
        "ensemble_read",
        "Read a session in one call: key, tempo, metre, form, which voices exist and who "
        "holds them, what every voice plays in the bars you are about to write, your own "
        "part, the version to write against, and what has changed recently.",
        _schema(
            {
                "session": _string("Session name. Omit to list the sessions."),
                "voice": _string("Your voice, to get its content and version."),
                "agent": _string("Who you are."),
                "bars": _string("Bars to look at, such as '5-8'. Default is all of them."),
                "history": _integer("How many log entries to include (default 8)."),
            }
        ),
        ensemble_read,
    )
    registry.add(
        "ensemble_write_part",
        "Write your voice's part. The notation is parsed and checked against the session "
        "header before anything reaches disk. Pass the base_version you read; if the voice "
        "has moved on the write is refused and you are given the current part to rebase onto.",
        _schema(
            {
                "session": _string("Session name."),
                "voice": _string("The voice you are writing."),
                "agent": _string("Who you are."),
                "content": _string(
                    "The part: section headers and rows for your voice only, no header block."
                ),
                "base_version": _integer("The version you read this voice at."),
                "summary": _string("One line saying what you changed, for the log."),
            },
            ["session", "voice", "agent", "content", "base_version"],
        ),
        ensemble_write_part,
    )
    registry.add(
        "ensemble_render",
        "Merge the parts and compile the session to MIDI, and optionally audio.",
        _schema(
            {
                "session": _string("Session name."),
                "audio": _boolean("Also render audio. Slower; off by default."),
            },
            ["session"],
        ),
        ensemble_render,
    )
    registry.add(
        "ensemble_log",
        "Read the session's change log, oldest first. This is how a joining agent finds out "
        "what has already happened.",
        _schema(
            {"session": _string("Session name."), "limit": _integer("Last N entries.")},
            ["session"],
        ),
        ensemble_log,
    )
    registry.add(
        "ensemble_status",
        "The short view of a session: version, voices, who holds what, bar count and whether "
        "the merged score still compiles. Omit the name to list sessions.",
        _schema({"session": _string("Session name. Omit to list the sessions.")}),
        ensemble_status,
    )
    registry.add(
        "analyze_features",
        "Describe a piece as sixteen numbers per bar -- density, register, tension, "
        "syncopation, dynamics and the rest -- so a model can perceive what is written.",
        _schema(
            {
                "path": _string("A .tap file to analyse."),
                "content": _string("Notation to analyse instead of a path."),
                "session": _string("An ensemble session to analyse instead."),
                "voice": _string("One voice by name. Default is the whole texture."),
                "bars": _string("Bars to report, such as '1-8'."),
                "table": _boolean("Also return a fixed-width table for reading."),
            }
        ),
        analyze_features,
    )
    registry.add(
        "apply_directives",
        "Apply a bandleader's directive JSON to a piece or an ensemble session and return "
        "the result as data: the directives as they were read, what the arrangement was "
        "before and after, and the sixteen features per bar of each. Use conduct_score "
        "instead when you want the timing report in prose.",
        _schema(
            {
                "directives": {
                    "type": ["object", "string", "array"],
                    "description": "The directive JSON. Call directive_reference for the shape.",
                },
                "path": _string("A .tap file."),
                "content": _string("Notation instead of a path."),
                "session": _string("An ensemble session instead."),
                "frame": _string("Whose ears: conductor, audience, player:<name>, score."),
                "features": _boolean("Include the feature vectors. On by default."),
            },
            ["directives"],
        ),
        apply_directives,
    )


# --------------------------------------------------------------------------
# the conductor, if this install has one
# --------------------------------------------------------------------------


def _conductor() -> tuple[Any, str]:
    """The conducting module, or a message saying this install has none.

    Soft on purpose. ``perform/`` is a separate feature and may be absent, older
    than this file, or newer than it. A missing conductor costs one tool call
    and a readable answer; it must not stop the server from starting or take
    the other tools down with it.
    """
    try:
        from ..perform import conduct as module
    except ImportError as exc:
        return None, (
            "error: this install has no conductor (tapscript.perform.conduct is not "
            f"importable: {exc}). Everything else on this server still works."
        )
    missing = [name for name in ("read", "apply") if not hasattr(module, name)]
    if missing:
        return None, (
            "error: the installed conductor is a different shape from the one this server "
            f"expects (no {', '.join(missing)}); use conduct_score instead"
        )
    return module, ""


def _as_dict(reading: Any) -> Any:
    """A directive set as data, whatever the conductor chose to call it."""
    describe = getattr(reading, "as_dict", None)
    return describe() if callable(describe) else str(reading)
