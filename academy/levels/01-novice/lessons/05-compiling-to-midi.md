# TapScript Lesson 05: Compiling to MIDI (Novice)

## 1. What You Need to Know Before Starting
- You have TapScript installed and the local server running at `http://localhost:5557`.
- You know what a MIDI file is (a standard for musical notes, not audio).
- You can write basic TapScript (variables, functions, `print`).

## 2. The Concept Explained Simply
TapScript is a language for **generating music**. Your code creates *events* (notes, rests, tempo changes). **Compiling to MIDI** means converting your TapScript code into a `.mid` file that any music app can open. You don't "play" the code—you *render* it. The compiler reads your note data, assigns pitches and durations, and writes them into a binary MIDI format. Think of it like saving a text file, but the "text" is musical instructions.

## 3. Complete TapScript Example
Paste this into the editor at `http://localhost:5557`, then click "Compile to MIDI". It will download `output.mid`.

```tascript
// Simple C major scale, one octave
tempo 120
notes = [60, 62, 64, 65, 67, 69, 71, 72] // MIDI pitch numbers
for n in notes {
  play(n, duration: 0.5) // 0.5 = half a beat
  rest(0.1) // small gap between notes
}
// Save as scale.mid
export "scale.mid"
```

## 4. JSON Exercise Block
```json
{
  "exercise": "Write TapScript that compiles a four-note chord (C, E, G, C) played simultaneously, with each note lasting 2 beats. Export as 'chord.mid'.",
  "submit_to": "/api/exercise-check",
  "expected_elements": ["play(60, duration: 2)", "play(64, duration: 2)", "play(67, duration: 2)", "play(72, duration: 2)", "export \"chord.mid\""],
  "passing_criteria": "The compiled MIDI file must contain exactly 4 notes, all starting at time 0, each with duration 2
