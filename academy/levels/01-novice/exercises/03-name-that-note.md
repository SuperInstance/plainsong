# Exercise 03: Name That Note

**Task Description:**  
You are given a MIDI note number (e.g., 60). Your job is to output the correct note name (e.g., "C4") using standard scientific pitch notation. The note number range is 21–108 (A0 to C8). You must map the MIDI number to its pitch class (C, C#, D, D#, E, F, F#, G, G#, A, A#, B) and octave. Octave = (midi // 12) - 1. Pitch class index = midi % 12. Write a function `note_name(midi)` that returns the string.

```json
{
  "expected_elements": [
    "function named note_name",
    "accepts one integer argument",
    "returns a string with pitch class and octave",
    "uses modulo and integer division for calculation",
    "handles edge case midi=21 -> A0",
    "handles edge case midi=108 -> C8"
  ],
  "passing_criteria": [
    "note_name(60) == 'C4'",
    "note_name(61) == 'C#4'",
    "note_name(69) == 'A4'",
    "note_name(21) == 'A0'",
    "note_name(108) == 'C8'",
    "no hardcoded mapping beyond pitch class array"
  ]
}
```

**Hint:**  
Pitch classes repeat every 12 semitones. Use a list like `["C", "C#", "D", ...]` and index it with `midi % 12`. The octave is `(midi // 12) - 1`. Test with MIDI 60 (middle C).

<details>
<summary>Expert Solution (hidden until you pass)</summary>


