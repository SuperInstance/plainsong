# TapScript Exercise: 02 – Four Bars of Rest

**Task Description:**  
You are a novice agent learning TapScript. Your goal is to write a script that creates **four bars of rest** (i.e., no notes, only silence) in a 4/4 time signature with a tempo of 120 BPM. The script must be syntactically correct and produce a musical output with exactly 16 beats of rest (4 bars × 4 beats). Use the `R` symbol for rests and specify the time signature and tempo at the top.

---

```json
{
  "expected_elements": [
    "tempo declaration (e.g., tempo: 120)",
    "time signature (e.g., time: 4/4)",
    "use of rest symbol 'R' with duration (e.g., R4 for quarter rest)",
    "total rest duration equals 16 quarter notes (4 bars × 4 beats)"
  ],
  "passing_criteria": [
    "Script starts with valid tempo and time signature lines",
    "Contains at least one rest symbol per bar (or continuous rests summing to 16 beats)",
    "Output duration is exactly 4 bars (no extra notes or rests)",
    "No syntax errors in TapScript"
  ]
}
```

---

**Hint:**  
Think of each bar as 4 quarter-note rests (`R4`). You can write `R4 R4 R4 R4` repeated four times, or use a repeat syntax if you know it. For a novice, writing all 16 rests explicitly is acceptable.

---

<details>
<summary>Expert Solution (hidden until you pass)</summary>

```tascript
tempo: 120
time: 4/4

R4 R4 R4 R4
R4 R4 R4 R4
R4 R4 R4 R4
R4 R4 R4 R4
```

This
