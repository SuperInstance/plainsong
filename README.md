# TapScript

Music notation you can write in any text editor, read like a lead sheet, keep in
version control, and compile to MIDI and audio.

```
[V1] (Verse - 4 Bars)
Chords: | Am . . . | F . . . | C . . . | G . . . |
Melody: | A4 . C5 E5 | F4 . A4 C5 | E4 . G4 C5 | D4 . F4 B4 |
Lyrics: | the tide  came | in  before  dawn | and  left  a | line  of  salt |
@bass   | a1 . e2 . | f1 . c2 . | c1 . g1 . | g1 . d2 . | vel: 70
```

```
$ tapscript compile harbour.tap --audio harbour.wav --play
Harbour Lights  --  Am, 96 bpm, 4/4
2 sections, dialect: absolute
118 notes across chords (48), melody (32), bass (38)
length 40s
midi  harbour.mid
audio harbour.wav  [builtin/python]
```

## Why

Notation software is GUI-first and produces binary files. You cannot diff a
`.sib` in git, embed sheet music in a README, or generate a part from a script.

[ABC](https://abcnotation.com/) and [LilyPond](https://lilypond.org/) proved
plain-text notation works, but ABC is folk-centric and LilyPond is a
domain-specific language with a steep climb. Neither reads like a
[lead sheet](https://en.wikipedia.org/wiki/Lead_sheet) — the chord-chart-plus-melody
format working musicians actually use.

TapScript is plain-text lead sheet notation. Three principles, from the
[founding philosophy](proposals/00-FOUNDING-PHILOSOPHY.md):

1. **Plain text is the source of truth** — not a GUI, not a binary. It diffs, it
   merges, it lives in git.
2. **Lead sheet, not full score** — chords, melody, lyrics, named players.
3. **Compile, don't interpret** — the output is a standard MIDI file any DAW can
   read, with no runtime dependency on TapScript.

## Install

Python 3.10 or newer. Nothing else.

```bash
git clone https://github.com/SuperInstance/tapscript-studio
cd tapscript-studio
python3 -m tapscript --help
```

Or install it so `tapscript` is on your path:

```bash
pip install -e .
```

There are no required dependencies. The parser, the MIDI writer, the
synthesiser, the web interface and every model provider adapter are written
against the standard library. Optional extras — NumPy for faster synthesis,
fluidsynth for soundfont-quality audio, ffmpeg for mp3, mido for hardware MIDI —
are detected when present and never required. `tapscript doctor` shows what your
machine has and what each missing piece would add.

## Three ways in

```bash
tapscript compile song.tap --play     # command line
tapscript tui                         # terminal interface
tapscript serve                       # web interface at localhost:8765
```

All three drive the same compiler and see the same library and settings.

The terminal interface needs Python's `curses`, which Linux and macOS have and
stock Python on Windows does not — `pip install windows-curses` there, or use
the web interface, which needs nothing.

## Timing that models the room

A score usually says "this note is at beat 4.5" without saying where that
happens — at the player's hands, at the instrument, or at the ear it is written
for. Declare a stage and TapScript treats written times as **arrival** times and
solves backwards for when each player has to act:

```
[Stage]
listener: conductor
@timpani: pos 4,-9  | speech: percussion
@organ:   pos 0,-14 | speech: organ-large
```

```
$ tapscript ensemble orchestra.tap
  voice    distance  onset   travel  p-centre  act
  timpani  9.8 m     0 ms    29 ms   1 ms      -30 ms
  organ    14.0 m    140 ms  41 ms   60 ms     -241 ms

what conductor hears, against the written beat
  spread 0 ms
```

The organist's key goes down 241ms early so the pipe speaks on the beat. At the
podium everything lands together; at any player's desk it does not, which is why
an orchestra watches rather than listens. See
[docs/performance.md](docs/performance.md).

Without a `[Stage]` block none of this applies and written times are taken at
face value, exactly as before.

## Connect a model, if you want one

The compiler does not need a model. Adding one gives you an agent that writes
and revises notation, and a build agent that adapts the install to your setup.

```bash
tapscript setup
```

It works with hosted APIs (Anthropic, OpenAI, DeepSeek, OpenRouter, Gemini, xAI,
Groq, Mistral, Together, Fireworks, Cerebras, Azure), with local servers (Ollama,
LM Studio, vLLM, llama.cpp), and with **no key at all** when you are already
running inside another agent such as Claude Code or openclaw — it borrows the
model that is already there. Providers are catalogue entries rather than code, so
adding one is a JSON file. See [docs/providers.md](docs/providers.md).

```bash
tapscript agent "a slow waltz in D minor, piano and cello, sixteen bars"
tapscript build            # tailor this install to your machine and use case
```

## Many agents, one score

`tapscript mcp` serves the whole system over the Model Context Protocol, so any
MCP-capable client — Claude Code, an SDK client, a fleet of agents — can drive
it without shelling out to the CLI.

```bash
tapscript mcp                 # JSON-RPC over stdio, what most clients expect
tapscript mcp --http          # loopback HTTP, for remote and multi-agent setups
tapscript mcp --list-tools    # what it exposes
```

On top of that sits an ensemble session: several agents working on one score at
the same time, each owning a voice. Because the parts are disjoint the common
case never conflicts, and a write made against a stale version is refused and
handed the current state to rebase onto rather than overwriting somebody. See
[docs/mcp.md](docs/mcp.md) and [docs/ensemble.md](docs/ensemble.md).

## Documentation

| | |
|---|---|
| [Getting started](docs/getting-started.md) | From clone to a finished piece |
| [Notation reference](docs/notation.md) | The whole language |
| [Performance timing](docs/performance.md) | Stages, arrival times, conductor directives |
| [MCP server](docs/mcp.md) | Driving the system from any MCP client |
| [Ensemble sessions](docs/ensemble.md) | Several agents co-authoring one score |
| [Providers](docs/providers.md) | Connecting a model, adding your own |
| [Host bridge](docs/host-bridge.md) | Running under another agent, with no key |
| [Agents](docs/agents.md) | The composer and build agents, and their tools |
| [Connectors](docs/connectors.md) | Getting notation and audio into other systems |
| [Architecture](docs/architecture.md) | How it fits together, and why |
| [Specs](docs/specs.md) | The checks the system runs against itself |
| [Contributing](CONTRIBUTING.md) | Getting involved |

## The library

The repository carries several thousand `.tap` files — a fake book across a
dozen languages, teaching material, and worked examples.

```bash
tapscript library "waltz"
tapscript play stand-by-me
```

## Testing

```bash
python3 -m tapscript spec                          # the system's checks on itself
python3 -m unittest discover -s tests              # the test suite
python3 -m tapscript check docs examples academy   # every .tap file still parses
```

CI runs all three on Python 3.10 through 3.13 across Linux, macOS and Windows
with nothing installed, which is what keeps the no-dependencies promise honest.

## Relation to the fleet

| Component | Relationship |
|---|---|
| [tapscript-worker](https://github.com/SuperInstance/tapscript-worker) | Cloudflare Worker version of this compiler — runs TapScript on the edge |
| [fleet-jepa-midi](https://github.com/SuperInstance/fleet-jepa-midi) | Takes TapScript notation as input; JEPA perceives the feel. Its conductor-directive vocabulary is the one `tapscript conduct` speaks. |
| [fleet-ensemble](https://github.com/SuperInstance/fleet-ensemble) | Renders TapScript scores as agentic performances |
| [fleet-gateway](https://github.com/SuperInstance/fleet-gateway) | Routes model calls for the fleet |

## Status

Version 1.0. The notation, the CLI surface and the provider catalogue format are
stable; changes to them will go through a deprecation cycle.

`legacy/` holds the two earlier engines this replaced, along with the image
gallery, the MIDI studio and a set of unrelated Rust-to-Python ports. Nothing
imports them and they are not maintained; see [legacy/README.md](legacy/README.md).

## Licence

MIT. See [LICENSE](LICENSE).
