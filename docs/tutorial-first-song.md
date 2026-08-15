# Your first song

Thirty minutes, start to finish. You will end with a piece you wrote, a MIDI
file any DAW opens, and enough of the notation to keep going without this page.

Every command and every output below was run against an installed build. If
something here does not match what you see, that is a bug in this document.

## Before you start

Python 3.10 or newer. Nothing else.

```bash
pip install tapscript
```

Working from a clone instead? `pip install -e .` in the repository does the
same thing.

## 1. Make something that already works

Do not start from an empty file. Start from one that plays:

```bash
tapscript new "Ocean Diner" -o ocean.tap
```

```
ok  wrote ocean.tap
next: tapscript compile ocean.tap --audio out.wav
```

Open it. This is the whole language, and you can read it before anyone explains
it:

```tapscript
**TRACK: Ocean Diner**
[MetaData]
key: Am | tempo: 96 | swing: 0% | subdivision: 8th
time: 4/4 | mood: Open

[V1] (Verse - 4 Bars)
Chords: | Am . . . | F . . . | C . . . | G . . . |
Melody: | A4 . C5 E5 | F4 . A4 C5 | E4 . G4 C5 | D4 . F4 B4 |
Lyrics: | write the words | one bar at a time | the bar divides | itself |
@bass   | a1 . e2 . | f1 . c2 . | c1 . g1 . | g1 . d2 . | vel: 70

[CH] (Chorus - 4 Bars)
Chords: | F . . . | G . . . | Am . . . | Am . . . |
Melody: | F4 . A4 C5 | G4 . B4 D5 | A4 . C5 E5 | A4 . . . |
@bass   | f1 . c2 . | g1 . d2 . | a1 . e2 . | a1 . . . | vel: 74
```

Four rows that line up. `|` separates bars. `.` means "nothing new starts
here". Pitches carry an octave: `A4` is the A above middle C.

## 2. Hear it

```bash
tapscript compile ocean.tap -o ocean.mid --audio ocean.wav --play
```

```
Ocean Diner  --  Am, 96 bpm, 4/4
2 sections, dialect: absolute
61 notes across chords (24), melody (22), bass (15)
length 20s
midi  ocean.mid
audio ocean.wav  [builtin/python]
```

If it says `no audio player found`, both files were still written — open
`ocean.wav` however you normally would. Nothing failed.

**Pass `-o` if you want the MIDI beside your file.** Without it the MIDI goes
into the workspace and the command prints the full path. `tapscript doctor`
shows where that is.

## 3. Change something and hear it again

This is the loop. Everything else is detail.

Open `ocean.tap` and change the first chord of the verse from `Am` to `Dm`.
Change `tempo: 96` to `tempo: 120`. Recompile:

```bash
tapscript compile ocean.tap -o ocean.mid --audio ocean.wav
```

```
Ocean Diner  --  Am, 120 bpm, 4/4
2 sections, dialect: absolute
61 notes across chords (24), melody (22), bass (15)
length 16s
```

Same note count, shorter piece — the tempo went up, so the same music takes
less time. That is the sanity check worth internalising: when you change one
thing, exactly one number should move.

## 4. Add a player

Any row starting `@` is a new voice and becomes its own MIDI track. Add this to
the verse:

```
@piano  | a3-c4-e4 . . . | f3-a3-c4 . . . | c3-e3-g3 . . . | g3-b3-d4 . . . | vel: 60
```

Dashes stack pitches into a chord — those three notes start together.

```
72 notes across chords (24), melody (22), bass (15), piano (11)
```

A new voice appeared. **Write `@piano |`, not `@piano: |`** — a colon after the
name is the single most common beginner mistake, and the row will not be read
as a player.

## 5. Add a section

Sections are `[TAG] (Description)`. The tag is yours. Add a bridge:

```tapscript
[BR] (Bridge - 4 Bars)
Chords: | Dm . . . | Dm . . . | E7 . . . | E7 . . . |
Melody: | D4 . F4 A4 | C5 . A4 F4 | E4 . G#4 B4 | E5 . . . |
```

