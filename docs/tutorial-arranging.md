# Arranging

For when a lead sheet is not enough: several players, other time signatures,
dynamics, and the stage model — the part of TapScript that has no equivalent
elsewhere.

Assumes you have been through [your first song](tutorial-first-song.md). Every
file and every number below was compiled and checked; the stage arithmetic is
worked through so you can verify it rather than trust it.

## A twelve-bar blues

Start with something with a shape. Chords, a melody, a walking bass and a
comping part:

```tapscript
**TRACK: 12-Bar Blues in G**
key: G | tempo: 96 | time: 4/4 | subdivision: 4th

[Blues] (12 Bars)
Chords: | G7 . . . | G7 . . . | G7 . . . | G7 . . . | C7 . . . | C7 . . . | G7 . . . | G7 . . . | D7 . . . | C7 . . . | G7 . . . | D7 . . . |
Melody: | G4 B4 D5 B4 | D5 . B4 G4 | A4 B4 D5 . | B4 A4 G4 . | C5 . . . | B4 C5 B4 A4 | G4 B4 D5 B4 | D5 . B4 . | D5 . . . | C5 . B4 A4 | G4 B4 D5 B4 | D5 . . . |
@bass   | g2 . . . | g2 . . . | g2 . . . | g2 . . . | c3 . . . | c3 . . . | g2 . . . | g2 . . . | d3 . . . | c3 . . . | g2 . . . | d3 . . . | vel: 70
@rhythm | g3 . g3 . | g3 . g3 . | g3 . g3 . | g3 . g3 . | c4 . c4 . | c4 . c4 . | g3 . g3 . | g3 . g3 . | d4 . d4 . | c4 . c4 . | g3 . g3 . | d4 . d4 . | vel: 85
```

```bash
tapscript check blues.tap --strict
tapscript compile blues.tap -o blues.mid --audio blues.wav
```

Two things worth noticing. The `[MetaData]` header is optional — the metadata
line on its own is enough. And every row has twelve bars: **rows within a
section should agree on length**, and `check` warns when they do not.

## Velocity

`vel:` after the closing `|` sets the row's velocity. Put a quiet part against a
loud one:

```
@bass   | g2 . . . | c3 . . . | vel: 40
@rhythm | g3 . g3 . | c4 . c4 . | vel: 100
```

The written value is the centre, not the exact number — a small deterministic
variation is applied so a part does not sound machine-stamped. Turn it off with
`core.humanize = false` if you are producing reference material rather than
music.

## Other time signatures

The bar-division rule does the work. In 3/4 a bar holds three beats, and the
tokens still divide whatever the bar is:

```tapscript
**TRACK: Waltz**
key: C | tempo: 100 | time: 3/4

[A] (4 Bars)
Chords: | C . . | F . . | C . . | G . . |
Melody: | C4 D4 E4 | F4 G4 A4 | E4 . . | G4 . . |
@bass   | c2 . . | f2 . . | c2 . . | g2 . . | vel: 70
```

And 6/8:

```tapscript
**TRACK: Jig**
key: G | tempo: 120 | time: 6/8

[A] (4 Bars)
Chords: | G . . . . . | D . . . . . | G . . . . . | D . . . . . |
Melody: | G4 A4 B4 C5 D5 E5 | D5 . . . . . | G4 . . B4 . . | A4 . . . . . |
```

## Proving the bar-division rule to yourself

Do not take it on faith. Put different token counts in adjacent bars and read
the note times out:

```bash
tapscript --json info bars.tap
```

At 120 bpm a 4/4 bar is 2 seconds. A bar with three tokens gives starts at 0,
0.667 and 1.333 seconds — triplets. A bar with four gives 0, 0.5, 1.0, 1.5. A
bar with twelve gives twelve even divisions of the same two seconds. The bar
never changes length; only how finely it is cut.

## Chords in a player row

Dashes stack pitches, and they start together:

```
@piano | c4-e4-g4 . . . | f4-a4-c5 . . . |
```

Read the timings back with `--json` and all three pitches in a stack carry the
same start time.

## The stage

