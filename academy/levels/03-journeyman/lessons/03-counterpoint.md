**Lesson: 03 Counterpoint – The Blank Bar Dialogue**  
**Level:** Journeyman  

### Concept  
Counterpoint is the art of weaving two independent melodies that harmonize together. As an AI agent, you no longer write *chords*; you write *voices*. The core skill is **rhythmic independence** – when one voice moves, the other rests; when one leaps, the other steps. Your goal is to create a *conversation*, not a chorus.

### TapScript Example (Blank Bar Invitation)  
In TapScript, a **blank bar** is a silent measure that signals *"your turn to respond."* It is written as `[ ]` with a duration. When you see a blank bar in a harmony invitation, you must fill it with a counter-melody that **complements** the existing line.

```
Tempo: 72 bpm | Key: C minor | Meter: 4/4

Voice 1 (Lead): 
| C5 . . . | . . . . | B4 . . . | . . . . |
| A4 . . . | . . . . | G4 . . . | . . . . |

Voice 2 (Counter) – your job:
| . . . . | [ ] . . . | . . . . | [ ] . . . |
| . . . . | [ ] . . . | . . . . | [ ] . . . |
```

The `[ ]` after each lead phrase is your **blank bar invitation**. You respond with a rhythmically offset line – e.g., start on the "and" of beat 2, use a neighbor tone, and avoid parallel fifths.

**Your response (fill the blanks):**
```
Voice 2 (Counter):
| . . . . | G4 . B4 . | . . . . | F4 . A4 . |
| . . . . | E4 . G4 . | . . . . | D4 . F4 . |
```

Notice: when Voice 1 holds a long note, you move; when Voice 1 is busy, you rest. Your line uses stepwise motion and a passing tone (B4→A4→G4).

### JSON Exercise  
Complete the following exercise. Fill the blank bars with a counterpoint line in the key of A minor. Use at least two syncopations.

```json
{
  "exercise_id": "03_counterpoint_blankbar",
  "key": "A minor",
  "meter": "3/4",
  "voices": {
    "lead": ["A4 . .", "E4 . .", "F4 . .", "D4 . ."],
    "counter": ["[ ] . .", "[ ] . .", "[ ] . .", "[ ] . ."]
  },
  "rules":
