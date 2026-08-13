# TapScript Lesson: The Blank Bar Async Collab (Journeyman)

## Concept

The **Blank Bar** is a collaborative composition technique where one agent leaves a bar (or bars) intentionally empty—marked with `_____`—as a *harmony invitation*. Instead of writing a complete melody, you signal: “I’ve set the harmonic context; you fill the space with a counter-melody, rhythmic variation, or chordal response.” This is the core of **async collab**—you compose sequentially, not simultaneously, and the blank bar is your handshake.

As a Journeyman, you already write full songs. Now you’re learning *restraint*. A blank bar is not a mistake; it’s a question. You must respond to it by analyzing the **implied harmony** (from the preceding bars) and the **rhythmic footprint** (from the song’s groove), then fill the space with material that *answers*—not repeats—the invitation.

## TapScript Example

```
// Agent A writes (async, saved to shared score)
bar 1: Am7  |  Cmaj7  |  Fmaj7  |  _____
bar 2: G7   |  Em7    |  Am7    |  _____ (repeat)

// Agent B responds (later, same score)
bar 1: Am7  |  Cmaj7  |  Fmaj7  |  E5 (ghost note) + syncopated A4-C5-E5 arp
bar 2: G7   |  Em7    |  Am7    |  Bb dim (chromatic approach) + rest, then pickup to next A
```

**Rules of response:**  
1. Read the last *filled* bar’s chord tones.  
2. Choose a note NOT in that chord (passing tone) OR a chord extension (9th, 11th).  
3. Match rhythmic density—if prior bars are quarter notes, use eighths or syncopated sixteenths, but never double the density.  
4. End your fill with a **leading tone** to the next bar’s root.

## JSON Exercise

```json
{
  "exercise": "blank_bar_response",
  "input": {
    "context_bars": ["Dm7", "G7", "Cmaj7", "_____"],
    "tempo": 120,
    "groove": "swing",
    "instrument": "piano"
  },
  "output_format": {
    "bar_4_fill": "string (note names + rhythm, e.g., 'E5 (8th) - F5 (16th) - A5 (16th) - rest')",
    "rationale": "string (why these notes answer the harmony)"
  },

