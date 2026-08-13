# TapScript notation reference

A file is a header, then sections. Rows inside a section say what each voice
plays. Bars are separated by `|`.

```
**TRACK: Harbour Lights**
[MetaData]
key: Am | tempo: 96 | swing: 0% | subdivision: 8th
time: 4/4 | mood: Reflective

[V1] (Verse - 4 Bars)
Chords: | Am . . . | F . . . | C . . . | G . . . |
Melody: | A4 . C5 E5 | F4 . A4 C5 | E4 . G4 C5 | D4 . F4 B4 |
Lyrics: | the tide  came | in  before  dawn | and  left  a | line  of  salt |
@bass   | a1 . e2 . | f1 . c2 . | c1 . g1 . | g1 . d2 . | vel: 70
```

## Header

`key:` `tempo:` `swing:` `subdivision:` on one line, `time:` and anything else
on the next. Both lines are optional; the defaults are C major, 100 bpm, 4/4.

- `key: Am` or `key: F# dorian`. Modes: major, minor, dorian, phrygian,
  lydian, mixolydian, locrian, harmonic minor, melodic minor.
- `tempo: 96` in beats per minute.
- `swing: 15%` delays every off-beat. 0% is straight, 100% is full triplet.
- `time: 3/4` — any metre, not just 4/4.

## Sections

`[V1] (Verse - 4 Bars)` — the name is what matters, the note in brackets is for
the reader. Sections play in the order they appear.

## Rows

| Row | Holds |
|---|---|
| `Chords:` | chord symbols: `Am`, `Cmaj7`, `F#m7b5`, `D/F#`, `G7sus4` |
| `Melody:` | pitches in scientific notation: `C4`, `A#3`, `Eb5` |
| `Lyrics:` | words, one bar per cell; never sounded, carried into the MIDI file |
| `@name` | a named player: pitches, with `-` stacking a chord: `a2-e3-a3` |

A `@name` row may end with `| vel: 70` to set its loudness (1-127), and
`| inst: upright bass` to set its instrument. Without one, the instrument is
guessed from the name: `@bass`, `@piano`, `@strings`, `@drums` all work.

`@name: upright bass, walk it under the chorus` — with a colon and no bars —
is a note to a human player. It is kept in the file and never sounded.

## Inside a bar

Tokens divide the bar between them. Four tokens in 4/4 are quarter notes;
three are triplets; six are sextuplets. You do not have to count to a grid.

- `.` holds the previous note for another slot.
- `(rest)` or `-` is silence.
- `C4~~~` extends one attack across four slots -- write duration as width.
- `a2-e3-a3` sounds together as a chord.

Two rows of the same kind in one section run one after another:

```
[Verse]
Melody: | C4 D4 E4 F4 | G4 A4 B4 C5 |
Melody: | C5 B4 A4 G4 | F4 E4 D4 C4 |
```

is eight bars of melody, not two bars played twice over.

## Relative dialect

Older files write harmony as roman numerals and melody as scale degrees,
against the key, with no row labels:

```
key: D minor
tempo: 65

[Verse]
| i . . . | iv . . . | V7 . . . | i . . . |
| 1 . 2 . | 3 . 2 . | 1 . 7 . | 6 . . . |
```

`^` raises an octave, `_` lowers it, `b`/`#` alter the degree. This dialect is
detected automatically. Write new material in the labelled form above.

## What to avoid

- Do not pad rows to a fixed token count. The bar divides itself.
- Do not put lyrics on a `Melody:` row; they will be read as pitches and dropped.
- Do not use `|` inside a lyric; it starts a new bar.
- Keep every row in a section the same number of bars unless you mean the
  short one to stop early.
