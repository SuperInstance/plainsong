# Plainsong for agents

You are probably reading this because you have been asked to write, read, or
change music in this notation. This document is the short version of what you
need, followed by the longer and more useful version: **the mistakes agents
actually make here**, every one of which was made by an agent working on this
repository and caught afterwards.

If you read only one section, read [What goes wrong](#what-goes-wrong).

## The contract in sixty seconds

```plainsong
**TRACK: Example**
[MetaData]
key: Am | tempo: 96 | time: 4/4

[V1] (Verse - 4 Bars)
Chords: | Am . . . | F . . . | C . . . | G . . . |
Melody: | A4 . C5 E5 | F4 . A4 C5 | E4 . G4 C5 | D4 . F4 B4 |
Lyrics: | the tide came | in before dawn | and left a | line of salt |
@bass   | a1 . e2 . | f1 . c2 . | c1 . g1 . | g1 . d2 . | vel: 70
```

Four facts do most of the work:

1. **A bar is one bar long, and its tokens divide it.** You never write
   durations. Three tokens in a 4/4 bar are triplets. Twelve are sixteenth-note
   triplets. A seventeenth cannot spill into the next bar.
2. **Rows of different kinds sound together. A repeated row runs on.** Two
   `Melody:` rows in one section are eight bars, not four played twice.
3. **Whitespace is decorative, and so is a column.** `|Am . . .|` and
   `|   Am    .     .     .   |` compile identically, so do not spend effort
   aligning columns unless a human will read the file. More importantly, do not
   *believe* a column: rows divide their bars independently, so a lyric written
   directly beneath a note need not sound with it. Three words under four melody
   tokens are thirds against quarters, and the third word lands two thirds of a
   beat late. `plainsong lyrics song.song` shows where each syllable really is;
   `core.lyrics = "bound"` puts them on their notes.
4. **A written time is an *arrival* time** — but only if the piece declares a
   `[Stage]`. Without one, written times are taken at face value and every
   existing file depends on that.

## Ask the tool; do not infer

Every command takes `--json`, and it works before or after the subcommand --
`plainsong --json info song.song` and `plainsong info song.song --json` are the
same command. Use it.

```bash
plainsong chord "G7alt" --explain     # what a symbol means, degree by degree
plainsong voicing "C13"               # which notes actually sound, and why those
plainsong lyrics song.song            # which note each syllable is sung on
plainsong chart song.song -o out.svg  # a chord chart you can embed in a document
plainsong info song.song --verbose    # every diagnostic available
plainsong check docs README.md        # compiles fenced blocks out of markdown too
plainsong fingerprint mysongs --check baseline.txt   # did anything change?
```

`plainsong chord --explain` exists specifically because guessing was cheaper
than checking, and that is how `EbMaj7` compiled to silence for months. It also
reports what is **absent** — `C7alt` says `no fifth` — and the absences are
often the point.

## What goes wrong

Everything in this section happened. None of it is hypothetical.

### Success is not evidence

The compiler is forgiving. Notation it cannot read becomes a rest, and the run
reports success. An agent asked to compile a score wrote this:

```
Title: Test
Tempo: 120
Section: A
Melody: C D E
```

None of that is Plainsong. It compiled, returned `isError=False`, and reported
"3 notes". The agent recorded a passing test.

**Check the note count and the diagnostics, not the exit code.** If you wrote
four bars and got three notes, you did not write four bars.

### A warning about the parser is not a warning about the file

An agent was asked to clear 85 warnings. Fifty-one came from one file full of
`I | 1 . 3 | 5 . . |` — roman numerals and scale degrees, the *relative*
dialect. It read the bare digits as generation artefacts and replaced all 51
with rests.

Every test passed. The warnings went to zero. The note count did not move. The
fingerprint changed by exactly the one file it was supposed to.

It had deleted a melody. The real defect was in `detect_dialect`, which never
looked at rows that begin with a label instead of a pipe. Told the right
dialect, that file yields 111 notes instead of 42.

**When a parser cannot read something, suspect the parser at least as hard as
you suspect the file.**

### Never re-record a baseline to make a check pass

`plainsong fingerprint` hashes what every file compiles to. CI fails if the
*music* changes, which `plainsong check` cannot see — flatten every major
seventh in the package by a semitone and `check` still reports `ok`.

`fingerprint --write` re-records the baseline. It is the single easiest way to
make CI green and it destroys the entire guarantee. If a fingerprint check
fails:

1. Look at the list of files it names.
2. Confirm it contains **exactly** the files you meant to change.
3. If a file you did not touch appears, stop — that is a bug in your work.
4. Only then re-record, and say in your commit message what moved and why.

### Do not find-and-replace on a word

An agent renaming things ran a replace on the word `minor` and rewrote 52 song
titles — *"Symphony No. 5 in C minor"* became *"Symphony No. 5 in Cm"* — across
193 files. All of it had to be reverted.

**Edit tokens between pipes. Never a `**TRACK:` line, a `key:` header, or a
section label.** Those carry human-readable text that looks like notation and
is not.

### Verify from somewhere neutral

Checking whether a published package contains a module, from inside the source
tree, tells you about the source tree. Python puts the working directory on
`sys.path`, so `import plainsong` finds the checkout and not the wheel.

This produced a confident, wrong "the module is present" in this repository.
**Run verification from `/tmp`, or anywhere that is not the project.**

### A tool that reports nothing has not told you nothing

Diagnostics come from two places. The parser produces some; the **arranger**
produces others, and the arranger's are the ones that matter most — an
unreadable chord becomes silence while arranging, not while parsing.

`transform.describe` arranged the score and then reported only the parser's
half, so `plainsong info --verbose` promised every diagnostic and delivered
some. A file whose only chord was `Xm9` reported `notes 0` and explained
nowhere. Fixed, but the shape recurs: when a tool tells you a file is fine and
the note count says otherwise, believe the note count.

### Say what you did not do

Reports that end "all tests pass, everything works" are the ones that turn out
to contain a deleted melody. The most useful thing you can write is the part you
could not verify, the thing you guessed at, and the file you left alone because
you were not sure.

An unresolved item in a report is fine. A confident wrong answer is expensive.

## Alignment

### Copyright

The bundled songbook is **chord charts only** — no melody rows, no lyric rows.
A chord progression is not protectable expression; a tune and its words are.
41,990 rows were removed from 6,309 files to make that true.

If you generate or regenerate material here, **emit chords only.** Do not
restore a melody or lyrics without provenance establishing the work is public
domain. The genre directories are not provenance — a 1979 film song was filed
under `folk-traditional`, and that misfiling was all it took to defeat the
policy for years.

### Do not invent the language

An earlier tutorial set taught four different invented syntaxes — a
bouncing-ball physics simulation, variables and operators, a bytecode compiler
that has never existed — because generating plausible-looking lessons is easier
than generating correct ones. Fourteen of seventeen documented examples compiled
to zero notes.

Everything in a fenced ```` ```plainsong ```` block is compiled by CI. If you
write one, it must work. If you are proposing syntax that does not exist yet,
tag it ```` ```plainsong-proposed ```` instead.

### Changing the notation is a breaking change

Several thousand `.song` files here depend on it, plus files nobody here can
see. A notation change needs a failing-then-passing spec, a clean
`plainsong check` over every source, and a `CHANGELOG.md` entry. If existing
notation would parse differently afterwards, that is breaking **even if the new
reading is better** — put it behind a setting and default to the old behaviour.

## Driving it programmatically

```python
from plainsong import pipeline
result = pipeline.compile_text(text, midi=Path("out.mid"))
result.ok            # False if it failed
result.diagnostics   # what it could not read -- always look at this
result.summary()     # dict, the same shape as --json
```

There is also an MCP server in
[plainsong-mcp](https://github.com/SuperInstance/plainsong-mcp): 27 tools, 9
resources, 2 prompts over JSON-RPC on stdio or loopback HTTP. It carries an
**ensemble session** so several agents can co-author one score — each owns a
voice, writes carry the version they were made against, and a stale write is
refused and handed the current state to rebase onto. See
[docs/ensemble.md](docs/ensemble.md).

## Where to look next

| | |
|---|---|
| [docs/notation.md](docs/notation.md) | The full syntax |
| [docs/chords.md](docs/chords.md) | Every chord spelling, and the rules that derive the notes |
| [docs/voicing.md](docs/voicing.md) | Which notes sound when a chord names more than fit |
| [docs/lyrics.md](docs/lyrics.md) | Binding syllables to notes, and why a column is not a promise |
| [docs/chart.md](docs/chart.md) | Drawing a chord chart, and what it deliberately is not |
| [docs/integration.md](docs/integration.md) | `--json`, the Python API, HTTP, MCP |
| [docs/performance.md](docs/performance.md) | Arrival-centric timing and the `[Stage]` block |
| [CLAUDE.md](CLAUDE.md) | How the codebase is organised, and why each rule exists |

Every rule in `CLAUDE.md` is a fault that was actually paid for. It is worth
reading before changing anything, for the same reason this document is worth
reading before writing anything.
