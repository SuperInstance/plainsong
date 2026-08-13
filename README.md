# 🎵 TapScript Studio

Plain-text music notation that looks like a lead sheet when printed, compiles to MIDI/WAV when rendered. Embeds in markdown like mermaid diagrams.

## Quick Start

```bash
# Image Gallery (port 5555)
python3 scripts/gallery_v4.py

# MIDI Studio (port 5556)
python3 scripts/midi_studio.py

# TapScript Studio (port 5557)
python3 scripts/tapscript.py
```

## The Format

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
Chords:  | Am    F     C     G    | Am    F     C     G    |
Melody: | A4    C5    A4    G4   | A4    C5    D5    E5   |
Lyrics: | This  is    the   new  | syn   -     tax   for  |
@flash  | a2    f2    c2    g2   | a2    f2    c2    g2   | vel: 80
@hermes | a1    .     a1    .    | f1    .     g1    .    | vel: 75
```

## Components

| Component | Port | Purpose |
|-----------|------|---------|
| Image Gallery | 5555 | SD 1.5 + DeepInfra FLUX generation, img2img, albums, resident artist |
| MIDI Studio | 5556 | Multi-track MIDI generation with DeepSeek composer |
| TapScript | 5557 | Plain-text notation → MIDI → WAV compiler |

## Documentation

- [Founding Philosophy](proposals/00-FOUNDING-PHILOSOPHY.md)
- [Claude's Architecture Proposal](proposals/claude-architecture.md)
- [Print Refinements](proposals/tapscript-print-refinements.md)
- [Plugin Architecture](proposals/tapscript-plugin-architecture.md)
- [Example Compositions](proposals/tapscript-examples.md)
- [Image API Reference](scripts/IMAGE_API.md)
