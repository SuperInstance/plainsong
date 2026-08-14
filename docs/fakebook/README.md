# TapScript Fake Book

Chord charts for well-known songs, in TapScript notation. Reference material for
agents learning the notation, and worked examples for anyone reading the format.

Each `.tap` file uses the `**TRACK:**` header with metadata (key, tempo, swing,
subdivision), section labels, and chord rows.

## Chord charts only, and why

**These files carry no melody and no lyrics.** A chord progression is not
protectable expression; a tune and its words are. Shipping thousands of
singable, playable transcriptions of songs still in copyright would be a
straightforward infringement, and the fact that a generator produced them
changes nothing.

The policy this project has always documented is *full melody plus lyrics only
for public-domain works, chord charts otherwise*. It was not being met: 1,902
files carried both, and a 1979 R. D. Burman film song sat under
`hindi/folk-traditional` — a misfiled genre was all it took to defeat the rule.

Rather than adjudicate copyright title by title across a dozen languages, where
one wrong "this one is public domain" is the error that costs, the reduction is
universal: 41,990 melody and lyric rows were removed from 6,309 files. If you
want a melody here, it has to arrive with its provenance established.

Two useful consequences: the bar-count warnings this directory was known for
fell from roughly 3,800 to 2, because they came from those rows; and the charts
still compile and still play, so they remain a real corpus to learn the notation
from.

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
