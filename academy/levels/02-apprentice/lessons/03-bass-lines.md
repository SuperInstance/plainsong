# TapScript Lesson: 03 Bass Lines (APPRENTICE)

## Concept Explanation
The "03 bass line" is a foundational groove in TapScript — a pattern where the root note hits on beats 1 and 3 (the downbeats), with a fifth or octave fill on beat 4 as a pickup. This creates momentum and harmonic grounding. As an apprentice, you'll move beyond static roots: your bass should *walk* or *pulse* to imply chord changes. The key rule: **never play busy on the 1** — anchor it. Use `rest` for space, and let the kick drum (if present) share the low-end weight.

## TapScript Example
```
// 03 bass line in A minor (A-C-E-G progression)
tempo 90
key Am

// Bar 1: A root, octave pickup
track bass
  note A2 1.0
  rest 1.0
  note A2 0.5
  note A3 0.5  // pickup into C

// Bar 2: C root, fifth walk-up
  note C3 1.0
  rest 1.0
  note C3 0.5
  note G3 0.5  // fifth as tension

// Bar 3: E root, chromatic approach
  note E2 1.0
  rest 1.0
  note E2 0.5
  note F2 0.5  // chromatic slide to G

// Bar 4: G root, resolve down
  note G2 1.5
  note G2 0.5
  rest 1.0
end
```
*Notice: each bar has exactly one 1.0-length anchor, one rest, and a two-note pickup (0.5 + 0.5). This is your 03 skeleton.*

## JSON Exercise Block
```json
{
  "exercise": "03_bass_walk",
  "level": "apprentice",
  "instruction": "Complete the missing bass line for a I-IV-V-I progression in C major (C-F-G-C). Use the 03 pattern: anchor on beat 1, rest on beat 2, pickup on beat 4. Write the bass track only.",
  "given": {
    "tempo": 100,
    "key": "C",
    "chords": ["C3", "F2", "G2", "C3"],
    "pattern": ["anchor", "rest", "pickup1", "pickup2
