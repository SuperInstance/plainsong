# Architecture

## The shape

```
    notation text
         |
    [ parse ]         plainsong/notation/parser.py
         |            -> Score: sections, rows, tokens. Timing still implicit.
         |
    [ arrange ]       plainsong/notation/arrange.py
         |            -> Arrangement: notes with a start, a length and a voice.
         |
    +----+----+
    |         |
[ midi ]  [ audio ]   plainsong/render/
    |         |       -> a .mid file; samples, via the built-in synth or fluidsynth
```

Around that core:

| Package | Holds |
|---|---|
| `notation/` | theory, parser, arranger, the intermediate representation, the time grid, lyric binding, merge |
| `render/` | MIDI writer, synthesiser, voices, the SVG chart and its font metrics, optional backends |
| `runtime/` | paths, layered configuration, host capability probing |
| `llm/` | provider-neutral types, transport, catalogue, adapters |
| `agent/` | the loop, the tool registry, prompts |
| `connectors/` | ways in and out, plus plugin discovery |
| `interfaces/` | CLI, TUI, web, setup wizard, host bridge |
| `specs.py`, `selfcheck.py` | the system's checks on itself |

Everything above `notation/` and `render/` is optional. Deleting `llm/` and
`agent/` would leave a working compiler.

## Parsing and arranging are separate on purpose

The parser produces a faithful structural picture of the text and keeps tokens
as written. The arranger decides when things happen. Keeping them apart means a
parsing bug cannot produce silent notes and a timing bug cannot corrupt notation
that is written back out.

It is also what makes transposition correct: parse, rewrite tokens, emit. Every
row moves, including the chord row.

## One coordinate system for every token

Rows divide their bars independently, which is the point of the notation and
also means vertical alignment carries no meaning to the compiler. Write
`Melody: | A4 . C5 E5 |` over `Lyrics: | the tide came |` and `came` sits
directly beneath `C5` while sounding two thirds of a beat after it, because one
row divided the bar into four and the other into three.

`notation/timegrid.py` gives every written token a position — sounding or not —
computed by one function, so a lyric and a note are placed by the same
arithmetic. `Arrangement.grid` carries it. `unit` is the load-bearing field: a
token's position within its own bar, from 0.0 to just under 1.0.

Three separate problems become the same projection, and two of them are built:

- **Rendering.** `render/chart.py` places a chord at `x = unit * bar_width` — a
  coordinate transform rather than a layout engine, so a chart cannot disagree
  with the audio about when a chord arrives.
- **Merging.** `notation/merge.py` decides a conflict by set intersection on
  `(section, row, bar)`: two edits collide exactly when those sets overlap. The
  row axis is disjoint and player rows are keyed by name, so two agents on
  `@bass` and `Melody:` cannot collide — and, less obviously, neither can two
  agents rewriting bars 1–4 and 5–8 of *one* melody. That second case is what a
  coordinate per bar buys over a file per voice.
- **Linting**, not yet built. `grid.disagreements()` names each bar whose rows
  divide it differently, which is the `came`/`C5` lie stated as data. Nothing
  raises a diagnostic from it: uneven subdivision is legal and usually
  deliberate, so what to warn about is still an open question.

The grid observes; it does not steer. The arranger populates it from positions
it has already computed, so if building it ever moved a note, the grid would be
wrong. That is held by the corpus fingerprint rather than by intent.

## The timing rule

**A bar is one bar long, and whatever tokens a row puts in it divide it.**

Twelve tokens in a bar of four are triplets. Five are quintuplets. A
seventeenth token cannot spill into the next bar, because there is no next bar
to spill into.

The earlier engine gave every token a fixed grid slot instead, so a row that did
not contain exactly the expected number of tokens was cut short or written over
the bar after it — the two bugs recorded in
[`examples/edge-cases/BUGS.md`](../examples/edge-cases/BUGS.md). Both are covered
by specs now.

