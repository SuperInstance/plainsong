# TapScript Lesson 02: Your First Bar

## Before You Start
- You can read TapScript syntax (even if you’ve never written it).
- You have a running local compiler at `http://localhost:5557`.
- You know what a "bar" is: 4 beats, the basic loop unit in live coding music.

## The Concept (Simply Put)
A **bar** is a musical container. In TapScript, you create a bar by defining a sequence of **steps** (usually 16 for a 4-beat bar). Each step holds a note or a rest. Your first bar is just a list of pitches — numbers — placed inside a `bar` block. The compiler turns that into sound.

## Complete Example (Compile at http://localhost:5557)
```
// my_first_bar.tap
synth drums {
    kick: [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0]
}

bar kick_bar {
    play drum kick
    steps 16
    notes [60,0,60,0, 60,0,60,0, 60,0,60,0, 60,0,60,0]
}

// Run it
loop kick_bar
```
This plays a simple kick drum on beats 1 and 3, with a bass note (MIDI 60) every other step.

## Exercise Block
```json
{
  "exercise": "Create a bar named 'melody_bar' with 16 steps. Put the note sequence [72, 0, 74, 0, 76, 0, 72, 0, 71, 0, 69, 0, 67, 0, 65, 0] inside it. Use a synth named 'pluck'.",
  "submit_to": "/api/exercise-check",
  "expected_elements": [
    "synth pluck",
    "bar melody_bar",
    "steps 16",
    "notes [72, 0, 74, 0, 76, 0, 72, 0, 71, 0, 69, 0, 67, 0, 65, 0]"
  ],
  "passing_criteria": "The bar
