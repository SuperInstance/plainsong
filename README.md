# 🎵 TapScript Studio

**Plain-text music notation that looks like a lead sheet when printed, compiles to MIDI/WAV when rendered. Embeds in markdown like [mermaid](https://mermaid.js.org/) diagrams.**

> *Write music the way you write code — in plain text, in your editor, with version control.*

---

## Table of Contents

- [Vision](#vision)
- [Quick Start](#quick-start)
- [The Notation](#the-notation)
- [Architecture](#architecture)
- [Key Concepts](#key-concepts)
- [Components](#components)
- [Documentation](#documentation)
- [Testing](#testing)
- [Further Reading](#further-reading)
- [Relation to the Fleet](#relation-to-the-fleet)

---

## Vision

Music notation software is bloated. [MuseScore](https://musescore.org/), [Sibelius](https://www.avid.com/sibelius), [Finale](https://www.finalemusic.com/) — they're powerful, but they're GUI-first tools that produce binary files. You can't diff a `.sib` file in git. You can't embed sheet music in a README. You can't generate music from a script.

[ABC Notation](https://abcnotation.com/) and [LilyPond](https://lilypond.org/) proved that plain-text music notation works. But ABC is folk-centric (jigs and reels), and LilyPond is a [domain-specific language](https://en.wikipedia.org/wiki/Domain-specific_language) with a steep learning curve. Neither feels like writing a [lead sheet](https://en.wikipedia.org/wiki/Lead_sheet) — the chord-chart-plus-melody format that working musicians actually use.

**TapScript is plain-text lead sheet notation.** It looks like music when you read it. It compiles to [MIDI](https://en.wikipedia.org/wiki/MIDI) and [WAV](https://en.wikipedia.org/wiki/WAV) when you run it. It handles chords, melody, lyrics, multiple players, swing, and micro-timing — all in a format that fits in a markdown code block.

### Design Philosophy

TapScript follows three principles (see [Founding Philosophy](proposals/00-FOUNDING-PHILOSOPHY.md)):

1. **[Plain text is the source of truth](https://en.wikipedia.org/wiki/Plain_text)** — not a GUI, not a binary format. Text diffs cleanly, merges cleanly, and lives in git.
2. **[Lead sheet, not full score](https://en.wikipedia.org/wiki/Lead_sheet)** — chord symbols + melody + lyrics. The format working musicians use, not orchestral notation.
3. **[Compile, don't interpret](https://en.wikipedia.org/wiki/Compiler)** — TapScript compiles to standard MIDI, which any DAW or player can read. No runtime dependency on TapScript itself.

---

## Quick Start

```bash
# Clone the repo
git clone https://github.com/SuperInstance/tapscript-studio.git
cd tapscript-studio

# Start the web studio (port 5557)
python3 scripts/tapscript_v2.py

# Or compile from the command line
python3 scripts/tapscript_v2.py --cli mysong.tap --midi out.mid --wav out.wav

# Try a built-in example
python3 scripts/tapscript_v2.py --example harbor_dawn --wav harbor.wav
```

### Components

| Component | Port | Purpose |
|-----------|------|---------|
| [Image Gallery](scripts/gallery_v4.py) | 5555 | [Stable Diffusion](https://en.wikipedia.org/wiki/Stable_Diffusion) + [FLUX](https://blackforestlabs.ai/) image generation, img2img, albums |
| [MIDI Studio](scripts/midi_studio.py) | 5556 | Multi-track MIDI generation with [DeepSeek](https://www.deepseek.com) composer |
| [TapScript Studio](scripts/tapscript_v2.py) | 5557 | Plain-text notation → MIDI → WAV compiler |

Each component is a standalone Python web server. Run them independently — they share no code, only the filesystem.

---

## The Notation

### v2 Format (Absolute Pitch)

```tapscript
**TRACK: Neon Shadows**
[MetaData]
key: Am | tempo: 75 | swing: 10% | subdivision: 16th

[V1] (Verse - 4 Bars)
Chords:  | Am    .    | F     G    |
Melody: | E4    . . . | A4    . G4 E4 |
Lyrics: | I     . . . | write . in code |
@wesley | e2-a2-c3 . . | f2-a2-c3 g2-b2-d3 | vel: 60

[C] (Chorus - Louder)
Chords:  | Am    F     C     G    |
Melody: | A4    C5    A4    G4   |
@flash  | a2    f2    c2    g2   | vel: 80
@hermes | a1    .     a1    .    | vel: 75
```

### v1 Format (Roman Numeral / Scale Degree)

```tapscript
Key: Am
Tempo: 120
Swing: 0
Time: 4/4

[Intro]
| i . . . | i . . . | VI . . . | VII . . . |

[Verse]
| i  5 . 4 | 3 . 2 . | VI  1 . 7 | i . . . |
```

### Notation Elements

| Element | Syntax | Example | Meaning |
|---------|--------|---------|---------|
| **Chord** | Root + quality | `Am`, `F`, `G7`, `Cmaj9` | Standard [chord symbols](https://en.wikipedia.org/wiki/Chord_(music)) |
| **Melody note** | Pitch + octave | `E4`, `a2`, `C#5` | [Scientific pitch notation](https://en.wikipedia.org/wiki/Scientific_pitch_notation) |
| **Chord (melody)** | Hyphen-separated | `e2-a2-c3` | Multiple simultaneous pitches |
| **Sustain** | `.` | `| Am . . . |` | Hold previous event |
| **Rest** | `-` | `| Am - - - |` | Explicit silence |
| **Player line** | `@name` | `@wesley ...` | A named player's part |
| **Velocity** | `vel: N` | `vel: 80` | [MIDI velocity](https://en.wikipedia.org/wiki/MIDI#Messages) (1-127) |
| **Section** | `[Name]` | `[V1]`, `[C]`, `[Bridge]` | Named section header |
| **Bar separator** | `\|` | `\| Am  F  \| C  G  \|` | Bar line |

---

## Architecture

TapScript Studio is **three independent processes** — not a monolith. They share the filesystem but no code:

```
┌─────────────────────────────────────────────────────┐
│                 TapScript Studio                      │
│                                                       │
│  ┌─────────────────┐  ┌─────────────────┐           │
│  │  Image Gallery   │  │  MIDI Studio    │           │
│  │  (port 5555)     │  │  (port 5556)    │           │
│  │                  │  │                  │           │
│  │  SD 1.5 + FLUX   │  │  DeepSeek        │           │
│  │  img2img         │  │  multi-track     │           │
│  │  albums          │  │  composition     │           │
│  └────────┬────────┘  └────────┬────────┘           │
│           │                     │                     │
│           ▼                     ▼                     │
│  ┌────────────────────────────────────────┐          │
│  │         Filesystem (shared)             │          │
│  │  ~/.openclaw/workspace/output/          │          │
│  │    images/gallery/                      │          │
│  │    audio/                               │          │
│  └────────────────────────────────────────┘          │
│           ▲                                           │
│           │                                           │
│  ┌────────┴────────┐                                 │
│  │  TapScript v2    │                                 │
│  │  (port 5557)     │                                 │
│  │                  │                                 │
│  │  .tap → MIDI →   │                                 │
│  │  WAV compiler    │                                 │
│  └─────────────────┘                                 │
└─────────────────────────────────────────────────────┘
```

### Source Files

| File | Purpose |
|------|---------|
| [`scripts/tapscript_v2.py`](scripts/tapscript_v2.py) | v2 engine (absolute pitch notation) — the primary parser and compiler |
| [`scripts/tapscript.py`](scripts/tapscript.py) | v1 engine (Roman numeral notation) — legacy |
| [`scripts/midi_studio.py`](scripts/midi_studio.py) | Multi-track MIDI generation with AI composer |
| [`scripts/gallery_v4.py`](scripts/gallery_v4.py) | Image generation gallery |
| `scripts/generate_image*.py` | Image generation variants |
| `scripts/fakebook_generator.py` | [Fake book](https://en.wikipedia.org/wiki/Fake_book) generator |

### Python Modules (in `src/`)

| Module | Purpose |
|--------|---------|
| [`pulse_grid.py`](src/pulse_grid.py) | [Pulse-based timing grid](https://en.wikipedia.org/wiki/Pulse_(music)) — subdivides beats into slots |
| [`groove_tracker.py`](src/groove_tracker.py) | [Groove](https://en.wikipedia.org/wiki/Groove_(music)) analysis and swing computation |
| [`counterpoint_analyzer.py`](src/counterpoint_analyzer.py) | [Counterpoint](https://en.wikipedia.org/wiki/Counterpoint) rule checking |
| [`tradition_dna.py`](src/tradition_dna.py) | Musical tradition fingerprints ([stylistic DNA](https://en.wikipedia.org/wiki/Style_(music))) |
| [`genome.py`](src/genome.py) | Musical genome — genetic algorithm for variation |
| `swmidi8.py` | [Swing](https://en.wikipedia.org/wiki/Swing_(jazz_performance_style))-weighted MIDI 8th-note processor |

---

## Key Concepts

### Scientific Pitch Notation

TapScript uses [scientific pitch notation (SPN)](https://en.wikipedia.org/wiki/Scientific_pitch_notation) for melody notes: a letter (A-G), optional accidental (# or b), and an octave number. `C4` is middle C (MIDI note 60). `A4` is 440 Hz. `E2` is the low E on a guitar.

### Chord Symbols

Chords use standard [jazz/pop chord notation](https://en.wikipedia.org/wiki/Chord_(music)#Symbols):
- `Am` = A minor (A, C, E)
- `F` = F major (F, A, C)
- `G7` = G dominant 7th (G, B, D, F)
- `Cmaj9` = C major 9th (C, E, G, B, D)

### Swing

[Swing](https://en.wikipedia.org/wiki/Swing_(jazz_performance_style)) is the asymmetric subdivision of [eighth notes](https://en.wikipedia.org/wiki/Eighth_note) — the first eighth is longer than the second. TapScript's `swing: 10%` means the first eighth gets 55% of the beat and the second gets 45%. At `swing: 0%`, eighths are even (straight). At higher values, the feel becomes more [laid-back](https://en.wikipedia.org/wiki/Groove_(music)#Laid_back).

### Subdivision

The `subdivision` parameter determines the smallest rhythmic unit per beat:
- `8th` = 2 slots per beat (eighth notes)
- `16th` = 4 slots per beat (sixteenth notes)

More slots = more rhythmic detail possible in the melody.

### General MIDI

TapScript maps instrument names to [General MIDI](https://en.wikipedia.org/wiki/General_MIDI) program numbers. `@wesley` defaults to piano (program 0), `@flash` to guitar (program 24), `@hermes` to bass (program 33). These can be overridden in the notation.

---

## Testing

```bash
# Run the SWMIDI8 tests (swing-weighted MIDI processing)
python3 src/test_swmidi8.py

# Test the v2 parser with examples
python3 scripts/tapscript_v2.py --example neon_shadows --midi /tmp/test.mid
python3 scripts/tapscript_v2.py --example harbor_dawn --wav /tmp/test.wav

# Test the v1 parser
python3 scripts/tapscript.py --example creatures_of_interval
```

### Test Compositions

The repo includes [8 example compositions](examples/) covering different styles and notation features:
- `creatures_of_interval.tap` — v1 Roman numeral notation
- `the_room_is_safe.tap` — Lullaby in E minor
- `hermes_blues.tap` — 12-bar blues
- `neon_shadows.tap` — Multi-player v2 with chords, melody, lyrics
- `deck_work.tap` — Multi-section composition
- Spacing tests (`spacing-*.tap`) — Edge cases for melody duration algorithm

---

## Documentation

### Core Docs

| Document | Description |
|----------|-------------|
| **[Getting Started](docs/01-getting-started.md)** | Complete notation guide, CLI flags, and first composition |
| **[Architecture](docs/02-architecture.md)** | How the three processes work (and don't), notation grammar, file formats |
| **[API Reference](docs/03-api-reference.md)** | HTTP endpoints for the web studio |
| **[Creative Guide](docs/04-creative-guide.md)** | How to compose with TapScript — form, harmony, melody, groove |

### Design Proposals

| Document | Description |
|----------|-------------|
| **[Founding Philosophy](proposals/00-FOUNDING-PHILOSOPHY.md)** | Why plain-text notation, why lead sheets, why compile |
| **[Claude's Architecture Proposal](proposals/claude-architecture.md)** | Design session with Claude for the v2 format |
| **[Print Refinements](proposals/tapscript-print-refinements.md)** | Making the notation look better on paper |
| **[Plugin Architecture](proposals/tapscript-plugin-architecture.md)** | Future plugin system design |
| **[Melody Duration Spacing](proposals/melody-duration-spacing.md)** | The algorithm for note durations from sparse tokens |
| **[Examples](proposals/tapscript-examples.md)** | Annotated compositions |

### Academy

The [`academy/`](academy/) directory contains a structured curriculum for learning TapScript:
- [`exercises/`](academy/exercises/) — graded exercises
- [`assessments/`](academy/assessments/) — self-evaluation rubrics
- [`knowledge-base/`](academy/knowledge-base/) — concept deep-dives
- [`levels/`](academy/levels/) — progressive skill levels
- [`certifications/`](academy/certifications/) — completion badges

---

## Further Reading

### For Developers

- [TapScript Getting Started](docs/01-getting-started.md) — the complete notation guide
- [TapScript Architecture](docs/02-architecture.md) — how the compiler works
- [MIDI Specification](https://www.midi.org/specifications-old/item/the-midi-1-0-specification) — the binary format TapScript compiles to
- [Standard MIDI File Format](https://www.cs.cmu.edu/~music/cmsip/readings/Standard-MIDI-file-format-updated.pdf) — SMF spec (PDF)
- [pretty_midi Documentation](https://craffel.github.io/pretty-midi/) — the Python MIDI library used
- [SciPy WAV I/O](https://docs.scipy.org/doc/scipy/reference/generated/scipy.io.wavfile.write.html) — WAV file writing

### For Musicians

- [Lead Sheet (Wikipedia)](https://en.wikipedia.org/wiki/Lead_sheet) — the format TapScript implements
- [Chord Symbol Notation (Wikipedia)](https://en.wikipedia.org/wiki/Chord_(music)#Symbols) — how chords are written
- [Scientific Pitch Notation (Wikipedia)](https://en.wikipedia.org/wiki/Scientific_pitch_notation) — the note naming system
- [Swing (Jazz Performance Style)](https://en.wikipedia.org/wiki/Swing_(jazz_performance_style)) — what the swing parameter controls
- [The Real Book](https://en.wikipedia.org/wiki/Real_Book) — the canonical jazz lead sheet collection
- [Fake Book (Wikipedia)](https://en.wikipedia.org/wiki/Fake_book) — the tradition TapScript extends

### For Educators

- [ABC Notation](https://abcnotation.com/) — alternative plain-text notation (folk-centric)
- [LilyPond](https://lilypond.org/) — engraving-quality music typography from text
- [MusicXML](https://www.w3.org/2021/06/musicxml40/) — W3C standard for music notation interchange
- [Humdrum](https://www.humdrum.org/) — musicology toolkit for computational music analysis
- [Music21](https://web.mit.edu/music21/) — MIT's toolkit for computer-aided musicology

### For Mathematicians

- [Equal Temperament (Wikipedia)](https://en.wikipedia.org/wiki/Equal_temperament) — the tuning system MIDI uses
- [Set Theory in Music (Wikipedia)](https://en.wikipedia.org/wiki/Set_theory_(music)) — analyzing pitch collections
- [Allen Forte's Pitch-Class Set Theory](https://en.wikipedia.org/wiki/Pitch_class) — mathematical music theory
- [The Geometry of Musical Chords](https://en.wikipedia.org/wiki/Chord_(music)#Geometry) — Dmitri Tymoczko's work
- [Schenkerian Analysis](https://en.wikipedia.org/wiki/Schenkerian_analysis) — deep structure of tonal music

### For Engineers

- [Python `http.server` Module](https://docs.python.org/3/library/http.server.html) — how the web studio serves itself
- [NumPy Audio Processing](https://numpy.org/doc/stable/reference/generated/numpy.sin.html) — waveform generation
- [Digital Audio (Wikipedia)](https://en.wikipedia.org/wiki/Digital_audio) — sampling, quantization, Nyquist
- [ADSR Envelope (Wikipedia)](https://en.wikipedia.org/wiki/Envelope_(music)) — Attack, Decay, Sustain, Release

---

## Relation to the Fleet

| Component | Relationship |
|---|---|
| **[tapscript-worker](https://github.com/SuperInstance/tapscript-worker)** | Cloudflare Worker version of this compiler — runs TapScript on the edge |
| **[fleet-jepa-midi](https://github.com/SuperInstance/fleet-jepa-midi)** | Uses TapScript notation as input; JEPA perceives the feel |
| **[fleet-ensemble](https://github.com/SuperInstance/fleet-ensemble)** | Renders TapScript scores as agentic performances |
| **[fleet-gateway](https://github.com/SuperInstance/fleet-gateway)** | Routes the AI composer calls (MIDI Studio uses DeepSeek) |

---

## License

MIT — part of the [SuperInstance](https://github.com/SuperInstance) fleet.
