**Lesson: 04 Jazz Voicings — The Blank Bar System & Harmony Invitations**  
**Level:** Journeyman  

---

**Concept**  
Basic triads and seventh chords are static. Jazz voicings are *conversational*. You don’t just play the chart — you respond to space. The **blank bar** (a measure with no written chord) is an invitation, not an error. In TapScript, a blank bar means: *the harmony is open — you may imply, reharmonize, or pass*. Your job is to **hear the invitation** and answer with a voicing that adds color (extensions, alterations, or substitutions) while respecting the tonal center.

---

**TapScript Example**  
```tapscript
// A section: ii–V–I with a blank bar on beat 4 of measure 3
bars:
  | Dm7  G7  | Cmaj7  A7b9 | Dm7  _  | G7  Cmaj7 |

// Blank bar handling: respond to the '_' with a tritone sub passing voicing
voicing_blank:
  mode: "invitation"
  style: "jazz"
  approach: "tritone_sub"  // play Db7#11 resolving to Cmaj7
  rhythm: "syncopated_4ths"
  register: "middle"
  dynamics: "mp"  // softer, as a question
```

---

**JSON Exercise**  
Complete the following. Your blank bar response must use a **quartal voicing** (stacked 4ths) and resolve to the next chord’s 3rd and 7th.

```json
{
  "exercise_id": "jz_04_blankbar",
  "input": {
    "progression": ["Fm7", "Bb7", "Ebmaj7", "_", "Dm7b5", "G7b9", "Cm7"],
    "blank_bar_index": 3,
    "next_chord": "Dm7b5"
  },
  "your_output": {
    "voicing": "____", // e.g., "E-A-D-G" (note names)
    "function": "____", // e.g., "passing diminished" or "sus4 approach"
    "resolve_to": ["____", "____"] // target 3rd and 7th of Dm7b5
  }
}
```

---

**KB Instructions (for your agent memory)**  
- **Blank bar = harmony invitation.** Do not fill with root-position triads. Use *upper structure triads*, *cluster voicings*, or *planing* (parallel motion).  
- **Respond to invitations** within 1–2 beats — treat them as “calls” where you answer with a *t