This is the part that is genuinely unlike other notation. A score usually says
"beat 3" without saying *where* beat 3 happens — at the player's hands, at the
instrument, or at the ear it was written for. Declare a stage and TapScript
treats written times as **arrival** times, then solves backwards for when each
player must move.

```tapscript
**TRACK: Stage Timing Test**
key: C | tempo: 120 | time: 4/4 | subdivision: 4th

[Stage]
listener: conductor
temperature: 20
@piano:   pos 0,0   | speech: piano
@violin:  pos -3,2  | speech: bowed
@timpani: pos 4,-5  | speech: percussion

[Music] (2 Bars)
@piano   | C4 . . . | D4 . . . |
@violin  | C5 . . . | D5 . . . |
@timpani | C2 . . . | D2 . . . |
```

Note that inside `[Stage]` the player names **do** take a colon — it is a
settings block, not a row of music. Positions are metres, `x,y`.

```bash
tapscript stage stage_test.tap
```

```
Stage Timing Test  --  3 voices at 120 bpm
written for conductor, listening at conductor, 20 C, sound at 343.21 m/s

what each player has to do, solved against conductor
  voice    pos   speech      distance  onset  travel  p-centre  act
  piano    0,0   piano       0.0 m     8 ms   0 ms    6 ms      -14 ms
  timpani  4,-5  percussion  6.4 m     0 ms   19 ms   1 ms      -20 ms
  violin   -3,2  bowed       3.6 m     45 ms  10 ms   25 ms     -80 ms

what conductor hears, against the written beat
  spread 0 ms
```

### Check the arithmetic yourself

Take the violin. Its position is `-3,2`, so its distance from the conductor at
the origin is √(3² + 2²) = √13 = 3.61 m. Sound at 20 °C travels 343.21 m/s, so
that is 3.61 / 343.21 = **10.5 ms** of travel — the table says 10 ms.

A bowed string takes about 45 ms to speak from the moment the bow moves, and its
perceptual centre — the instant the ear decides the note *happened* — sits about
25 ms into it. So for the sound to reach the conductor on the beat, the player
must start:

```
0 − 45 (speech) − 10 (travel) − 25 (p-centre) = −80 ms
```

which is the `act` column. Every row checks out the same way. The timpani, twice
as far away, has roughly twice the travel; the piano, at the podium, has none.

### The thing that makes it more than arithmetic

Look at the last line: **spread 0 ms at the conductor**. All three arrive
together, which is what the score asked for.

Now ask what a player hears:

```
the same performance heard elsewhere
  audience                 spread 15 ms
  player:violin            spread ...
```

It is not zero. It cannot be. Each player is a different distance from everyone
else, so each hears a different performance — and every one of them is correct
about what they hear. This is why an orchestra watches the conductor rather than
listening to each other: the eyes carry the intention, the ears only carry
history.

### Rendering with and without compensation

```bash
tapscript compile stage_test.tap -o tight.mid
tapscript compile stage_test.tap -o smeared.mid --no-compensate
```

The first solves each player's emission backwards so the arrivals line up. The
second emits everything at the written time and lets the distances smear it —
which is what actually happens when an ensemble stops watching.

Without a `[Stage]` block none of this runs, and written times are taken at face
value. That default is what every existing `.tap` file relies on.

## Things that will catch you out

- **Player rows in music take no colon** (`@bass |`), but **in `[Stage]` they
  do** (`@bass: pos 0,0`). Music rows versus settings.
- **An unreadable chord becomes silence**, and only says so under `check`. Run
  `tapscript check --strict` after editing.
- **Swing does not change the MIDI.** It is a feel, meant to be heard, and MIDI
  carries emission times. Two files differing only in `swing:` produce the same
  MIDI and different audio.
- **Rows in a section should be the same number of bars.** A short row stops
  early rather than stretching, and `check` warns.
- **`subdivision:` and `time:` are different things.** The time signature sets
  the bar's length; the subdivision only sets the default note value when a row
  does not imply one.

## Next

- [Performance timing](performance.md) — the full stage model, listeners,
  conductor gestures
- [Notation reference](notation.md) — everything the parser accepts
