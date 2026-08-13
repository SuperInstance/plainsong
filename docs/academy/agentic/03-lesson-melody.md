# TAPSSCRIPT BOOT CAMP FOR AI AGENTS
## LESSON 03: MELODY & RHYTHM

---

### 1. MELODY VS. CHORD — THE RELATIONSHIP

Every melody note you write exists in relation to the chord playing beneath it. Think of it as a conversation:

**Chord Tones (Safe):** The 1st, 3rd, and 5th of the chord. These sound stable, resolved, and "at home." If your chord is C Major (C-E-G), then C, E, and G are your safe notes.

**Passing Tones (Spice):** The 2nd, 4th, 6th, and 7th (plus any accidentals). These create tension, movement, and emotional color. A passing tone wants to *resolve* — usually by stepping up or down to a chord tone.

**The Rule of Thumb:**
- Start and end phrases on chord tones.
- Use passing tones *between* chord tones for momentum.
- Land on a passing tone ONLY if it resolves within a beat or two.

---

### 2. SCALE DEGREES — WHEN TO USE WHAT

If we're in A minor (your home key), the scale is: A B C D E F G

| Degree | Note | Feel | Best Used For |
|--------|------|------|---------------|
| 1 | A | Home | Phrase starts/ends |
| 3 | C | Minor third, sad | Emotional emphasis |
| 5 | E | Dominant, strong | Building tension, ending |
| 2 | B | Restless | Passing up to 3 |
| 4 | D | Suspended | Moving to 3 or 5 |
| 6 | F | Dark color | Descending to 5 |
| 7 | G | Leading tone | Resolving up to 1 |

**Safe pattern:** 1 → 3 → 5 → 3 → 1 (all chord tones, zero risk)
**Spicy pattern:** 1 → 2 → 3 → 4 → 5 (passing tones create lift)

---

### 3. RHYTHM — DOTS AND DASHES

In TapScript, rhythm is **explicit** — no guesswork:

- **Dots (.)** = sustain the note through that beat
- **Dashes (-)** = rest/empty space
- **Numbers** = play the note on that beat

**Examples (4/4 time, one bar = 4 beats):**

```
E4 . . .    →  Play E4 on beat 1, hold for 4 beats (whole note)
E4 . . -    →  Play E4, hold 3 beats, rest 1
- - E4 .    →  Rest 2 beats, play E4, hold 1
E4 - E4 -   →  Staccato pulse — play, stop, play, stop
E4 . - E4   →  Long-short-rest-long — syncopated feel
```

**Groove comes from contrast.** A melody of all equal eighth notes is robotic. Mix:
- Long sustains (emotional weight)
- Short stabs (urgency)
- Strategic rests (anticipation)

**Rest = power.** A rest before a big note makes it land harder.

---

### 4. SWING — THE FEEL DIAL

Swing percentage controls how much your eighth notes "shuffle."

| Swing | Feel | Use For |
|-------|------|---------|
| 0% | Straight — even 8ths | Rock, techno, march |
| 15% | Slight hesitation | Pop, funk, natural groove |
| 30% | Triplet feel (shuffle) | Jazz, blues, hip-hop |

**In TapScript:**
```
[Swing:0%]  E4 . E4 . E4 . E4 .
[Swing:15%] E4 . E4 . E4 . E4 .
[Swing:30%] E4 . E4 . E4 . E4 .
```

Same notation, different feel. The swing percentage is a **global setting** — set it once at the top of your file.

**Pro tip:** Set swing to 15% by default. It makes almost anything sound better.

---

### 5. WRITING A MEMORABLE MELODY

Memorable = simple + repeatable + slight surprise.

**The Formula:**
1. **Phrase A (2 bars):** State your main idea — 3–5 notes, strong rhythm.
2. **Phrase A' (2 bars):** Repeat Phrase A but change the ending (variation).
3. **Phrase B (2 bars):** Contrast — higher register, different rhythm, new rhythm pattern.
4. **Phrase A'' (2 bars):** Return to Phrase A for resolution.

**Example (8-bar structure):**
```
[Melody]
| E4 . G4 . | A4 . - . | E4 . G4 . | B4 . - . |
| C5 . B4 . | A4 . G4 . | E4 . . - | - - - - |
```

**Never forget:** The human ear loves **repetition**. If you write 8 unique bars, it's forgettable. If you repeat with small changes, it sticks.

---

### 6. THE BLANK BAR SYSTEM — ASYNC COLLABORATION

This is how you work with other agents who might be composing *later* or *in parallel*.

**The Rule:** A bar with `_____` means *"I cede this bar — you fill it."*

**How it works:**
```
[V1]
Chords:  | Am    .    | _____ | F     G    |
Melody:  | E4 . . .   | _____ | A4 . G4 E4 |
Lyrics:  | I . . .    | _____ | write . code |
@you     | e2-a2 . .  | _____ | f2-a2 g2-b2 |
```

**What each blank means:**
- `Chords: _____` → Another agent chooses the harmony.
- `Melody: _____` → Another agent writes the vocal line.
- `@you: _____` → A bass or harmony agent adds their part.

**Contract rules:**
1. If you leave a blank, you MUST provide the surrounding context (key, chord before/after, melody before/after).
2. If you fill a blank, match the established register and energy.
3. Never change another agent's filled bar without a `// revision` note.

**Example — you write the melody, leave chords blank:**
```
[Chorus]
Chords:  | _____ | _____ | F . . . | G . . . |
Melody:  | C5 . . . | C5 . B4 A4 | A4 . . . | G4 . . - |
Lyrics:  | shine . . . | through . the dark | sky . . . | now .
