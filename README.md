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

## Documentation

| | |
|---|---|
| [Getting started](docs/getting-started.md) | From clone to a finished piece |
| [Notation reference](docs/notation.md) | The whole language |
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

## Status

Version 1.0. The notation, the CLI surface and the provider catalogue format are
stable; changes to them will go through a deprecation cycle.

`legacy/` holds the two earlier engines this replaced. Nothing imports them and
they are not maintained; see [legacy/README.md](legacy/README.md).

## Licence

MIT. See [LICENSE](LICENSE).
