# TapScript Lesson 01: Chord Progressions — Apprentice Level

**Concept: The "Function Ladder"**  
A chord progression is a sequence of harmonies that create tension and release. At apprentice level, you move beyond memorizing I–IV–V and learn **functional roles**: Tonic (T, home), Subdominant (S, departure), Dominant (D, tension). The golden rule: **T → S → D → T** (with any step skippable, but never D → S directly — that’s a "retrograde" that sounds weak unless intentional).

**TapScript Example**  
TapScript uses `prog` blocks with `chord` atoms. Each chord gets a `func` tag and a `beat` duration.

```tapscript
prog "Apprentice_01" {
  key: C major
  meter: 4/4
  section A {
    chord C  func:T  beat:2
    chord F  func:S  beat:2
    chord G  func:D  beat:2
    chord C  func:T  beat:2
  }
  section B {
    chord Am func:T(relative) beat:2
    chord Dm func:S(secondary) beat:1
    chord G7 func:D(extended) beat:2
    chord C  func:T  beat:3
  }
}
```

Notice: `G7` adds a 7th for extra tension. `Am` is marked as relative Tonic (vi) — still feels like home but darker.

**JSON Exercise Block**  
Complete the progression. Fill in missing `func` and `beat` values (use only T, S, D). The last chord must resolve to T.

```json
{
  "exercise_id": "tap_01_apprentice",
  "key": "G major",
  "meter": "4/4",
  "given": [
    {"chord": "G",  "func": "T", "beat": 2},
    {"chord": "C",  "func": "___", "beat": 2},
    {"chord": "D",  "func": "___", "beat": 2},
    {"chord": "Em", "func": "___", "beat": 1},
    {"chord": "C",  "func": "___", "beat": 1},
    {"chord": "G",  "func": "___", "beat": 3}
  ],
  "constraints": ["No D→S", "Last chord must resolve
