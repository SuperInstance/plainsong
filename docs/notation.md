# Plainsong notation reference

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
- `swing: 66%` — see [Swing](#swing).
- `time: 3/4` — any metre, not just 4/4.

## Sections

`[V1] (Verse - 4 Bars)` — the name is what matters, the note in brackets is for
the reader. Sections play in the order they appear.

## Rows

| Row | Holds |
|---|---|
| `Chords:` | chord symbols: `Am`, `Cmaj7`, `F#m7b5`, `D/F#`, `G7sus4` |
| `Melody:` | pitches in scientific notation: `C4`, `A#3`, `Eb5` |
| `Lyrics:` | words, one bar per cell; never sounded, carried into the MIDI file. See [lyrics.md](lyrics.md) — a word does **not** sound with the note it is written under unless you ask it to |
| `Vel:` | dynamics for the row above it: numbers, `pp`–`ff`, `+10`/`-8`, `cresc`/`dim`. See [Dynamics](#dynamics) |
| `AnyName:` | an annotation layer over the row above it — any dimension you can name. See [Annotation rows](#annotation-rows) |
| `@name` | a named player: pitches, with `-` stacking a chord: `a2-e3-a3` |

A `@name` row may end with `| vel: 70` to set its loudness (1-127), and
`| inst: upright bass` to set its instrument. Without one, the instrument is
guessed from the name: `@bass`, `@piano`, `@strings`, `@drums` all work.

`@name: upright bass, walk it under the chorus` — with a colon and no bars —
is a note to a human player. It is kept in the file and never sounded.

## Dynamics

`vel: 70` sets a whole row to one loudness. Two finer controls exist, and they
combine: the row sets a base, the marks below it shape that base note by note,
and a mark written on a token itself wins over both.

A `Vel:` row marks the playable row directly above it. The k-th token of a
`Vel:` cell holds the k-th token of that bar, so a mark sits under the note it
shapes — and a `.` holds its column, exactly the way `.` holds a note.

```plainsong
[Verse]
Melody: | C4 . E4 G4 | A4 G4 E4 C4 |
Vel: | mf . cresc . | f . dim p |
```

A `Vel:` cell holds:

| Mark | Means |
|---|---|
| `72` | that note sounds at MIDI velocity 72 (1-127) |
| `mf`, `f`, `pp` … | the usual ladder: pp 32, p 48, mp 64, mf 80, f 96, ff 112 |
| `+10`, `-8` | a change riding on whatever came before |
| `!` | an accent: twenty louder |
| `cresc`, `dim` | ramp to the next explicit value in the row — or, if the row never names one, to 24 louder or softer, reached on the row's last note |
| `.` | hold the column; the note keeps the dynamic in hand |

Dynamics hold until the next one, the way they do on paper: `| p . . f |`
plays piano for three notes and forte on the fourth. A mark standing over a
sustain or a rest does nothing. Marks beyond the row's own tokens warn and do
nothing.

A mark can also ride on the token itself: `C4!` accents that note by twenty,
`C4@99` plays it at exactly 99, and both work on chord symbols and stacks
(`Am!`, `a2-e3-a3@64`) in either dialect. Marks go before any sustains —
`C4!~~~`, not `C4~~~!` — and travel with the note through transposition.

## Annotation rows

`Vel:` is one instance of a general thing: **any row you can name**. A
labelled row of bar-aligned cells that the compiler does not otherwise play —
`Breath:`, `Mute:`, `Gaze:`, `Emotion:` — is an annotation layer over the
playable row above it, parsed as first-class data: preserved, addressable,
and round-tripped. If a composer doesn't need a row, it isn't there; nothing
phantom is constructed. A row the compiler cannot interpret is data, not an
error — unknown names never warn and never change a note of the compile.

```plainsong
[Verse]
Melody: | A4 . C5 E5 | G4 . E5 . |
Breath: | 1.0 . 0.6 0.9 | . 0.8 . . |
Gaze: | far . near . | . close . . |
```

The alignment is the alignment `Vel:` and `Lyrics:` use — the k-th token of a
layer's cell holds the k-th token of that bar, `.` holds its column — so a
value sits under the event it describes rather than merely looking like it
does. Every value carries its resolved address in the arrangement: which
voice, which bar, which beat window, which target token — the same arithmetic
that timed the notes, which is what lets a consumer join on it:

```python
from plainsong.notation import arrange, parse
from plainsong.features import annotation_stats

arrangement = arrange(parse(text))
for mark in arrangement.annotations:
    print(mark.name, mark.token, mark.voice, mark.bar, mark.onset, mark.target)
# Breath 1.0 melody 0 0.0 A4
# Breath 0.6 melody 0 2.0 C5
annotation_stats(arrangement, "Breath")  # {'count': 4, 'mean': 0.825, ...}
```

A layer marks the nearest playable row (`Chords:`, `Melody:`, `@player`)
above it. To name the row it marks instead — useful when the layer is written
elsewhere, or two voices need separate layers of one dimension — end the row
with `on:`, the same way a player row ends with `vel: 70`:

```plainsong
[Verse]
Breath: | deep . light . | on: @bass
Chords: | Am . F . |
@bass | a1 . e2 . | vel: 70
```

Layers own no time, never count as a voice, survive transposition untouched
(the values stay under the notes they were written for), and pass through
`plainsong transpose` and back. `Vel:` is simply the built-in layer whose
values have MIDI velocity semantics; a new semantic for a new name is
registered in one table, `plainsong.notation.annotations.ANNOTATION_SEMANTICS`,
and unregistered names stay data forever.

## Perf blocks

A `Vel:` row marks the row above it, positionally. A `[Perf]` block marks
the whole take: **channel tables over a voice's own notes, written anywhere
in the file**. Where annotation layers are prose over the chart, `[Perf]` is
the performance — what the player does with the notes, bar by bar.

```plainsong
[V1]
@piano | C3-G3-D4 . E4 G4 (rest) C5 . . | vel: 82

[Perf]
@piano.vel | 96 . 64 40 . 112 . . |
@piano.ache | 0.2 . 0.8 1.0 . 0.4 . . |
```

One row is one *channel* of one *voice*. `@piano.vel` marks the player
named piano; a row kind written bare (`melody.vel`) marks that row instead.
The cells are bar-aligned and the alignment is the same walk `Vel:` uses:
the k-th token of a cell holds the k-th token of that voice's bar, `.` holds
its column, and a voice that runs across several rows or sections is one
stream, marked in order. A stack (`C3-G3-D4`) is one attack and takes one
value.

Values are **literals — numbers only**. A curve in v1 is an explicit value
list; expressions, and everything they would buy, arrive in v2.

`vel` is the one channel with compilation semantics: it drives per-note
MIDI velocity. Precedence is deliberate and one line: **a `[Perf]` value
wins; a `.` leaves whatever else said standing.** The take speaks over the
chart, but only where it has something to say — row `vel:`, `Vel:` marks and
inline `@n`/`!` marks all survive underneath a spacer column.

Any other channel is data: kept, addressed like an annotation (voice, bar,
beat window, target token — on `arrangement.perf`), and with zero effect on
the compile. Registering a new channel semantic happens in one table,
`plainsong.notation.perf.CHANNEL_SEMANTICS`, the same contract annotation
layers use. The block is read, not played — like `[Stage]`, it never joins a
section — and it survives `plainsong transpose` and back, so a transposed
take keeps its channels.

## Swing

`swing:` names the share of a beat the *long* note of each eighth-note pair
occupies. 50% is straight — the pair splits the beat in half. 66% is
approximately a triplet, 75% is dotted. Anything at or below 50% reads as
straight; anything above 90% is held at 90%, past which the short eighth
stops being a note.

Swing is a playback decision. Only the eighth-note off-beat moves — every
other position, in every metre, stays exactly where it was written — and
notes stretch to meet the moved off-beat, so a pair sounds long-short rather
than merely late. A tie onto the half-beat stretches with it; a rest there
leaves a hole exactly as written; nothing crosses a bar line late. The
notation's own timing — the grid, the chord chart, where lyrics land — is
unchanged, which is why two files differing only in `swing:` compile to the
same chart.

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
- **Do not trust a lyric's column.** Rows divide their bars independently, so a
  word written directly beneath a note need not sound with it: three words under
  four melody tokens are thirds against quarters. `plainsong lyrics song.song`
  shows which note each syllable actually lands on, and
  `core.lyrics = "bound"` makes them land on the notes they are written under.
  See [lyrics.md](lyrics.md).
- Keep every row in a section the same number of bars unless you mean the
  short one to stop early.


## Metre

`time: 3/4` and `time: 6/8` work the same way as `4/4`: a bar is a bar, and the
tokens in it divide it. The metre changes how long a bar lasts, not how you
write one.

## Two rows of the same kind

Rows of *different* kinds sound together. A row repeated within one section
continues it:

```
[Verse]
Chords: | Am | F |
Chords: | C | G |
Melody: | A4 C5 | F4 A4 |
Melody: | E4 G4 | D4 F4 |
```

Four bars, chords and melody together throughout.

## Sustain, rests and duration

| Token | Means |
|---|---|
| `.` | hold the previous note through this slot |
| `(rest)`, `-`, `r` | silence |
| `(hold)` | hold — the same as `.`, for readability |
| `C4~~~` | one attack lasting four slots |
| `a2-e3-a3` | three notes sounding together |

A parenthesised direction where a note should be — `(hold 4 beats)`, `(let ring)`
— holds the previous note and is kept in the file for the reader.

## Rows without bar lines

A row with no `|` at all is read at the subdivision unit, so width is duration:

```
[Verse]
Melody: C4~~~ D4~~~ E4~~~ F4~~~
```

Each token is one eighth plus one per `~`, so that line is four half notes. This
is the older duration-by-spacing style; the barred form above is easier to keep
aligned and is what `plainsong new` writes.

## Diagnostics

`plainsong check` reports three levels:

- **error** — the file will not compile. Nothing is written.
- **warning** — it compiles, but something will probably not sound as intended:
  a row shorter than its section, a bar overfilled in `grid` mode, a velocity
  that is not a number.
- **info** — a row was kept but not played, such as an unrecognised label.

A row the parser cannot classify is never guessed at. It is reported and kept as
an annotation, because a silently dropped melody is worse than a warning.
