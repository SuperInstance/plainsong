# TapScript Cookbook: 10 Practical Recipes

## Recipe 1: Walking Bass Line

**Problem:** You need a bass line that moves smoothly between chords, creating forward momentum.

**Solution:** Use stepwise motion (scale tones) approaching each chord change from a half-step below or above. In TapScript, define the bass as a separate @agent and use `@notes` with explicit octave shifts.

**Example:**
```
@agent bass
@instrument electric-bass
@tempo 120
@time 4/4

@bars 1-4
@notes
C2 E2 G2 B2 | C3 B2 G2 E2 | F2 A2 C3 E3 | F3 E3 C3 A2 |
G2 B2 D3 F3 | G3 F3 D3 B2 | C3 E3 G3 C4 | G3 E3 C3 G2 |
```

---

## Recipe 2: Layering Piano Chords Under a Melody

**Problem:** You have a melody, but the piano accompaniment feels sparse or clashes.

**Solution:** Use a separate @agent for piano. Play chords in the mid-register (C3–C5), with the melody’s root note as the bass of each chord. Use `@sync` to align chord changes with the melody’s phrasing (typically every 1–2 bars).

**Example:**
```
@agent melody
@instrument flute
@bars 1-4
@notes
E4 G4 A4 B4 | C5 B4 A4 G4 | A4 C5 E5 D5 | C5 B4 G4 E4 |

@agent piano
@instrument grand-piano
@sync melody
@bars 1-4
@notes
C3 E3 G3 B3 | C3 E3 G3 B3 | F3 A3 C4 E4 | F3 A3 C4 E4 |
G3 B3 D4 F4 | G3 B3 D4 F4 | C3 E3 G3 B3 | C3 E3 G3 B3 |
```

---

## Recipe 3: Lyrics Aligned with Melody Rhythm

**Problem:** Lyrics feel unnatural because syllables don’t match the rhythmic stress of the melody.

**Solution:** Map each syllable to a specific note value. Use `@lyrics` with underscores (`_`) for sustained notes, and hyphens for split syllables. Place stressed syllables on downbeats (beat 1 and 3 in 4/4).

**Example:**
```
@agent vocals
@instrument voice
@time 4/4
@bars 1-4
@notes
C4 E4 G4 A4 | G4 E4 D4 C4 | D4 F4 A4 C5 | B4 A4 G4 E4 |

@lyrics
The_ wind_ blows_ cold_ | through_ the_ night_ sky_ | I_ seek_ a_ warm_ | fire_ to_ keep_ me_ high_
```

---

## Recipe 4: Key Change Mid-Song

**Problem:** You want to modulate to a higher key for emotional lift, but the transition feels abrupt.

**Solution:** Use a pivot chord (common chord between old and new key). In TapScript, write a `@transpose` directive on a specific bar, and add a short instrumental fill (2 beats) to mask the shift.

**Example:**
```
@agent melody
@instrument violin
@tempo 100
@bars 1-4   // Key: C major
@notes
C4 E4 G4 C5 | E5 D5 C4 B4 | A4 C5 E5 G5 | F5 E5 D4 C4 |

@transpose +2   // Shift to D major at bar 5
@bars 5-8
@notes
D4 F#4 A4 D5 | F#5 E5 D4 C#4 | B4 D5 F#5 A5 | G5 F#5 E4 D4 |

@agent piano
@instrument grand-piano
@bars 4-5  // Fill during transition
@notes
C3 E3 G3 B3 | C#3 F#3 A3 C#4 |
```

---

## Recipe 5: Creating a 3/4 Waltz Feel

**Problem:** You want a lilting, dance-like triple meter, but your default pattern is 4/4.

**Solution:** Set `@time 3/4` and use a bass note on beat 1, chord on beat 2 and 3. In TapScript, use `@note` patterns with three distinct beats per bar.

**Example:**
```
@agent bass
@instrument upright-bass
@time 3/4
@tempo 90
@bars 1-4
@notes
C2 A1 F1 | C2 A1 F1 | G1 E1 C1 | G1 E1 C1 |

@agent piano
@instrument grand-piano
@bars 1-4
@notes
C3 E3 G3 E3 G3 | C3 E3 G3 E3 G3 | G3 B3 D3 B3 D3 | G3 B3 D3 B3 D3 |
```

---

## Recipe 6: Multi-Instrument Arrangements with @player

**Problem:** You need to coordinate several instruments playing together, but managing separate files is messy.

**Solution:** Use `@player` blocks inside a single script. Each `@player` acts as a separate track, with its own `@agent`, `@instrument`, and `@bars`. Use `@start` and `@end` to control entry points.