`core.bar_fill = "grid"` restores the old behaviour for files written around it,
and reports every token it drops rather than dropping them quietly.

Slot positions are computed from the start of the bar rather than accumulated,
so rounding cannot drift over a long piece and the last slot in a bar ends
exactly on the bar line.

## Rows that sound together, and rows that follow on

Rows of different kinds in one section sound together. A row repeated within a
section continues it, bar after bar, the way successive lines of a lead sheet
read. That single rule covers both the labelled dialect (`Chords:` and `Melody:`
playing at once) and the older unlabelled one (four pipe rows in a row being
sixteen bars, not four played four times).

## Two dialects, one parser

| | `absolute` | `relative` |
|---|---|---|
| Rows | labelled: `Chords:`, `Melody:`, `Lyrics:`, `@player` | unlabelled pipe tables |
| Harmony | chord symbols: `Am`, `Cmaj7` | roman numerals: `i`, `bVII`, `V7` |
| Melody | scientific pitch: `C4`, `a2-e3-a3` | scale degrees: `1`, `5^`, `b3_` |
| Resolved | at parse time | against the key, at arrange time |

The dialect is detected from the shape of the rows and can be forced with
`--dialect`. Both compile through the same arranger to the same representation.

Unlabelled rows are classified by shape, and the bar for that is deliberately
high: a row with no bar lines must be entirely musical before it is treated as
notation, because a line of prose in a section is more likely than a melody
someone forgot to label. A row that cannot be classified is reported and kept as
an annotation. Nothing is guessed at silently.

## Nothing is required

The core is written against the standard library, including the MIDI writer
(the SMF format is a few hundred bytes of documented structure) and the
synthesiser. A clone with nothing installed produces sound. This is checked by
CI on four Python versions and three operating systems with no `pip install`
step.

Optional pieces are found at runtime by `runtime/capabilities.py`, never
imported at module scope, and never required:

| Present | Used for |
|---|---|
| NumPy | vectorised synthesis, same audio about twenty times faster |
| fluidsynth + a soundfont | instrument-accurate rendering |
| ffmpeg | mp3, ogg, flac, m4a |
| mido | playing to hardware MIDI |
| an audio player | `plainsong play` |

The pure-Python synthesiser avoids per-sample Python loops: waveforms are built
once per voice and pitch as a short block of whole cycles and repeated,
envelopes are cached by length, and mixing runs through `map` with `operator`
callables so the inner loop stays in C. It is a preview renderer, and says so.

## Nothing is hardcoded

Every path is derived in `runtime/paths.py`: environment variable, then a
project-local `.plainsong/`, then the platform convention. No module may
hardcode a home directory — there is a test that greps for it, because the
previous version wrote everything to one contributor's `~/.openclaw`.

Configuration is layered: defaults, user file, project file, environment, flags.
`plainsong config list` shows the resolved values and where they came from.

Providers are catalogue entries rather than code. Adding a service that speaks
an existing wire format is a JSON file.

## One of everything

The previous version kept four copies of the General MIDI program table, four
CSS themes and four velocity-humanisation routines that had drifted apart. There
is now one of each: `plainsong/instruments.py`, one stylesheet in
`interfaces/web/app.html`, one arranger.

The three interfaces are thin. They all call `pipeline.compile_text`, so
"compile" cannot come to mean different things in the CLI and the web page.

## Specs

`specs/*.toml` state outcomes the system promises and name the checks that prove
them. `plainsong spec` runs them; the build agent runs them after making a
change, which is what lets it tell whether the change helped. See
[specs.md](specs.md).

## Determinism

Velocity humanisation uses a seeded RNG, the synthesiser's noise source is a
fixed sequence, and slot positions are computed rather than accumulated. The
same input produces byte-identical audio, which is what makes the render tests
meaningful.

## What was left behind

The two previous engines were separate implementations of the same idea, with
different notation, different internal representations, duplicated tables, both
hardcoding port 5557 and one contributor's home directory. They have been
deleted.
