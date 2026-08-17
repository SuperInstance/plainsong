# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Plainsong is a plain-text music notation that compiles to MIDI and audio. The
product is the `plainsong/` package: one compiler, three interfaces (CLI, TUI,
web), a provider-agnostic model layer, an embedded agent, and a timing solver
that treats a written beat as the moment a sound *arrives* rather than the
moment a player acts. The two superseded engines are not maintained and live
in `legacy/`, which also holds unrelated work that is still active -- see
Rough edges.

Where it came from, because it explains most of the rules below. The first
version was built by an agent around the tools that agent happened to have: it
wrote into one contributor's home directory, needed numpy/scipy/pretty_midi/flask,
and carried four copies of the General MIDI table that had drifted apart. This
version is the rebuild — nothing hardcoded, nothing imported that is not in the
standard library, one copy of everything. The rules in this file are not style
preferences; each one is a fault that was actually paid for.

`SuperInstance/plainsong-mcp` is the sibling repository: the same tools served
over the Model Context Protocol, plus the session layer that lets several agents
write one score at once. It depends on this package and not the other way round.

## Commands

No dependencies are required. Do not add any to the core.

```bash
# Tests (CI runs these on 3.10-3.13 across Linux, macOS, Windows, with no pip install)
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_notation.TestArrange.test_tokens_divide_the_bar
python3 -m pytest tests -q                    # works too, if pytest is installed

# The system's checks on itself -- run these before and after any change
python3 -m plainsong spec                     # exits non-zero on failure
python3 -m plainsong doctor --specs
python3 -m plainsong check docs examples plainsong/songbook README.md   # every source, prose included

# Working with notation
python3 -m plainsong new "Title" -o song.song
python3 -m plainsong compile song.song -o out.mid --audio out.wav
python3 -m plainsong info song.song --verbose  # every diagnostic
python3 -m plainsong transpose song.song Dm

# The browser demo -- open it, no server needed
#   docs/demo/index.html

# Interfaces
python3 -m plainsong tui
python3 -m plainsong serve --port 8765
python3 -m plainsong mcp --list-tools        # see also the plainsong-mcp repo

# Timing
python3 -m plainsong stage orchestra.song     # what each listener actually hears
# there is no `conduct` subcommand -- gestures are `plainsong.perform.conduct`

# The agent, offline
python3 -m plainsong agent --provider echo "write something in D minor"
python3 -m plainsong setup                   # connect a model
python3 -m plainsong build                   # tailor this install to the machine
```

Every command takes `--json`. Use it when parsing output.

Run the suite with `discover`, not by naming files. Several tests are about how
modules behave when imported in a particular order, and a single-file run can
pass while the suite fails.

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

**A written time is an arrival time.** This is the one genuinely new idea in the
system and the easiest thing here to break. `perform/solve.py` treats the beat a
note is written on as the moment the sound should *reach the listener*, and
solves backwards for when the player has to move:

```
emission = feel*feel_scale + shift - alignment*(speech + preparation + travel_ref + p_center)
arrival  = emission + speech + preparation + p_center + travel_observed
```

Two propagation terms, and they are not the same number. `reference_propagation`
is the distance to the listener the score is compensated *for*; `observed_propagation`
is the distance to whoever is currently listening. When they are equal the second
line cancels the first and the note lands exactly where it was written. When they
differ it does not — which is why the spread is 0 ms at the podium and non-zero
at every player's desk, and why an orchestra watches the conductor instead of
listening to each other. If you ever collapse those two into one variable the
model becomes symmetric and stops describing a real room.

`feel` survives compensation deliberately: swing is meant to be heard, so it is
not solved away. Note the distinction between `anticipate`, which moves the
emission and leaves the arrival on the grid (a correction), and `push_forward`,
which moves the arrival itself (an intention). They are not synonyms.

Without a `[Stage]` block none of this runs and written times are taken at face
value. That default is load-bearing — every existing `.song` file relies on it.

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

**One of everything.** GM programs live only in `plainsong/instruments.py`; all
three interfaces call `pipeline.compile_text`. The version this replaced kept
four copies of the GM table that had drifted apart. If you are about to copy a
table between files, don't.

There are exactly two live exceptions, both deliberate and both carrying a guard:

- `plainsong/mcp/` also exists in the sibling repository (see Rough edges).
- `docs/demo/index.html` carries its own parser, arranger and MIDI writer in
  JavaScript, because the landing page has to run with nothing installed. It is
  a faithful subset, verified note-for-note against this compiler across
  triplets, 3/4, 6/8, chord qualities, stacks, sustains and repeated rows. The
  page states the note count it produces for each preset, and
  `tests/test_demo.py` compiles the same notation with the real compiler and
  requires the same answer — so a change to the arranger that moves a count
  fails in CI rather than making the demo quietly lie. If you change the
  arranger, expect that test and re-check the page.

**3.10 is a supported version, and it does not have `tomllib`.** That is why
`runtime/_toml.py` exists. Do not delete it as dead code and do not `import
tomllib` at module scope anywhere — the CLI would stop importing on the oldest
version we advertise, which is exactly the bug it was written to fix. It is
kept honest by a differential test that parses every TOML file in the repo with
both readers and compares.

## Portability

CI is 3.10 through 3.13 across Linux, macOS and Windows. Windows is where the
interesting failures live, and all three of these were found by tests running
there rather than by reasoning:

- Stock Python on Windows ships no `curses`, so the TUI does not run. It says so
  and points at `windows-curses`.
- `Path.home()` *raises* when neither HOME nor USERPROFILE is set, which is the
  case on some runners. `runtime/paths.py` catches it and falls back to a temp
  directory.
