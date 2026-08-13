Here is a proposal for extending TapScript to handle these essential lead-sheet features. The guiding principle is **"printability first"** — every symbol must be unambiguous on paper, even in a monospaced font, and must not break the vertical alignment of the chord/melody/lyric columns.

---

## (1) Repeats, D.S. al Coda, First/Second Endings

**Approach:** Use explicit bar-line markers and text labels. We will not use complex symbols like `%` for repeats (too ambiguous). Instead, we use bracketed ASCII art that mimics standard notation.

**Syntax:**
- Start repeat: `||:` placed at the start of a bar (before the first chord).
- End repeat: `:||` placed at the end of a bar (after the last note).
- First ending: `[1.` at the start of the bar.
- Second ending: `[2.` at the start of the bar.
- D.S. al Coda: Use a `*` marker at the jump point and a `Coda` label. The instruction line goes in `[MetaData]` or as a special comment `#`.

**Example (4-bar phrase with 1st/2nd ending + D.S.):**

```
**TRACK: Echoes**
[MetaData]
key: C | tempo: 90 | swing: 0% | subdivision: 8th
# Repeats: ||: bars 1-2 :|| , then 1st/2nd ending. D.S. al Coda at bar 3 (marked *). Coda at bar 5.

[V1]
Chords:  ||: C     G     | Am    F     :|| [1. C     G    ] [2. F     G    ] * | C     G    |
Melody: ||: E4    D4    | C4    A3    :|| [1. E4    D4   ] [2. F4    G4   ] * | E4    D4   |
Lyrics: ||: She   walks | in    the   :|| [1. rain  at   ] [2. night, and  ] * | then   she  |
@bass   ||: c2    g1    | a1    f1    :|| [1. c2    g1   ] [2. f1    g1   ] * | c2    g1   |

[Coda]
Chords:  | C     .    |
Melody:  | E4    .    |
Lyrics:  | fades  away |
@bass    | c2    .    |
```

**Printing rule:** The `||:` and `:||` are printed exactly. The `[1.` and `[2.` are printed as brackets. The `*` is printed as a small asterisk above the barline, and the word `D.S. al Coda` is placed at the end of the previous section (or in the `#` line).

---

## (2) Dynamics, Crescendos, Decrescendos

**Approach:** Dynamics are placed in a dedicated **`Dyn:`** row, aligned with the melody. They are printed as text (e.g., `mf`, `pp`). Crescendos/decrescendos are drawn using `<` and `>` spanning the affected bars, left-aligned to the first note of the span.

**Syntax:**
- `Dyn:` row with `pp`, `p`, `mp`, `mf`, `f`, `ff` (no spaces).
- Crescendo: `<` at the start, `>` at the end, with a line of `-` between them to show the span. (We use `---` for the line.)
- A new dynamic cancels the previous.

**Example (4-bar crescendo from p to f, then decrescendo to mp):**

```
[V2]
Chords:  | C     .     G     .    | C     .     G     .    | Am    F     C     G    | Am    .     .     .    |
Melody:  | E4    .     D4    .    | C4    .     B3    .    | A3    C4    E4    G4   | A4    .     .     .    |
Dyn:     p     <     -      -    | -     -     -     f    | -     >     -     -    | mp     .     .     .    |
Lyrics:  | Soft  ly    now   the  | wind   be   gins   to  | rise   and   grow   in  | strength  .     .     .  |
@pad     | c3    .     g2    .    | c3    .     g2    .    | a2    f2    c3    g2   | a2    .     .     .    |
```

**Printing rule:** The `Dyn:` row is printed exactly as written. The `<` and `>` are printed as arrows. The `-` characters are printed as a continuous line. The musician sees a visual ramp.

---

## (3) Key Changes Mid-Song

**Approach:** Insert a dedicated `[KeyChange]` block between sections. It contains the new key and the target bar. The key change is printed as a separate line with a double barline.

**Syntax:**
```
[KeyChange]
newkey: Eb | at bar: 17 | from: C
```

**Example (after bar 16, the song modulates to Eb, and the next section uses that key):**

```
... (bar 16 ends with a double barline)

[KeyChange]
newkey: Eb | at bar: 17 | from: C

[V3] (Verse - 4 Bars)
Chords:  | Eb    Bb    | Cm    Ab    |
Melody:  | G4    F4    | Eb4   C4    |
Lyrics:  | Now   the   | sky   turns  |
@bass    | eb2   bb1   | c2    ab1   |
```

