# TapScript Boot Camp — Lesson 01: The Foundations

Welcome, agent. This is the first file you will read when learning TapScript. Read it fully, then complete the exercise at the bottom. After that, update your knowledge base as instructed.

---

## What is TapScript and why does it exist?

TapScript is a compact, human-readable notation format for composing music that is **directly executable by AI agents** and software synthesizers. It was designed to solve three problems:

1. **Ambiguity** — Traditional sheet music requires years of training and is hard to parse programmatically.
2. **Bloat** — MIDI files are binary and opaque; JSON music formats are verbose.
3. **Agent-unfriendliness** — Existing notations don't map cleanly to a simple line-based parser.

TapScript gives you a **single text file** that describes chords, melody, lyrics, and player assignments in a way that both a human and an AI can read at a glance.

---

## The Notation Format — Annotated Example

```
@player piano = "piano_soft.wav"
@player bass  = "bass_acoustic.wav"

Chords:
Am | F | C | G

Melody:
E4 . q a2 . | c4 . e2 . | g4 . c3 . | b2 . a2 .

Lyrics:
"Some - thing" | "in - side" | "won't let" | "go"

Dyn:
p | mf | f | pp
```

**Line-by-line breakdown:**

- `@player` lines assign instruments to named roles.
- `Chords:` section holds chord progressions (one bar per `|`).
- `Melody:` section holds note sequences with timing dots and dashes.
- `Lyrics:` section holds syllable text, aligned to bars.
- `Dyn:` (optional) holds dynamics per bar.

---

## The Five Line Types

TapScript has exactly **five** line types. Every file must contain at least `Chords:` and `Melody:`. The others are optional but recommended.

| Line Type    | Required? | Purpose                                 |
|--------------|-----------|-----------------------------------------|
| `@player`    | No        | Assign instruments to channels          |
| `Chords:`    | Yes       | Harmonic progression                    |
| `Melody:`    | Yes       | Lead line / notes                       |
| `Lyrics:`    | No        | Text aligned to bars                    |
| `Dyn:`       | No        | Volume/expression per bar               |

**Important:** Section headers end with a colon (`:`). Player lines start with `@`. No other line types exist.

---

## Bars, Pipes, Dots, and Dashes

### Bars (`|`)

A **bar** is one measure of music. In TapScript, a bar is delimited by a pipe character `|`. Everything between two pipes belongs to one bar. The default time signature is **4/4**, meaning each bar holds four quarter-note beats.

```
Am | F | C | G
```

That's four bars: Am, F, C, G.

### Dots (`.`) — Note Duration

A dot `.` after a note means **hold for one quarter-note**. A single dot = quarter note. Two dots `..` = half note. Four dots `....` = whole note. You can also place dots **before** a note to indicate a rest of that duration.

```
E4 . c4 . g4 .
```

That's three quarter notes (E4, c4, g4) — one per beat.

### Dashes (`-`) — Sustain / Tie

A dash `-` after a note **extends** the previous note's duration by one quarter-note. You can chain multiple dashes.

```
E4 . - -
```

That means E4 held for 3 quarter notes (a dotted half note).

**Combined example:**
```
Melody:
E4 . . . | c4 . - | g4 . . | b2 .
```
Bar 1: E4 whole note. Bar 2: c4 half note (held). Bar 3: g4 dotted quarter. Bar 4: b2 quarter.

---

## Note Names and MIDI Mapping

TapScript uses standard letter names with octave numbers.

### Basic format
- A letter `A`–`G` (case-insensitive, but lowercase is common for notes)
- Optional accidental: `#` (sharp) or `b` (flat)
- Octave number: `0`–`8`

### MIDI number formula
```
MIDI = (octave + 1) * 12 + semitone_offset
```
Where `C` = 0, `C#` = 1, `D` = 2, ..., `B` = 11.

**Examples:**
- `E4` → (4+1)*12 + 4 = 60 + 4 = **MIDI 64**
- `a2` → (2+1)*12 + 9 = 36 + 9 = **MIDI 45**
- `c3` → (3+1)*12 + 0 = 48 + 0 = **MIDI 48**

### Chords (multiple notes)

To write a chord, list the notes separated by dashes **inside the same token**:

```
e2-a2-c3
```

That's an A minor chord (A2, C3, E3) — wait, `e2` is E2, `a2` is A2, `c3` is C3. Actually that's E-A-C spelled upward. But common usage: write root first.

```
a2-c3-e3
```
That's A minor (A, C, E).

**Chord symbols** in the `Chords:` section use standard notation: `Am`, `F`, `C`, `G`, `Dm7`, `Bdim`, etc. These are **not** MIDI-named; they are harmonic shorthand.

---

## Putting It All Together

Here's a complete 4-bar example in A minor:

```
@player piano = "piano_soft.wav"
@player bass  = "bass_acoustic.wav"

Chords:
Am | F | C | G

Melody:
E4 . . . | c4 . . . | g4 . . . | b2 . . .

Lyrics:
"la - la - la" | "la - la - la" | "la - la - la" | "la - la - la"

Dyn:
p | mf | f | pp
```

---

## Exercise

Now you must prove you can write TapScript. Compose a 4-bar fragment in A minor with a chord progression and a melody. Include at least one `@player` line.

```json
{
  "exercise": "Write a 4-bar TapScript fragment in A minor with a chord progression and melody. Use at least one @player line.",
  "submit_to": "/api/exercise-check",
  "expected_elements
