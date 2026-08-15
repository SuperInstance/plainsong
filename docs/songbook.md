# The songbook

Chord charts for well-known songs, in TapScript notation. Reference material for
agents learning the notation, and worked examples for anyone reading the format.

Each `.tap` file uses the `**TRACK:**` header with metadata (key, tempo, swing,
subdivision), section labels, and chord rows.

## Where it lives

| | |
|---|---|
| `tapscript/songbook/` | 3,824 charts. **Inside the package**, so they ship in the wheel. |
| `docs/fakebook-archive/` | 2,484 more. Not packaged — available to a clone only. |

The packaged half is inside `tapscript/` for the same reason the specs are: a
wheel carries only what is under the package. Kept in `docs/`, the whole library
was invisible to anyone who installed rather than cloned — `tapscript library
"waltz"` said nothing found, and `tapscript play stand-by-me`, which the README
advertises, could not work at all.

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
Nothing in the files records provenance, so no rule could separate the
public-domain works from the rest.

Rather than adjudicate copyright title by title across a dozen languages, where
one wrong "this one is public domain" is the error that costs, the reduction is
universal: 41,990 melody and lyric rows were removed from 6,309 files. If you
want a melody here, it has to arrive with its provenance established.

If you regenerate any of this, emit chords only.

One trap, if you write the stripper yourself. A blacklist does not work. Matching
`Melody:` and `Lyrics:` literally misses `Melody (8th):`, and it misses bare
lyric lines that carry no row label at all. Keep the rows you recognise as
chords and drop everything else.

Two useful consequences: the bar-count warnings this directory was known for
fell from roughly 3,800 to 2, because they came from those rows; and the charts
still compile and still play, so they remain a real corpus to learn the notation
from.

## Index

The nine hand-written entries at the top of `tapscript/songbook/`. Everything
else is generated and reached through `tapscript library`.

| # | Song | Artist | Key | Tempo | Difficulty |
|---|------|--------|-----|-------|------------|
| 01 | [House of the Rising Sun](../tapscript/songbook/01-house-of-the-rising-sun.tap) | Traditional / Animals | Am | 120 | ★★☆☆☆ |
| 02 | [Wonderwall](../tapscript/songbook/02-wonderwall.tap) | Oasis | G | 87 | ★★☆☆☆ |
| 03 | [Hallelujah](../tapscript/songbook/03-hallelujah.tap) | Leonard Cohen | C | 60 | ★★★☆☆ |
| 04 | [Hotel California](../tapscript/songbook/04-hotel-california.tap) | Eagles | Bm | 75 | ★★★★☆ |
| 05 | [Knockin' on Heaven's Door](../tapscript/songbook/05-knockin-on-heavens-door.tap) | Bob Dylan | G | 70 | ★☆☆☆☆ |
| 06 | [Blowin' in the Wind](../tapscript/songbook/06-blowin-in-the-wind.tap) | Bob Dylan | C | 90 | ★☆☆☆☆ |
| 07 | [No Woman No Cry](../tapscript/songbook/07-no-woman-no-cry.tap) | Bob Marley | C | 76 | ★★★☆☆ |
| 08 | [Stand By Me](../tapscript/songbook/08-stand-by-me.tap) | Ben E. King | A | 120 | ★★☆☆☆ |
| 10 | [The Sound of Silence](../tapscript/songbook/10-the-sound-of-silence.tap) | Simon & Garfunkel | Am | 108 | ★★☆☆☆ |

## Difficulty guide

- **★☆☆☆☆** — Beginner: 2–4 chords, simple progression, slow tempo
- **★★☆☆☆** — Easy: Standard progressions, moderate tempo, basic strumming
- **★★★☆☆** — Intermediate: Extended chords (7ths, sus), arpeggios, syncopation
- **★★★★☆** — Advanced: Complex progressions, fast arpeggios, modulations
- **★★★★★** — Expert: Virtuosic technique, complex rhythm, advanced harmony

## Usage

You do not need to know where a file is. Search by title, key or collection:

```bash
tapscript library "waltz"          # search
tapscript library --collections    # what is in here
tapscript play stand-by-me         # render and play by name
```

Or compile one directly:

```bash
tapscript compile tapscript/songbook/01-house-of-the-rising-sun.tap \
  -o rising-sun.mid --audio rising-sun.wav
```

## Conventions

- All songs are **simplified for educational purposes** — they are not
  note-perfect transcriptions but capture the essential chord progression and
  feel.
- Chord progressions use actual chord names (Am, C, G, F#m, etc.) rather than
  Roman numerals.
- `@player` lines describe performance instructions for specific instruments.
- Tempos are approximate, matching the well-known recorded versions.
- This is generated material. It parses; it is not all well written.

---

Part of [TapScript Studio](..).
