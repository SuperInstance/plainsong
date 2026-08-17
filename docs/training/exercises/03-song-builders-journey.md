# Plainsong Progressive Song-Building Curriculum

## The Capstone: From One Bar to a Complete Song

This curriculum guides you through ten progressive stages of composition. Each stage builds directly on the previous, creating a complete, original song by the end. Work through each stage sequentially—do not skip ahead. At each checkpoint, verify your work meets the criteria before proceeding.

---

## Stage 1: Foundation — Key & Emotion

**Instructions:** Choose a musical key and an emotional direction for your song. The key determines your tonal palette; the emotion guides every subsequent choice. Write exactly **one bar** of music—a single chord with clear duration.

**Checkpoint Criteria:** Your Plainsong must contain a key declaration, an emotion descriptor, and one complete bar with a chord symbol and duration.

**Example Plainsong:**
```
@key = C major
@emotion = bittersweet nostalgia
@tempo = 72 bpm

bar 1: Cmaj7 (4 beats)
```

---

## Stage 2: Expansion — Four Bars, Two Chords

**Instructions:** Extend your single bar to four bars. Add a second chord that creates tension or movement relative to your first. Consider the emotional arc: does the second chord lift, darken, or destabilize?

**Checkpoint Criteria:** Four complete bars, two distinct chords, and a written note explaining the relationship between the chords and your emotion.

**Example Plainsong:**
```
@key = C major
@emotion = bittersweet nostalgia
@tempo = 72 bpm

bar 1: Cmaj7 (4 beats)
bar 2: Cmaj7 (4 beats)
bar 3: Am7 (4 beats)
bar 4: Am7 (4 beats)

@note: The shift to Am7 introduces gentle melancholy, a "remembering" quality.
```

---

## Stage 3: Melody — The Singing Line

**Instructions:** Add a melody line above your four-bar chord progression. The melody should have a clear contour—rising, falling, or arching—that expresses your chosen emotion. Use scale tones that highlight the character of each chord.

**Checkpoint Criteria:** A melody line with one note per beat (or clearly notated rhythm), using notes that fit the underlying chords. The melody must have intentional shape.

**Example Plainsong:**
```
@key = C major
@emotion = bittersweet nostalgia
@tempo = 72 bpm

bar 1: Cmaj7 | Melody: E - G - A - G
bar 2: Cmaj7 | Melody: E - D - C - B
bar 3: Am7  | Melody: A - C - E - C
bar 4: Am7  | Melody: A - G - E - C

@note: Melody descends in bar 2 and 4, evoking a sigh.
```

---

## Stage 4: Lyrics — Words for the Melody

**Instructions:** Write lyrics that match the rhythm and contour of your melody. Each syllable should map to a note. The words should deepen your emotional theme—specific images, not abstractions.

**Checkpoint Criteria:** Every melody note has a corresponding syllable. Lyrics are written beneath the melody line and coherently express the emotion.

**Example Plainsong:**
```
bar 1: Cmaj7 | Melody: E - G - A - G
             | Lyrics: "the - sum - mer - light"
bar 2: Cmaj7 | Melody: E - D - C - B
             | Lyrics: "fades — in - to - night"
bar 3: Am7  | Melody: A - C - E - C
             | Lyrics: "I - re - mem - ber"
bar 4: Am7  | Melody: A - G - E - C
             | Lyrics: "your - qui - et - voice"
```

---

## Stage 5: Bass — The Foundation

**Instructions:** Add a `@bass` line beneath the chords. The bass should outline chord roots and fifths, creating rhythmic stability. Use longer note values (half or whole notes) to ground the harmony.

**Checkpoint Criteria:** One bass note per bar (minimum), clearly tied to the chord. Bass line direction and rhythm should complement the melody without competing.

**Example Plainsong:**
```
bar 1: Cmaj7 | Melody: E-G-A-G | Lyrics: "the sum-mer light"
             | Bass: C (whole note)
bar 2: Cmaj7 | Melody: E-D-C-B | Lyrics: "fades in-to night"
             | Bass: G (half notes: G - G)
bar 3: Am7  | Melody: A-C-E-C | Lyrics: "I re-mem-ber"
             | Bass: A (whole note)
bar 4: Am7  | Melody: A-G-E-C | Lyrics: "your qui-et voice"
             | Bass: E (half notes: E - E)
```

---

## Stage 6: Contrast — Verse vs. Chorus

**Instructions:** Write a contrasting section—a chorus if your first section is a verse, or a bridge if you want a middle section. This section should differ in at least three ways: chord progression, melody contour, and emotional intensity.

**Checkpoint Criteria:** A new four-bar section with at least one new chord, a melody that moves differently (higher range, wider intervals, or new rhythm), and a clear emotional shift.

**Example Plainsong:**
```
@section = chorus
@emotion = rising hope beneath sadness

bar 5: Fmaj7 | Melody: A - C - F - E | Lyrics: "but I still hold"
             | Bass: F (whole)
bar 6: Gsus4 | Melody: D - F - G - A | Lyrics: "the light you gave"
             | Bass: G (half, half)
bar 7: G7    | Melody: B - D - G - F | Lyrics: "through ev - 'ry cold"
             | Bass: G (whole)
bar 8: Cmaj7 | Melody: E - G - C - B | Lyrics: "and si - lent wave"
             | Bass: C (whole)
```

---

## Stage 7: Dynamics — Shaping the Volume

**Instructions:** Add dynamic markings to both sections. Decide where the song grows louder (building tension) and where it softens (releasing or retreating). Dynamics should follow emotional logic.

**Checkpoint Criteria:** Dynamic markings (`p`, `mf`, `f`, crescendo/decrescendo) on every bar. A written rationale for at least one dynamic choice.

**Example Plainsong:**
```
@dynamics:
Verse: p (bars 1-2), mp (bars 3-4) — growing unease
Chorus: mf (bar 5), f (bar 6-7), mf (bar 8) — peak and release

bar 5: Fmaj7 | Melody: A
