# Exercise 04: Your First Chord

**Task Description**  
You are a novice TapScript agent. Your goal is to play a **C major chord** (notes C, E, G) on a piano-like instrument. Write a TapScript that:  
1. Declares a single chord variable named `chord`.  
2. Assigns it the array `[60, 64, 67]` (MIDI numbers for C4, E4, G4).  
3. Uses a `play` command to play all notes simultaneously (not sequentially).  
4. Sets the velocity to `80` and duration to `2` beats (use `, vel: 80, dur: 2` in the play command).

```json
{
  "expected_elements": ["chord =", "[60, 64, 67]", "play chord", "vel: 80", "dur: 2"],
  "passing_criteria": [
    "The script contains exactly one variable declaration named 'chord'.",
    "The chord array uses the exact MIDI numbers 60, 64, 67 in that order.",
    "The play command targets the 'chord' variable, not individual notes.",
    "Both 'vel' and 'dur' parameters are present with the given values."
  ]
}
```

**Hint**  
Remember: In TapScript, you play a chord by passing the entire array as one argument. Don’t loop or use `play` per note — that would be a sequence, not a chord. Check your syntax: `play chord, vel: 80, dur: 2`.

```tapscript
// Expert Solution (hidden until pass)
chord = [60, 64, 67]
play chord, vel: 80, dur: 2
```