**Example:**
```
@player 1
@agent drums
@instrument kit
@bars 1-8
@notes
Kick1 Snare1 Kick1 Snare1 | Kick1 Snare1 Kick1 Snare1 | ...

@player 2
@agent bass
@instrument electric-bass
@bars 1-8
@notes
C2 E2 G2 B2 | C2 E2 G2 B2 | F2 A2 C3 E3 | F2 A2 C3 E3 | ...

@player 3
@agent guitar
@instrument acoustic-guitar
@bars 3-8  // Enters at bar 3
@notes
C3 E3 G3 C4 | C3 E3 G3 C4 | F3 A3 C4 F4 | ...
```

---

## Recipe 7: Adding Swing

**Problem:** Your eighth notes feel stiff and robotic; you want a jazzy, loping feel.

**Solution:** In TapScript, use `@swing` with a ratio like `@swing 60` (60% of the beat on the first eighth, 40% on the second). Apply it to all instruments that need it.

**Example:**
```
@swing 60
@agent saxophone
@instrument tenor-sax
@tempo 140
@bars 1-4
@notes
E4 G4 A4 B4 | C5 B4 A4 G4 | A4 C5 E5 D5 | C5 B4 G4 E4 |

@agent piano
@instrument grand-piano
@swing 60
@bars 1-4
@notes
C3 E3 G3 B3 | C3 E3 G3 B3 | F3 A3 C4 E4 | F3 A3 C4 E4 |
```

---

## Recipe 8: Sequential Round (Canon)

**Problem:** You want multiple voices singing the same melody at staggered times (e.g., "Row, Row, Row Your Boat").

**Solution:** Use separate `@player` blocks with identical `@notes` but different `@start` bars. Use `@delay` for precise entry offset.

**Example:**
```
@player 1
@agent voice1
@instrument choir
@bars 1-8
@notes
G4 G4 E4 E4 | C4 C4 D4 D4 | E4 E4 F4 F4 | G4 G4 G4 G4 |

@player 2
@agent voice2
@instrument choir
@start 3  // Enters at bar 3
@delay 2  // 2 beats later than player 1
@bars 1-8
@notes
G4 G4 E4 E4 | C4 C4 D4 D4 | E4 E4 F4 F4 | G4 G4 G4 G4 |
```

---

## Recipe 9: Leaving Blank Bars for Async Harmony

**Problem:** You want another agent to fill in a harmony part later, but you don’t know what notes they’ll play. You need reserved space.

**Solution:** Use `@rest` in the main agent, and define a placeholder `@player` with `@mute` so it doesn’t sound until you add notes. Mark bars as `@blank` in the arrangement.

**Example:**
```
@agent main
@instrument flute
@bars 1-8
@notes
C4 E4 G4 C5 | E5 D4 C4 B4 | A4 C5 E5 G5 | F5 E4 D4 C4 |
@rest 5  // Bars 5-6 blank
@notes
G4 B4 D5 G5 | F5 E4 D4 C4 |

@player harmony
@agent voice
@instrument choir
@mute  // Not active yet
@bars 5-6
@notes
@placeholder  // You will fill these later
```

---

## Recipe 10: Simple Sea Shanty

**Problem:** You want a call-and-response, stomping rhythm with a nautical feel.

**Solution:** Use a 4/4 time, a strong backbeat (beats 2 and 4), and repeat a simple chord progression (I–IV–V). Write a solo line for the "call" and a unison line for the "response."

**Example:**
```
@agent call
@instrument baritone
@tempo 100
@bars 1-4
@notes
C4 E4 G4 G4 | A4 A4 G4 E4 | F4 F4 A4 A4 | G4 G4 E4 C4 |
@lyrics
Heave_ ho_ the_ anchor_ | pull_ the_ rope_ and_ strain_ | Watch_ the_ tide_ come_ rolling_ | back_ to_ sea_ a- gain_ |

@agent response
@instrument male-choir
@bars 1-4
@notes
C3 G3 C3 G3 | C3 G3 C3 G3 | F3 C3 F3 C3 | G3 C3 G3 C3 |
@lyrics
Heave_ ho_ | Heave_ ho_ | Heave_ ho_ | Heave_ ho_ |

@agent drums
@instrument kit
@bars 1-4
@notes
Kick1 Snare1 Kick1 Snare1 | Kick1 Snare1 Kick1 Snare1 | Kick1 Snare1 Kick1 Snare1 | Kick1 Snare1 Kick1 Snare1 |
```

---

**Final Notes:** These recipes are modular—combine them freely. Use `@transpose`, `@swing`, `@sync`, and `@player` to build complex, expressive arrangements. TapScript’s strength is its declarative style: you describe *what* you want, not *how* to compute it. Happy composing!
