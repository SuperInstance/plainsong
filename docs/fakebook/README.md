# TapScript Fake Book

A collection of real songs transcribed into TapScript notation. These entries
serve as reference material for agents learning the notation and as educational
examples for anyone exploring TapScript Studio.

Each `.tap` file follows the modern `**TRACK:**` header format with metadata
(key, tempo, swing, subdivision), section labels, chords, melody lines, lyrics,
and `@player` performance notes.

## Index

| # | Song | Artist | Key | Tempo | Difficulty |
|---|------|--------|-----|-------|------------|
| 01 | [House of the Rising Sun](01-house-of-the-rising-sun.tap) | Traditional / Animals | Am | 120 | ★★☆☆☆ |
| 02 | [Wonderwall](02-wonderwall.tap) | Oasis | G | 87 | ★★☆☆☆ |
| 03 | [Hallelujah](03-hallelujah.tap) | Leonard Cohen | C | 60 | ★★★☆☆ |
| 04 | [Hotel California](04-hotel-california.tap) | Eagles | Bm | 75 | ★★★★☆ |
| 05 | [Knockin' on Heaven's Door](05-knockin-on-heavens-door.tap) | Bob Dylan | G | 70 | ★☆☆☆☆ |
| 06 | [Blowin' in the Wind](06-blowin-in-the-wind.tap) | Bob Dylan | C | 90 | ★☆☆☆☆ |
| 07 | [No Woman No Cry](07-no-woman-no-cry.tap) | Bob Marley | C | 76 | ★★★☆☆ |
| 08 | [Stand By Me](08-stand-by-me.tap) | Ben E. King | A | 120 | ★★☆☆☆ |
| 09 | [Mad World](09-mad-world.tap) | Gary Jules | F#m | 92 | ★★★☆☆ |
| 10 | [The Sound of Silence](10-the-sound-of-silence.tap) | Simon & Garfunkel | Am | 108 | ★★☆☆☆ |

## Difficulty Guide

- **★☆☆☆☆** — Beginner: 2–4 chords, simple progression, slow tempo
- **★★☆☆☆** — Easy: Standard progressions, moderate tempo, basic strumming
- **★★★☆☆** — Intermediate: Extended chords (7ths, sus), arpeggios, syncopation
- **★★★★☆** — Advanced: Complex progressions, fast arpeggios, modulations
- **★★★★★** — Expert: Virtuosic technique, complex rhythm, advanced harmony

## Usage

```bash
# Render any fake book entry to WAV
python3 scripts/tapscript_v2.py --cli docs/fakebook/01-house-of-the-rising-sun.tap --wav output/house.wav

# Render to MIDI
python3 scripts/tapscript_v2.py --cli docs/fakebook/03-hallelujah.tap --midi output/hallelujah.mid
```

## Conventions

- All songs are **simplified for educational purposes** — they are not
  note-perfect transcriptions but capture the essential chord progression,
  melody contour, and feel.
- Chord progressions use actual chord names (Am, C, G, F#m, etc.) rather
  than Roman numerals.
- `@player` lines describe performance instructions for specific instruments.
- Lyrics are included for at least the first verse and chorus.
- Tempos are approximate, matching the well-known recorded versions.

---

Part of [TapScript Studio](../..).
