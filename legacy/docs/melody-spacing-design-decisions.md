# Melody Duration-by-Spacing: Design Decisions

## Overview

Casey proposed a notation redesign where note duration is determined by characters
between notes (tildes `~` or dashes `-`) rather than explicit duration markers or
fixed subdivision slots. This document records the decisions made during implementation.

## Date
Implemented: 2026-08-13

## Notation Formats from the Proposal

Three formats were proposed:

| Format | Sustain char | Example | Whole note | Eighth note |
|--------|-------------|---------|-----------|-------------|
| A: Tildes | `~` | `C4~~~~` | 4 tildes | 0 tildes |
| B: Dashes | `-` | `C4----` | 4 dashes | 0 dashes |
| C: Blocks | `█` | `████C4` | 4 blocks | 1 block |

### Duration mapping (all formats)

Each sustain character = one eighth-note duration. The base note token already
occupies one eighth, so:

| Sustain chars | Total duration | Note type |
|--------------|---------------|-----------|
| 0 (bare note) | 1 eighth | eighth note |
| 1 | 2 eighths = 1 quarter | quarter note |
| 2 | 3 eighths | dotted quarter |
| 3 | 4 eighths = 1 half | half note |
| 7 | 8 eighths = 1 whole | whole note |

This is the "grid unit = eighth note" approach from the proposal.

## Implementation Decisions

### D1: Both formats A and B supported; C deferred

**Decision:** Implement tilde (`~`) and dash (`-`) sustain formats. Defer block (`█`) notation.

**Rationale:**
- Tildes and dashes are ASCII — work in any editor, any encoding
- Block characters require Unicode and are harder to type
- Dashes have a natural "tie line" visual metaphor
- Tildes are distinct enough from other notation to avoid ambiguity
- Block notation can be added later as a display layer

### D2: Sustain characters attach to the PRECEDING note

```
C4~~ D4 - E4
```

- `C4~~` = C4 sustained for 3 eighth durations (quarter + dotted eighth... actually 3 eighths = dotted quarter)
- `D4` = D4 for 1 eighth
- `-` = rest for 1 eighth
- `E4` = E4 for 1 eighth

The sustain characters are part of the note token itself, not separators between notes.

### D3: Bars still delimited by `|`

The bar pipe delimiter is preserved from existing TapScript. Within a bar,
the total duration of all notes (including sustains) should add up to the
bar's total beats. We don't enforce this — we just parse and let the compiler
lay it out — but a linter/warning could be added later.

### D4: Backward compatibility with v1 notation

The v1 engine (`tapscript.py`) uses scale degrees (digits 1-7) with `,` and `:`
separators. The spacing notation uses absolute pitches (C4, D4, etc.). These
are mutually exclusive on a single line:

- **If a melody line contains tokens matching `[A-Ga-g][#b]?\d[~\-]*`** → parse as spacing notation
- **Otherwise** → parse as legacy v1 scale-degree notation

This means existing `.tap` files using scale degrees continue to work exactly
as before. The new notation is detected automatically.

### D5: Rests in spacing notation

- `r` followed by sustain chars = rest of that duration: `r~~` = 3-eighth rest
- Bare `-` = eighth rest (same as v1)
- `r` = eighth rest

### D6: Chords in spacing notation

Using `+` to stack notes (from the proposal):
```
C4~~+E4~~+G4~~
```
All notes in a chord share the same duration. The `+` separator connects notes
that play simultaneously. The sustain character count on the LAST note token
determines the chord's duration (all notes must have matching sustain counts —
if they don't, we use the maximum and log a warning).

### D7: NoteEvent extended, not replaced

Added new fields to the existing `NoteEvent` dataclass:

```python
@dataclass
class NoteEvent:
    degree: int           # scale degree 1-7 (legacy)
    alteration: int       # chromatic alteration (legacy)
    octave: int           # -1, 0, +1 (legacy)
    duration_div: int     # duration divisor: 1=quarter, 2=eighth, 4=sixteenth (legacy)
    is_rest: bool = False
    sustain: bool = False
    # NEW: spacing notation fields
    absolute_pitch: Optional[str] = None   # e.g. "C4", "D#5"
    duration_eighths: int = 1              # duration in eighth notes (1=eighth, 2=quarter, etc.)
    is_chord_note: bool = False            # True if this note is part of a chord
    chord_index: int = 0                   # position within chord (0=root)
```

When `absolute_pitch` is set, the compiler uses it directly instead of computing
from degree/key. When `duration_eighths` > 0, it overrides `duration_div` for
timing calculations.

### D8: Compiler changes

The MIDI compiler now handles spacing-based notes:
- If a `NoteEvent` has `absolute_pitch` set, convert directly to MIDI note number
- If `duration_eighths` is set (>0), use it for note duration instead of the
  subdivision-based slot system
- Chord notes (is_chord_note=True) share the same start time

### D9: Detection heuristic

A line is a "spacing notation melody" line if:
1. It's already classified as a melody line (or has `Melody:` prefix for v2 compat)
2. AND at least one token matches the pattern `[A-Ga-g][#b]?\d[~\-]*`

This is checked before falling back to legacy v1 parsing.

## Edge Cases

### E1: Mixed notation in one line
Not supported. A line is either spacing notation OR legacy. Mixing produces
unpredictable results. Future: could add a warning.

### E2: Sustain count doesn't fill the bar
If notes' total duration < bar duration, the remaining time is silence (implicit rest).
If notes' total duration > bar duration, notes overflow into the next bar (current
behavior matches v1 — we don't truncate).

### E3: Octave numbers vs scale degrees
`C4` is unambiguous (letter + number). `4` alone is a scale degree in v1.
The detection regex requires a letter prefix to distinguish.

### E4: Flat/sharp notation
`Bb4` and `A#4` are both valid. The parser normalizes flats to sharps internally
(consistent with existing v1 behavior).

## Open Questions

1. **Should we add a `spacing: on/off` header directive?** Currently auto-detected.
   Could add explicit opt-in for clarity.

2. **Triplet support?** The current eighth-grid doesn't support triplets. Could
   add a `/3` modifier: `C4~~/3` = triplet quarter. Deferred.

3. **Should block notation (Format C) be added as a rendering output?** It could
   be pretty for display, even if not used for input.

4. **Integration with v2 engine?** Currently implemented in v1 engine only.
   Could port to v2 since the notation style (absolute pitches, labeled lines)
   is closer to v2's philosophy.
