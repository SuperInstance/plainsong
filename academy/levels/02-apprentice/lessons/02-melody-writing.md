# TapScript Lesson 02: Melody Writing (APPRENTICE)

> **Under revision — the notation below is not TapScript.** This lesson was
> generated before the notation existed and describes commands the compiler has
> never had. It is kept, labelled, so the rewrite has a starting point. Do not
> learn from it. See `SHIPPING.md`.

## Concept: Motif → Phrase → Period

A melody is not random notes—it’s a **conversation**. At apprentice level, you build from a **motif** (2–4 note rhythmic/interval cell) into a **phrase** (4 bars) and then a **period** (8 bars, antecedent–consequent). The antecedent ends *unresolved* (often on scale degree 2 or 5), the consequent *resolves* (degree 1 or 3). Use **stepwise motion** as default, leap only for emphasis, and keep a **single climax** (highest note) around 75% of the melody’s length.

## TapScript Example

```text
// Melody builder: C major, 4/4, 8 bars
Key: C
Meter: 4/4
Tempo: 100

Motif m1: [C4 E4 G4] rhythm: [1 0.5 0.5]  // pickup: three ascending steps

Phrase A (bars 1–4):
  bar1: m1
  bar2: [A4 G4 F4] rhythm: [1 0.5 1.5]   // descending sequence
  bar3: [E4 D4 C4] rhythm: [0.5 0.5 2]   // turning back
  bar4: [D4] rhythm: [4]                 // antecedent ends on 2 (unresolved)

Phrase B (bars 5–8):
  bar5: m1 transposed: +4               // sequence up
  bar6: [A4 B4 C5] rhythm: [0.5 0.5 2]  // climb to climax
  bar7: [C5 B4 A4 G4] rhythm: [0.5 0.5 0.5 1.5] // descent
  bar8: [C4] rhythm: [4]                // resolution on tonic
```

## JSON Exercise Block

```json
{
  "exercise": "melody-write-02",
  "level": "apprentice",
  "prompt": "Write an 8-bar melody in A minor. Use a 3-note motif (A–C–E) as your seed. Bar 4 must end on E (dominant). Bar 8 must end on A. Use at most 2 leaps >3rd total.",
  "output_schema