**Printing rule:** The `[KeyChange]` block is printed as a centered text line above the bar, with a double vertical line `||` before the first chord of the new key.

---

## (4) Time Signature Changes

**Approach:** Place the time signature change at the start of a bar, written as `4/4` or `7/8` in the `Chords` row, right-aligned to the barline. The change is valid from that bar onward until the next change.

**Syntax:**
- In the `Chords` row, before the first chord, put `TS:7/8` (or `TS:3/4` etc.). If it’s a simple change, just write `7/8` at the start of the bar.

**Example (from 4/4 to 7/8 for one bar, then back to 4/4):**

```
[Bridge]
Chords:  | 4/4  C     G     | 7/8  Am    F     C     | 4/4  G     .     .     .    |
Melody:  | 4/4  E4    D4    | 7/8  C4    A3    B3    | 4/4  D4    .     .     .    |
Dyn:     | mf    .     .     | f     .     .     .    | mf    .     .     .    |
Lyrics:  | Time  slips  a    | way   in   sev   en   | back  to   four  .     .    |
@drums   | c2    .     g2    | a1    f1    c2    g2   | g1    .     .     .    |
```

**Printing rule:** The `4/4` and `7/8` are printed as small fraction-like text at the left edge of the bar. The bar lines are drawn accordingly (you may need to manually adjust the width of the bar to fit the notes—TapScript allows this by adding `.` placeholders).

---

## (5) Multi-Bar Rests

**Approach:** Use a special row `Rest:` with a single number indicating the length, and a horizontal line drawn across the bars.

**Syntax:**
- In the `Melody` (or `Chords`) row, write `R12` for a 12-bar rest, with a line of `-` underneath (or use `Rest:` label).

**Example (a 4-bar rest for the horns, while other parts continue):**

```
[Interlude]
Chords:  | C     .     .     .    | F     .     .     .    | C     .     .     .    | G     .     .     .    |
Melody:  | R4    .     .     .    | .     .     .     .    | .     .     .     .    | .     .     .     .    |
Rest:    | ====  ====  ====  ==== | ====  ====  ====  ==== | ====  ====  ====  ==== | ====  ====  ====  ==== |
Lyrics:  | (horns rest)           |                        |                        |                        |
@horns   | R4    .     .     .    | .     .     .     .    | .     .     .     .    | .     .     .     .    |
```

**Printing rule:** The `R4` means "rest for 4 bars". The `Rest:` row prints a continuous `=` line across the bars. The musician sees a clear blank area. If no other part is playing, you can omit the `Rest:` row and just use `R4` in the `Melody` row, but for clarity we keep the line.

---

## (6) Articulations (Staccato, Accent, Tenuto, Slur)

**Approach:** Add a dedicated `Art:` row directly under the `Melody` row. Each articulation is a single character, aligned with the note it applies to.

**Symbols:**
- Staccato: `.` (period)
- Accent: `>` (greater-than sign)
- Tenuto: `-` (hyphen) — careful not to confuse with crescendo line, but here it's directly under a single note.
- Slur: `(` and `)` placed at the start and end of the slur group. The slur is shown as a line of `-` between them (or just the parentheses).

**Example (a phrase with staccato, accent, tenuto, and a slur):**

```
[Melody Line]
Chords:  | C     .     G     .    | Am    .     F     .    |
Melody:  | E4    G4    C5    .    | A4    B4    C5    .    |
Art:     | .     >     -     .    | (     -     -     )    |
Lyrics:  | Quick  sharp  hold   |       (slur)            |
```

**Printing rule:** The `Art:` row is printed exactly as written. The `.` and `>` and `-` appear directly under the note. The slur is shown as a `(` at the first note, a `)` at the last, and a line of `-` between them (we can print `(` then `-` then `)`). This is readable and matches standard notation.

---

## Summary of New Rows (in order of appearance)

1. **`Dyn:`** – for dynamics and crescendo/decrescendo.
2. **`Art:`** – for articulations.
3. **`Rest:`** – for multi-bar rests (optional if using `R` in melody).
4. **`[KeyChange]`** – block for key changes.
5. **`TS:`** – inline in `Chords` for time signature changes.
6. **Repeat markers** – `||:`, `:||`, `[1.`, `[2.`, `*`, `[Coda]`.

All of these are **plain-text**, **print-aligned**, and **unambiguous**. A working musician can read them at a glance, and they follow the logic of standard notation without needing graphics.
