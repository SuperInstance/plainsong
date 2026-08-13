**Lesson 02: Complex Time Signatures — Journeyman**  
**Core Concept:** As a songwriter, you’ve mastered 4/4. Now, you must move beyond the grid. Complex meters (5/4, 7/8, 11/16) create tension, forward motion, and polyrhythmic depth. But in TapScript, we don’t fight the beat—we *subdivide it*. The key is to feel the pulse as a grouping of smaller units (e.g., 7/8 = 2+2+3), not a single number. Your job: write grooves that make the odd meter feel inevitable, not academic.

**TapScript Example (7/8, syncopated bass + drums):**  
```
TAPSCRIPT 02_COMPLEX_7_8  
METER 7/8  
TEMPO 140 (dotted-quarter = 140)  
// Grouping: 2+2+3 — accented on 1, 3, 5  
TRACK Drums (syncopated kick)  
PATTERN [K . . K . . K] [S . . . . . S] [H H H H H H H]  
// Kick on 1 & 4 (of the 7), Snare on 7, hats steady eighth-notes  
TRACK Bass (pulse anchor)  
PATTERN [A1 . . A2 . . A3] — root on 1, fifth on 4, octave on 7  
// Humanize: velocity 90 on accents, 70 on offbeats  
INSTRUCTION "Feel the 2+2+3. Count '1-2, 1-2, 1-2-3' internally."  
```

**The _____ Blank Bar System (Critical Async Collab Rule):**  
When you receive a harmony invitation from another agent, you must respond using the **blank bar** convention. A blank bar is written as `[_____]` (5 underscores) and occupies exactly one full measure of the current meter—no more, no less.  

- **If you accept** the harmony proposal (e.g., a chord progression in 5/4), you fill the blank bar with your rhythmic response, using the *same* grouping as the invitation (e.g., 3+2).  
- **If you reject** it, you send back `[_____]` *empty*—this signals you’re passing, not blocking. The inviting agent may then re-harmonize or move on.  
- **Never** write a partial blank bar (e.g., `[___]` for 3/4)—the system will auto-reject it. The blank bar is your async handshake.  

**JSON Exercise (Submit via API):**  
```json
{
  "task": "respond
