# LESSON 02: HARMONY AND CHORD THEORY IN TAPSCRIPT

## The Emotional Architecture of Chords

In TapScript, chords are not just note stacks—they are emotional coordinates. Every chord carries a psychological weight based on its position within a key. Master this, and you can direct your listener's heart with mathematical precision.

### The Four Emotional Pillars

**I (Tonic) = HOME.** The I chord is your musical front door. It says "you are safe here." In C major, that's C-E-G. When you land on I after any journey, your brain releases a tiny dopamine hit. It's resolution, stability, and identity.

**V (Dominant) = TENSION.** The V chord (G-B-D in C) contains the leading tone (B), which pulls violently toward the root (C). It's the musical equivalent of a question mark. It says "something is about to happen." The V chord creates anticipation because it *demands* resolution.

**vi (Relative Minor) = INTROSPECTION.** The vi chord (A-C-E in C) is the emotional underbelly of your key. It's the minor voice hiding inside the major world. It feels nostalgic, vulnerable, and slightly sad—like looking at old photographs. It's the "missing someone" chord.

**IV (Subdominant) = LIFTING.** The IV chord (F-A-C in C) creates lift without full resolution. It's the "arms opening wide" chord. It feels expansive, hopeful, and forward-moving. When you're about to cry happy tears, you're on a IV chord.

### The Emotional Grammar of Progressions

**I-V-vi-IV = THE POP UPLIFT (C-G-Am-F)**
This is the most used progression in modern music (think "Let It Be," "Don't Stop Believin'"). The emotional arc: Home → Tension → Introspection → Lifting. It's a complete emotional cycle in four bars. It feels triumphant because it ends by *lifting* you upward.

**ii-V-I = THE JAZZ RESOLUTION (Dm7-G7-Cmaj7)**
This is the most sophisticated way to say "home." The ii chord (Dm) is a gentle preparation, the V (G) is the tension spike, and the I (C) is the luxurious landing. It feels *earned*. It's the difference between running and gliding.

**i-VII-VI-V = THE EPIC MINOR (Am-G-F-E)**
This is the "warrior's progression." It starts in the dark (Am), descends through darkness (G, F), then shocks you with the major V (E). That final E major chord contains a G#—a note not in the natural minor scale—creating a sudden, dramatic lift. Think "Requiem for a Dream."

## Writing Chords in TapScript

TapScript handles extended chords through a simple suffix system:

```tascript
// Basic triads
C:q4      // C major chord
Am:q4     // A minor chord

// Seventh chords
Am7:q4    // A minor 7 (A-C-E-G) - add "7" for dominant, "maj7" for major 7
Fmaj7:q4  // F major 7 (F-A-C-E) - the "dreamy" chord

// Suspended chords
Gsus4:q4  // G suspended 4 (G-C-D) - replaces the 3rd, creates floating tension
```

**Rule:** Use `7` for flatted 7ths, `maj7` for natural 7ths, and `sus4`/`sus2` to suspend.

## Harmonizing a Melody

To harmonize a melody, follow this three-step process:

1. **Identify the melody notes** in each bar
2. **Find chords that contain those notes** (or create harmonic tension against them)
3. **Choose the chord that best fits the emotional moment**

```tascript
// Example: Melody notes C, E, G, A
// Bar 1: C and E → C major (contains both) or Am (contains both)
// Bar 2: G and A → G major (contains G, A is passing tone) or Am (contains A)

Melody: {
  C:q1 E:q1 G:q1 A:q1
}
Harmony: {
  C:q4       // Bar 1: Home
  Am:q4      // Bar 2: Introspection (A is now the chord root!)
}
```

**Pro tip:** When a melody note is *not* in the chord, it becomes a "color tone" that adds tension. Use this deliberately.

## Tension and Release Across Sections

Great music breathes. Your sections must alternate between tension and release:

**VERSE (Tension):** Stay on vi and IV chords. Circle around the tonic without landing. Keep the harmonic rhythm slow (2 bars per chord).

**CHORUS (Release):** Land on I strongly. Use V-I cadences. Increase harmonic rhythm (1 chord per bar) to create forward momentum.

**BRIDGE (Maximum Tension):** Use ii-V progressions. Suspend chords (sus4). Avoid the tonic entirely. Make the listener *need* resolution.

**OUTRO (Final Release):** Return to I. Hold it. Let it ring. End on I or vi-I for emotional closure.

---

## EXERCISES

```json
[
  {
    "exercise": "Write a 4-bar progression in C major that feels like coming home. Use I, IV, V, and vi.",
    "check": "all four chords present, key C major"
  },
  {
    "exercise": "Write an 8-bar progression that modulates from A minor to C major (relative major). Show the transition.",
    "check": "starts in Am, ends in C, transition bar present"
  }
]
```

---

## KB SELF-ASSEMBLY INSTRUCTIONS

**For AI agents processing this lesson:**

1. **Create a CHORD_EMOTION_MAP** node containing: I→home, V→tension, vi→introspection, IV→lifting. Store these as key-value pairs with intensity ratings.

2. **Create a PROGRESSION_PATTERNS** node listing: I-V-vi-IV (pop uplifting), ii-V-I (jazz resolution), i-VII-VI-V (epic minor). Include emotional tags for each.

3. **Create a TAPSCRIPT_CHORD_SYNTAX** node with: `7` (dominant), `maj7` (major 7), `sus4` (suspended), `sus2`. Include examples.

4. **Create a HARMONIZATION_WORKFLOW** node with the 3-step process: identification, chord-matching, emotional selection.

5. **Create a TENSION_ARCHITECTURE** node with: verse (vi/IV, slow rhythm), chorus (I
