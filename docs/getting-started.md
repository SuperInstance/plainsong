# Getting started

## Install

You need Python 3.10 or newer. Nothing else is required.

```bash
git clone https://github.com/SuperInstance/plainsong
cd plainsong
python3 -m plainsong --help
```

`pip install -e .` puts a `plainsong` command on your path. Every example below
works either way — `python3 -m plainsong` and `plainsong` are the same program.

Check what your machine offers:

```bash
plainsong doctor
```

Anything reported as missing is optional. The line under each one says what it
would add and how to install it.

## Your first piece

```bash
plainsong new "Harbour Lights" -o harbour.song
```

That writes a file you can open in any editor:

```
**TRACK: Harbour Lights**
[MetaData]
key: Am | tempo: 96 | swing: 0% | subdivision: 8th
time: 4/4 | mood: Open

[V1] (Verse - 4 Bars)
Chords: | Am . . . | F . . . | C . . . | G . . . |
Melody: | A4 . C5 E5 | F4 . A4 C5 | E4 . G4 C5 | D4 . F4 B4 |
Lyrics: | write the words | one bar at a time | the bar divides | itself |
@bass   | a1 . e2 . | f1 . c2 . | c1 . g1 . | g1 . d2 . | vel: 70
```

Compile it:

```bash
plainsong compile harbour.song --audio harbour.wav
```

And listen, if this machine can play audio:

```bash
plainsong compile harbour.song --play
```

If it cannot, you have a `.wav` and a `.mid` to open in anything else.

## Reading a piece before you change it

```bash
plainsong info harbour.song
```

```
Harbour Lights
  key      Am
  tempo    96 bpm
  metre    4/4
  sections 2
  length   20s
  notes    118
  voices   chords (nylon guitar), melody (piano), bass (electric bass)
```

`plainsong check` is the same reading, aimed at problems. Point it at a file or
a whole directory:

```bash
plainsong check harbour.song
plainsong check docs/fakebook --strict
```

Warnings are worth reading. The most common one — a row covering fewer bars than
the section around it — usually means a lyric line ran out before the chords
did, and that the piece will stop singing halfway through the verse.

## Editing

The notation is a text file; use your editor. Two rules cover most of it:

- Bars are separated by `|`. Whatever tokens you put inside a bar divide it
  between them, so you never count to a grid.
- `.` holds the note before it, `(rest)` is silence.

The full language is in [notation.md](notation.md). It is short.

## Changing key

```bash
plainsong transpose harbour.song Dm            # to standard output
plainsong transpose harbour.song +3 -i          # rewrite the file
```

Every row moves, including the chord row and the accompaniment.

## Browsing what is already here

The repository carries a few thousand pieces.

```bash
plainsong library                 # a sample
plainsong library "blues"         # search
plainsong library --collections   # what is in there
plainsong play stand-by-me        # play one by name
```

## The terminal interface

```bash
plainsong tui
```

Arrow keys move, `enter` loads, `c` compiles, `p` plays, `t` transposes,
`/` filters, `a` hands the piece to the agent, `?` lists the keys.

## The web interface

```bash
plainsong serve --open
```

An editor, the library, and the agent in a browser at `http://127.0.0.1:8765`.
It binds to loopback and refuses cross-origin requests; it is a local tool, not
a service to expose. `Ctrl`/`Cmd` + `Enter` compiles.

## Adding a model

Optional. The compiler does not use one. With one connected you get an agent
that writes and revises notation for you.

```bash
plainsong setup
```

Pick a provider, paste a key, done. If you are running inside another agent —
Claude Code, openclaw — choose `host` and it will use the model that is already
in the room, with no key of its own. See [providers.md](providers.md) and
[host-bridge.md](host-bridge.md).

```bash
plainsong agent "sixteen bars of slow blues in G, walking bass"
plainsong agent                 # no prompt: an interactive session
```

The agent writes into a workspace (`.plainsong/workspace` inside a project) and
cannot write anywhere else.

## Where things go

```bash
plainsong config list     # every setting and where it came from
plainsong config path     # the file to edit
plainsong config set render.sample_rate 22050
```

Output lands in `.plainsong/workspace/output` when you are inside a project, and
in your platform's data directory otherwise. `plainsong doctor` prints the exact
paths. Nothing is written outside them.

## When something is wrong

| Symptom | Try |
|---|---|
| `no such file or library entry` | the path is wrong, or the library index is stale — `plainsong library --refresh` |
| Compiles but silent | `plainsong info` — a piece with 0 notes usually has its melody on an unlabelled row |
| Audio is slow to render | `pip install numpy`, or `plainsong config set render.sample_rate 22050` |
| Audio sounds thin | install fluidsynth and a soundfont; `plainsong doctor` will then offer that backend |
| `no API key for ...` | `plainsong setup`, or use `--provider echo` to work offline |
| The agent stops early | raise `agent.max_steps`, or ask for less in one go |

`plainsong doctor --specs` runs the system's own checks and tells you which part
is not working.
