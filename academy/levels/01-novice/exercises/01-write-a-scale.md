# TapScript Exercise: 01 — Write a Scale

## Task Description
You are a novice TapScript agent. Your task is to write a simple **major scale** (C major) using TapScript syntax. The scale should be one octave, ascending from C4 to C5, and each note must be represented as a `note` object with `pitch` and `duration` properties. Use a `scale` array to hold the notes, and ensure the script is syntactically valid TapScript.

## JSON Criteria
```json
{
  "expected_elements": [
    "scale array",
    "note objects with pitch and duration",
    "pitches: C4, D4, E4, F4, G4, A4, B4, C5",
    "duration: 1 (whole note) for each"
  ],
  "passing_criteria": [
    "Array named 'scale' exists",
    "Array length equals 8",
    "Each element is a note object with pitch and duration",
    "Pitches match the C major scale exactly",
    "All durations are numeric and equal to 1"
  ]
}
```

## Hint
Think of TapScript as JSON-like. A note looks like `{ "pitch": "C4", "duration": 1 }`. Use `[ ]` for the array.

## Expert Solution
```tascript
scale = [
  { "pitch": "C4", "duration": 1 },
  { "pitch": "D4", "duration": 1 },
  { "pitch": "E4", "duration": 1 },
  { "pitch": "F4", "duration": 1 },
  { "pitch": "G4", "duration": 1 },
  { "pitch": "A4", "duration": 1 },
  { "pitch": "B
