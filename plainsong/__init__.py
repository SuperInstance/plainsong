"""Plainsong -- plain-text music notation that compiles to MIDI and audio.

The public surface is small on purpose::

    from plainsong import compile_text

    result = compile_text(open("song.song").read(), midi="song.mid", wav="song.wav")
    print(result.summary())

Everything else -- providers, agents, interfaces -- is built on top of this and
imported from its own subpackage, so the compiler stays usable on its own.
"""

from __future__ import annotations

from .version import __version__

__all__ = ["__version__", "compile_text", "compile_file", "parse", "arrange"]


def __getattr__(name: str):
    # Imported lazily so `import plainsong` stays cheap for the CLI's fast paths.
    if name in {"parse", "parse_file"}:
        from .notation import parser

        return getattr(parser, name)
    if name == "arrange":
        from .notation.arrange import arrange

        return arrange
    if name in {"compile_text", "compile_file", "CompileResult"}:
        from .pipeline import CompileResult, compile_file, compile_text

        return {"compile_text": compile_text, "compile_file": compile_file, "CompileResult": CompileResult}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
