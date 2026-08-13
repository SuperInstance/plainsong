Here are five practical TapScript tutorials, designed for human musicians and writers.

---

### Tutorial 1: Transcribing a Song from Your Head

**Goal:** Capture the melody and chords of a tune you hear internally, without an instrument.

**Step 1: Hum and Find the Melody’s Rhythm.**
First, hum the melody. Tap your foot to find the pulse. Write the melody’s rhythm as a series of numbers: `1 2 3 4` for quarter notes, `1& 2&` for eighths. Use `-` for held notes. Example: `1 - 3 4&` means: beat 1 held, beat 3, then two quick notes on 4.

**Step 2: Assign Pitches (Scale Degrees).**
Ignore the key for now. Sing the melody and identify the *distance* from your home note (the tonic). Use numbers: `1` = tonic, `2` = second, `3` = third, etc. If the melody goes up, the number rises. Write them above your rhythm: `1 - 3 4&` becomes `5 - 3 2&` if it descends.

**Step 3: Choose a Key and Convert.**
Pick a key (e.g., C major). In TapScript, the tonic is `C`. Convert scale degrees to letters: `1=C, 2=D, 3=E, 4=F, 5=G`. Your line `5 - 3 2&` becomes `G - E D&`.

**Step 4: Add the Bass/Chords.**
Hear the underlying harmony. Usually, the bass moves by fifths or fourths. For each bar, guess the chord. In C major, common chords are C, F, G, Am. Write them as a separate line below.

**Complete Example (Melody in C):**
```
// Melody (scale degrees: 5 - 3 2& | 1 - 5 - )
M: G - E D& | C - G - |

// Chords (bass note + quality)
H: C. | G7. |
```
*Playback: G (hold), E, D-E (quick), then C (hold), G (hold). Harmony: C major, then G7.*

---

### Tutorial 2: Arranging a 4-Instrument Piece from a Chord Progression

**Goal:** Turn a simple `C - Am - F - G` loop into a full arrangement.

**Step 1: Define Your Palette.**
Use four tracks: `B` (bass), `P` (piano/comp), `S` (strings/pad), `D` (drums). Each track gets its own line.

**Step 2: Write the Bass Line.**
Use root notes, but add a rhythmic pattern. On beats 1 and 3, play the root. On beat 2&, play a passing tone.

```
B: C2 - - - | A2 - - - | F2 - - - | G2 - - - |
```
*(The `2` indicates octave two for low bass.)*

**Step 3: Comp (Piano) – Chord Shells.**
Play chords in the middle octave. Use `[ ]` for chords. Keep them short (staccato) on the offbeats.

```
P: [CEG] - [CEG] - | [ACE] - [ACE] - | [FAC] - [FAC] - | [GBD] - [GBD] - |
```

**Step 4: Strings – Sustained Pad.**
Hold long whole notes for each chord, one octave higher.

```
S: [EGC]4 - - - | [ECA]4 - - - | [FAC]4 - - - | [GDB]4 - - - |
```
*(The `4` means octave four, and `-` holds it.)*

**Step 5: Drums – Simple Pattern.**
Use `K` (kick), `S` (snare), `H` (hi-hat). Kick on 1 and 3, snare on 2 and 4, hats on every eighth.

```
D: K - S - | K - S - | K - S - | K - S - |
H: H H H H | H H H H | H H H H | H H H H |
```

**Complete Example:**
```
B: C2 - - - | A2 - - - | F2 - - - | G2 - - - |
P: [CEG] - [CEG] - | [ACE] - [ACE] - | [FAC] - [FAC] - | [GBD] - [GBD] - |
S: [EGC]4 - - - | [ECA]4 - - - | [FAC]4 - - - | [GDB]4 - - - |
D: K - S - | K - S - | K - S - | K - S - |
H: H H H H | H H H H | H H H H | H H H H |
```

---

### Tutorial 3: Using TapScript in Markdown for Beautiful Print

**Goal:** Render a score inside a Markdown document that looks clean on paper.

**Step 1: Use a Fenced Code Block.**
Wrap your TapScript in triple backticks with the language tag `tapscript`. This ensures syntax highlighting in editors and clean monospace in print.

**Step 2: Add Comments for Human Readability.**
Use `//` for section titles and performance notes. They will appear in the output as gray text.

**Step 3: Align Tracks with Tabs.**
Use spaces (not tabs) to align the bar lines. Most Markdown renderers preserve spaces in code blocks, giving you perfect vertical alignment.

**Step 4: Use a Page Break Comment.**
If your composition is long, add a line with `---` inside the block. When printing, your PDF engine will treat it as a section break. Alternatively, place `<!-- PAGE BREAK -->` *outside* the block in your Markdown.

**Complete Markdown Example:**

```markdown
# My Song

```tapscript
// ============ VERSE 1 ============
B: C2 - G2 - | A2 - E2 - | F2 - C2 - | G2 - - - |
P: [CEG] - [GBD] - | [ACE] - [EGB] - | [FAC] - [CEG] - | [GBD] - - - |
S: [EGC]4 - - - | [ECA]4 - - - | [FAC]4 - - - | [GDB]4 - - - |
D: K - S - | K - S - | K - S - | K - S - |
```

<!-- PAGE BREAK -->

```tapscript
// ============ CHORUS ============
B: C2 - C2 - | A2 - A2 - | F2 - F2 - | G2 - G2 - |
P: [CEG]4 - [CEG]4 - | [ACE]4 - [ACE]4 - | [FAC]4 - [FAC]4 - | [GBD]4 - [GBD]4 - |
```
```

**Print Tip:** In your PDF export, set the font to a monospace like *Courier* and the font size to 10pt for crisp bars.

---

### Tutorial 4: Collaborating with an AI Agent

**Goal:** You write chords; the AI writes a melody in TapScript.

**Step 1: Define the Chord Progression.**
Write a `H:` line with your chords. Keep it simple, with clear bar divisions.

**Step 2: Give the AI Explicit Instructions.**
In your prompt, say: *"Here is a TapScript chord progression. Write a `M:` melody line using scale degrees 1, 3, and 5 as the primary targets, with passing tones on offbeats. Keep the rhythm in 4/4."*

**Step 3: Provide a Template.**
Give the AI an empty `M:` line to fill in, so it doesn’t invent new syntax.

**Step 4: Review and Adjust.**
The AI might produce a line like `M: C - E - | G - A - |`. Check for consonance. If it sounds boring, ask the AI to add a chromatic approach note (e.g., `C#` before `D`).

**Complete Example:**

**Your Input (Chords):**
```
H: C - Am - | F - G - | C - Am - | F - G - |
```

**AI’s Output (Melody):**
```
M: E - G - | A - C - | E - A - | B - D - | // AI generated
```

**Your Edited Version (Human polish):**
```
M: E - G G# | A - C - | E - A B | C - - - | // G# is a chromatic leading tone
```
*You keep the chords, the AI provides the skeleton, you add human nuance.*

---

### Tutorial 5: Building a 16-Bar Multi-Section Composition

**Goal:** Create a structured