Recompile and the piece gets longer. Sections play in the order they appear.

## 6. The rule that will surprise you

**A bar is one bar long, and the tokens inside it divide it.**

```
Chords: | Am . . . |        four tokens  -> four beats
Melody: | A4 C5 E5 |        three tokens -> a triplet
Melody: | A4 . C5 . E5 . |  six tokens   -> six eighth notes
```

You never write durations. You write how many things happen in the bar, and the
bar shares itself out between them. This trips up everyone who arrives from
notation software, and it is why the starter file's lyric says *the bar divides
itself*.

## 7. Break it on purpose

Knowing what a mistake looks like is worth more than avoiding one.

**A chord that is not a chord.** Change a chord to `Xm9`:

```bash
tapscript check ocean.tap --strict
```

```
warn  ocean.tap:7: warning: chords row: nothing understood Xm9; silence there instead
    hint: chords look like Am, F#m7, Bb; pitches carry an octave, as in A4 or c3 -- a bare A is not a pitch
```

The bar goes silent rather than failing. That is deliberate — one bad chord
should not stop you hearing the rest — but it means **you should run `check`
after editing**, because a compile will happily produce a piece with a hole in
it.

**A pitch with no octave.** `A` instead of `A4` is read as an A major *chord*,
not the note A. It will sound, and it will not be what you meant.

**A missing bar line.** A row with too few `|` is short, and you get:

```
warning: [V1] chords covers 3 bar(s), the section runs 4
hint: short rows stop early rather than stretching to fill the section
```

Count your pipes. Rows in a section should agree.

## 8. Change key

```bash
tapscript transpose ocean.tap D -o ocean-d.tap
```

Every row moves, including the chords. Note that **the tonic moves and the mode
stays**: `Am` transposed to `D` becomes `Dm`, not D major. If you want a
specific number of semitones instead, `tapscript transpose ocean.tap -- -3`.

## 9. Look around the library

Several thousand chord charts ship with the tool:

```bash
tapscript library "blues"
tapscript library --collections
tapscript play stand-by-me
```

They are chord charts only — no melody, no lyrics. See
[the songbook note](songbook.md) for why.

## 10. Know your machine

```bash
tapscript doctor
```

Tells you what is installed, what each missing piece would add, and where your
files are going. Nothing here is required — the compiler and synthesiser are
written against the standard library alone — but fluidsynth with a soundfont is
the difference between a preview and something you would play to somebody.

## Where to go next

- [Arranging](tutorial-arranging.md) — several players, time signatures, the
  stage model
- [Notation reference](notation.md) — the whole language
- [Integration](integration.md) — driving TapScript from other software

## The finished file

```tapscript
**TRACK: Ocean Diner**
[MetaData]
key: Am | tempo: 120 | swing: 0% | subdivision: 8th
time: 4/4 | mood: Open

[V1] (Verse - 4 Bars)
Chords: | Dm . . . | F . . . | C . . . | G . . . |
Melody: | A4 . C5 E5 | F4 . A4 C5 | E4 . G4 C5 | D4 . F4 B4 |
Lyrics: | write the words | one bar at a time | the bar divides | itself |
@bass   | a1 . e2 . | f1 . c2 . | c1 . g1 . | g1 . d2 . | vel: 70
@piano  | a3-c4-e4 . . . | f3-a3-c4 . . . | c3-e3-g3 . . . | g3-b3-d4 . . . | vel: 60

[BR] (Bridge - 4 Bars)
Chords: | Dm . . . | Dm . . . | E7 . . . | E7 . . . |
Melody: | D4 . F4 A4 | C5 . A4 F4 | E4 . G#4 B4 | E5 . . . |

[CH] (Chorus - 4 Bars)
Chords: | F . . . | G . . . | Am . . . | Am . . . |
Melody: | F4 . A4 C5 | G4 . B4 D5 | A4 . C5 E5 | A4 . . . |
@bass   | f1 . c2 . | g1 . d2 . | a1 . e2 . | a1 . . . | vel: 74
```
