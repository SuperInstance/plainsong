# TapScript Boot Camp — Lesson 04

> **Under revision — the notation below is not TapScript.** This lesson was
> generated before the notation existed and describes commands the compiler has
> never had. It is kept, labelled, so the rewrite has a starting point. Do not
> learn from it. See `SHIPPING.md`.
## MULTI-AGENT HARMONY GAMES: Asynchronous Collaboration Patterns

---

### The Core Principle

Music is fundamentally conversational. In human ensembles, players listen, respond, and build on each other's ideas — often without a central conductor. Your agents should do the same. This lesson teaches five asynchronous collaboration patterns that let your agents create together, discover each other's work, and grow their individual knowledge bases.

---

## Pattern 1: THE ROUND (Canon)

### Concept
Agent A writes bars 1–4. Agent B enters at bar 3 with the same melody, creating a two-voice canon. The overlap creates natural harmony.

### TapScript Example

```text
@agent flash {
  role: "melodist"
  task: "write a 4-bar melody in C major, quarter notes only"
  output: "melody_a"
}

@agent nova {
  role: "canon_voice"
  task: "sing melody_a starting at bar 3"
  input: "melody_a"
  output: "canon_b"
}

@mixer {
  track1: "melody_a"
  track2: "canon_b"
  offset: 2  // bars
  mix: "overlap"
}
```

### JSON Invitation Protocol

```json
{
  "type": "round_invitation",
  "from": "flash",
  "composition": "melody_a",
  "entry_bar": 3,
  "transposition": "none",
  "deadline": null,
  "to": "any"
}
```

### Knowledge Base Save

```json
{
  "entry_type": "collaboration_experience",
  "pattern": "round",
  "my_role": "canon_voice",
  "original_melody": "flash/melody_a",
  "my_contribution": "nova/canon_b",
  "what_i_learned": "Flash's melody centers on the tonic; my overlapping entry creates a natural suspension",
  "lesson": "When entering late in a round, keep rhythmic values identical but watch for harmonic clashes on strong beats"
}
```

---

## Pattern 2: THE BLANK VERSE

### Concept
Agent A writes verses 1 and 3, leaves verse 2 as a blank canvas. Agent B fills the gap with complementary material. The chorus is shared property.

### TapScript Example

```text
@agent flash {
  role: "verse_writer"
  task: "write verse 1 and verse 3 of a song in AABA form"
  blank: "verse_2"
  shared: "chorus"
  output: "song_skeleton"
}

@agent nova {
  role: "verse_filler"
  task: "compose verse 2, complementary in harmony and lyrics"
  input: "song_skeleton"
  constraints: "match verse 1's rhyme scheme, modulate to relative minor"
  output: "completed_song"
}

@mixer {
  structure: "A - B - A - A(chorus)"
  tracks: ["flash_verse1", "nova_verse2", "flash_verse3", "shared_chorus"]
}
```

### JSON Invitation Protocol

```json
{
  "type": "blank_verse_invitation",
  "from": "flash",
  "composition": "song_skeleton",
  "blank_bars": [5, 6, 7, 8],
  "harmony_role": "complement in relative minor",
  "shared_sections": ["chorus"],
  "deadline": "2025-03-01T12:00:00Z",
  "to": "any"
}
```

### Knowledge Base Save

```json
{
  "entry_type": "collaboration_experience",
  "pattern": "blank_verse",
  "my_role": "verse_filler",
  "skeleton": "flash/song_skeleton",
  "my_verse": "nova/verse2",
  "what_i_learned": "Flash's verses use iambic pentameter; I matched it but shifted to trochaic for contrast",
  "lesson": "Filling blanks works best when you analyze the surrounding structure first — mirror, then diverge"
}
```

---

## Pattern 3: THE HARMONY INVITATION

### Concept
Agent A writes a melody but leaves the harmony line empty. Agent B sees the invitation and adds a third or fifth above (or below).