- A file with a delete pending answers `PermissionError` on open. Lock
  acquisition treats that as contention, not as an error.

`chmod` is a no-op on Windows, so permission tests must be skipped there rather
than asserted around.

## Specs

`plainsong/spec_files/*.toml` state what the system promises;
`plainsong/selfcheck.py` holds the checks. They are separate from the tests
because a user runs them to find out what works on their machine, and the build
agent runs them to verify its own changes. A new capability wants a spec as well
as a test.

A `kind = "command"` check must write `{python}`, not `python3` — it substitutes
the interpreter actually running. Hardcoding `python3` passes in a checkout and
fails in every virtualenv and pipx install, reporting "No module named plainsong"
about a package that installed perfectly well.

**Anything read at runtime must live inside `plainsong/`.** A wheel carries only
what is under the package, and `[tool.setuptools.package-data]` must list it.
This is not theoretical: the specs sat in a top-level `specs/` directory and
`plainsong spec` reported "no specs found" to everybody who installed rather than
cloned — the self-verification the whole design leans on, quietly doing nothing.
The songbook had the same fault. Both now live in the package. If you add a new
kind of data file, add it to `package-data` and then prove it by installing the
built wheel into a fresh venv *outside the source tree* and running
`plainsong spec` there; see `docs/releasing.md`.

## `check` reads the prose, not just the `.song` files

`plainsong check` extracts fenced ```` ```plainsong ```` blocks out of markdown
and compiles them, with file:line reporting, and
`tests/test_notation.py::TestDocumentedNotation` fails if any documented example
stops compiling or stops making a sound.

A block tagged ```` ```plainsong ```` is a promise. Syntax that is only
proposed goes in ```` ```plainsong-proposed ````, and anything that is not
Plainsong should not claim to be. The three tutorials (`docs/tutorial-*.md` and
`docs/integration.md`) are held to this standard.

## Diagnostics come from two places

The parser produces some and the **arranger** produces others — an unreadable
chord becoming silence is found while arranging, not while parsing. Anything
reporting to a user has to ask for both. `cmd_check` showed only the parser's
for a long time, so the arranger's never reached anybody.

Related, and the reason that matters: an unrecognised token silently became a
rest. `Xm9` compiled "ok, 0 warnings" and produced a bar of nothing. It now
warns. Turning that on immediately found that `EbMaj7`, `G7alt` and `CM7` are
legitimate spellings the chord parser does not accept and has been quietly
dropping — still open, and it wants a spec and a changelog entry because it
changes how existing notation compiles.

## Changing the notation

Several thousand `.song` files in this repository depend on it, plus files we
cannot see. A change needs a failing-then-passing spec, a clean
a clean `plainsong check` over every source, and a `CHANGELOG.md` entry. If existing
notation would parse differently afterwards, that is breaking even if the new
reading is better: put it behind a setting and default to the old behaviour.

## Content directories

`plainsong/songbook/` (3,824 chord charts across a dozen languages, packaged and
shipped), `docs/fakebook-archive/` (2,484 more, not packaged), `docs/songs/`,
`docs/prose/`, `docs/traditions/`, `docs/training/`. Generated material: it
parses, but it is not all well written.

**The songbook is chord charts only, and must stay that way.** Melody and lyric
rows were stripped from all 6,309 files -- 41,990 rows -- because the documented
policy (full melody plus lyrics only for public-domain works) was not being met
and could not be enforced per title: nothing in the files records provenance,
and the genre directories lie. A 1979 R. D. Burman film song was filed under
`hindi/folk-traditional`. A chord progression is not protectable expression; a
tune and its words are. If you regenerate anything here, emit chords only, and
do not restore a melody without provenance to go with it. See
`docs/songbook.md`.

It lives inside the package because `plainsong library` and
`plainsong play stand-by-me` found nothing for anyone who had not cloned.

Two side effects worth knowing: the ~3,800 bar-count warnings this directory was
famous for came from those rows and are now 2.

## Rough edges

- The built-in synthesiser is a preview renderer; timbres are approximations.
  Audio is mono.
- The host bridge cannot stream and reports no token usage.
- **`plainsong/mcp/` also exists in `SuperInstance/plainsong-mcp`.** This is the
  one open violation of "one of everything" and it is deliberate but temporary:
  the extraction happened while this branch was in review. The intended end
  state is that the MCP server lives only in the sibling repository and this
  package stops carrying it. Until that lands, a change to one copy must be
  made to the other or they will drift — which is precisely the failure mode
  the rule exists to prevent. Do not build anything new on this copy.
- The MCP server has never had a third-party MCP client connect to it. Its
  protocol behaviour is verified by hand-driven JSON-RPC against the
  specification, which is strong evidence and not the same thing.

## Emitting notation must round-trip

`transform.to_text` writes notation that `parse` has to read back to the same
shape. It did not: a player row with options closed with `|` and then appended
` | vel: 70`, so the text carried `... | | vel: 70`, and the empty cell was read
as a real bar. Every transpose pushed each `@player` row one bar further out of
step with its section, and the resulting warning looked like the user's mistake.

`tests/test_notation.py::TestRoundTrip` holds the invariant: repeated
transposition does not change any row's width, and emitted text parses back to
the shape it came from. If you touch the emitter, that is the test to watch.

## Two words that used to be one

`plainsong stage` analyses what each listener on a physical stage hears. An
*ensemble session* is several agents co-authoring one score, and lives in
`plainsong-mcp`. These were both called "ensemble" at one point and it confused
everything written about either. Keep them apart.
