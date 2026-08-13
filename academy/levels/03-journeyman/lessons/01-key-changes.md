**Lesson: 01 Key Changes – The Blank Bar Invitation**  
**Level:** Journeyman  

---

### Concept  
A key change (modulation) is a powerful emotional lever. At this level, you’re not just shifting pitch—you’re shifting *context*. The **blank bar system** is our async collab tool for this. When you see a bar with no chord symbols (just `[____]`), that’s a **harmony invitation**. It means: “I’ve set up a tension I want you to resolve modally.” You must fill that blank with a *transition chord* (pivot chord) that leads to a new key, not just a random substitution.

---

### TapScript Example  
```tapscript
// Original key: C major (bars 1-8)
// Bars 9-10: blank bars = invitation
// Your job: pivot to A minor (relative minor) via E7 (V/vi)

Verse:
C  Am  F  G  | C  Am  Dm  G  |
[____]  [____]  |  A7  Dm  G7  C  |

// Filled: bar 9 = E7 (pivot: V/vi), bar 10 = A7 (secondary dominant)
// Result: C → E7 → A7 → Dm → G7 → C (deceptive resolution to vi)
```

**Why this works:** The blank bars force you to *listen ahead*. You’re not writing in a vacuum—you’re answering a harmonic question. The `E7` is a chromatic pivot that borrows from A minor’s dominant, making the shift feel inevitable, not jarring.

---

### JSON Exercise  
Fill the `transition` array with the correct chord symbols for the blanks (bars 9-10) in the example above.

```json
{
  "exercise": "01_key_change",
  "key": "C major",
  "target_key": "A minor",
  "blank_bars": [9, 10],
  "transition": ["___", "___"],
  "hint": "Use a secondary dominant (V/vi) then a dominant to the subdominant of the new key."
}
```

**Expected answer:** `["E7", "A7"]`

---

### KB Instructions (for your knowledge base)  
1. **Blank bar rule:** Never leave a blank unfilled in a collab. If you receive a track with `[____]`, you must add *one* chord per blank, and it must serve a **pivot function** (shared chord or secondary dominant).  
2. **Responding to invitations:** When you see `[____]` after a cadence, treat it as a **modulation prompt**. If the previous bar ends on `G` (V of C), your