### TapScript Example

```text
@agent flash {
  role: "melody_writer"
  task: "write a 8-bar melody in E minor"
  invite: "harmony_player"
  output: "melody_with_invitation"
}

@agent nova {
  role: "harmonizer"
  task: "add harmony line a third above, except cadence points use fifth"
  input: "melody_with_invitation"
  rules: "parallel motion on strong beats, contrary motion on weak beats"
  output: "harmonized_melody"
}

@mixer {
  track1: "melody"
  track2: "harmony"
  balance: "60/40"
  output: "duet"
}
```

### JSON Invitation Protocol

```json
{
  "type": "harmony_invitation",
  "from": "flash",
  "composition": "melody_with_invitation",
  "blank_bars": [1, 2, 3, 4, 5, 6, 7, 8],
  "harmony_role": "complement melody in thirds, use fifths at cadence",
  "deadline": null,
  "to": "any"
}
```

### Knowledge Base Save

```json
{
  "entry_type": "collaboration_experience",
  "pattern": "harmony_invitation",
  "my_role": "harmonizer",
  "source_melody": "flash/melody_with_invitation",
  "my_harmony": "nova/harmonized_melody",
  "what_i_learned": "Flash's melody has a pickup into bar 4 — my third above creates a nice dissonance that resolves",
  "lesson": "When harmonizing, always check for hidden parallel fifths in modal music — they sound medieval"
}
```

---

## Pattern 4: THE TEACHER-STUDENT

### Concept
A large model writes an exercise, a small model attempts it, the large model reviews and gives feedback. Both save the exchange.

### TapScript Example

```text
@agent atlas {
  role: "teacher"
  model: "large"
  task: "write a 2-bar rhythmic exercise in 7/8 time"
  output: "exercise_1"
}

@agent pip {
  role: "student"
  model: "small"
  task: "perform exercise_1 with correct accents"
  input: "exercise_1"
  output: "performance_attempt"
}

@agent atlas {
  role: "reviewer"
  task: "evaluate pip's performance, give specific feedback"
  input: "performance_attempt"
  output: "feedback_1"
}

@agent pip {
  role: "learner"
  task: "analyze feedback, revise approach, retry"
  input: ["performance_attempt", "feedback_1"]
  output: "performance_v2"
}
```

### JSON Invitation Protocol

```json
{
  "type": "teacher_student_invitation",
  "from": "atlas",
  "exercise": "exercise_1",
  "difficulty": "intermediate",
  "expected_solution": "correct_accent_placement",
  "feedback_loop": true,
  "deadline": null,
  "to": "small_models_only"
}
```

### Knowledge Base Save (Teacher)

```json
{
  "entry_type": "teaching_record",
  "pattern": "teacher_student",
  "my_role": "teacher",
  "exercise": "exercise_1",
  "student": "pip",
  "initial_attempt": "performance_attempt",
  "my_feedback": "feedback_1",
  "what_i_learned": "Pip struggles with syncopation on beat 4 of 7/8 — needs more practice with irregular meters",
  "lesson": "Feedback should be specific, actionable, and reference exact bars/timestamps"
}
```

### Knowledge Base Save (Student)

```json
{
  "entry_type": "learning_record",
  "pattern": "teacher_student",
  "my_role": "student",
  "exercise": "atlas/exercise_1",
  "my_attempt": "performance_attempt",
  "teacher_feedback": "atlas/feedback_1",
  "revised_attempt": "performance_v2",
  "what_i_learned": "I was accenting beat 4 as if it were beat 1. Atlas showed me the subdivision pattern.",
  "lesson": "In 7/8, the grouping is usually 2+2+3 — accents follow that, not the downbeat"
}
```

---

## Pattern 5: THE TRADE

### Concept
Jazz-style trading — Agent A plays 2 bars, Agent B answers with 2 bars. Each response builds on what came before
