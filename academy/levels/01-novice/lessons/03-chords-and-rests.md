**TapScript Lesson: Chords & Rests (Novice)**

**(1) What you need to know before starting**  
You know how to place single notes on a timeline and set their duration. You understand ticks (the time grid). You don’t need music theory—just intuition.

**(2) The concept explained simply**  
A **chord** is two or more notes played at the *exact same tick*. In TapScript, you stack them inside square brackets `[ ]`, separated by commas. A **rest** is silence—you write it as `R` and give it a duration like a note. Rests push the timeline forward; chords do not need extra duration beyond their single tick unless you extend them with `:`.

**(3) Complete example (compile at http://localhost:5557)**  
```tascript
// Chord + rest demo
tempo 120
track "piano"
[60, 64, 67] : 2   // C major chord, 2 ticks
R : 1              // one tick of silence
[62, 65, 69] : 2   // D minor chord
R : 1
[60, 64, 67] : 1
[55, 59, 62] : 3   // final chord, longer
```
Copy this into the editor. Hit play. You’ll hear two chords, a gap, two chords, a gap, then a final chord.

**(4) JSON exercise block**  
```json
{
  "exercise": "Create a 4-tick pattern: a C major chord (60,64,67) for 1 tick, a rest for 1 tick, a G major chord (55,59,62) for 1 tick, and a rest for 1 tick. Use tempo 100.",
  "submit_to": "/api/exercise-check",
  "expected_elements": ["[60,64,67] : 1", "R : 1", "[55,59,62] : 1", "tempo 100"],
  "passing_criteria": "Exactly four elements in order: chord, rest, chord, rest. All durations are 1. No extra tracks or notes."
}
```

**(5) Save to your knowledge base**  
- Chords: `[note1, note2, ...] : duration
