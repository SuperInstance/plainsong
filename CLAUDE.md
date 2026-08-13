# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

TapScript is a plain-text music notation that compiles to MIDI and audio. The
product is the `tapscript/` package: one compiler, three interfaces (CLI, TUI,
web), a provider-agnostic model layer, and an embedded agent. `legacy/` holds
the two superseded engines and is not maintained.

## Commands

No dependencies are required. Do not add any to the core.

```bash
# Tests (CI runs these on 3.10-3.13 across Linux, macOS, Windows, with no pip install)
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_notation.TestArrange.test_tokens_divide_the_bar
python3 -m pytest tests -q                    # works too, if pytest is installed

# The system's checks on itself -- run these before and after any change
python3 -m tapscript spec                     # exits non-zero on failure
python3 -m tapscript doctor --specs
python3 -m tapscript check docs examples academy   # 6,322 .tap files must still parse

# Working with notation
python3 -m tapscript new "Title" -o song.tap
python3 -m tapscript compile song.tap -o out.mid --audio out.wav
python3 -m tapscript info song.tap --verbose  # every diagnostic
python3 -m tapscript transpose song.tap Dm

# Interfaces
python3 -m tapscript tui
python3 -m tapscript serve --port 8765

# The agent, offline
python3 -m tapscript agent --provider echo "write something in D minor"
```

Every command takes `--json`. Use it when parsing output.

## Architecture

`docs/architecture.md` is accurate; read it before a nontrivial change. The
parts that are easy to get wrong:

**Parse and arrange are separate.** `notation/parser.py` builds a `Score` --
structure and tokens as written, timing still implicit. `notation/arrange.py`
turns that into an `Arrangement` of timed notes. Renderers only ever see the
arrangement. Transposition is parse, rewrite tokens, emit (`transform.py`),
which is why it moves the chord row.

**The timing rule: a bar is one bar long, and the tokens in it divide it.**
Twelve tokens are triplets; a seventeenth cannot spill into the next bar. This
is the fix for BUG-1/BUG-2 in `examples/edge-cases/BUGS.md`. `core.bar_fill =
"grid"` restores the old fixed-slot behaviour and reports what it drops. Slot
positions are computed from the bar start, never accumulated -- do not
reintroduce a running cursor.

**Rows of different kinds sound together; a row repeated in one section follows
on.** Two `Melody:` rows in a section are eight bars, not four played twice.

**Nothing may be imported at module scope outside the standard library.** The
MIDI writer and synthesiser are hand-written for this reason. NumPy, fluidsynth,
ffmpeg and mido are probed in `runtime/capabilities.py` and imported inside the
function that uses them. CI installs nothing, so a stray import fails the build.

**Nothing may hardcode a path.** Everything comes from `runtime/paths.py`.
`tests/test_runtime.py::test_no_home_directory_is_hardcoded` greps the package
for `~/.openclaw`, `/home/eileen` and `/Users/` -- the previous version wrote
into one contributor's home directory.

**Providers are data.** `llm/catalog.json` maps a provider to a wire format;
`llm/providers/` has one adapter per format (`openai`, `anthropic`, `gemini`,
`host`, `echo`). Adding a service that speaks an existing format is a catalogue
entry, not code. The `host` provider borrows the model from a surrounding agent
(Claude Code, openclaw) so no API key is needed -- see `docs/host-bridge.md`.

**One of everything.** GM programs live only in `tapscript/instruments.py`; all
three interfaces call `pipeline.compile_text`. The version this replaced kept
four copies of the GM table that had drifted apart. If you are about to copy a
table between files, don't.

## Specs

`specs/*.toml` state what the system promises; `tapscript/selfcheck.py` holds the
checks. They are separate from the tests because a user runs them to find out
what works on their machine, and the build agent runs them to verify its own
changes. A new capability wants a spec as well as a test.

## Changing the notation

Several thousand `.tap` files in this repository depend on it, plus files we
cannot see. A change needs a failing-then-passing spec, a clean
`tapscript check docs examples academy`, and a `CHANGELOG.md` entry. If existing
notation would parse differently afterwards, that is breaking even if the new
reading is better: put it behind a setting and default to the old behaviour.

## Content directories

`docs/fakebook/` (~3,800 generated `.tap` transcriptions across a dozen
languages), `docs/songs/`, `docs/prose/`, `docs/traditions/`, `docs/training/`,
`academy/`. Generated material -- it parses, but it is not all well written, and
it accounts for ~3,800 bar-count warnings. The old generator in
`legacy/scripts/fakebook_generator.py` enforced a copyright policy (full
melody+lyrics only for public-domain works, chord charts otherwise). Keep that
policy if you regenerate anything.

## Rough edges

- The built-in synthesiser is a preview renderer; timbres are approximations.
  Audio is mono.
- The host bridge cannot stream and reports no token usage.
- `legacy/` needs `numpy scipy pretty_midi flask` and is excluded from CI and
  from ruff. It can be deleted.
