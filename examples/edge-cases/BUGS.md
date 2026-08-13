# TapScript v2 — Edge-Case Bug Reports

Play-tested by Navigation (KimiCode) against the live app at `localhost:5557`
(parser: `scripts/tapscript_v2.py`). Each bug was reproduced via `POST /api/compile`
and verified by inspecting the resulting MIDI with `pretty_midi`.

Severity key: **HIGH** = wrong musical output or silent data loss,
**MEDIUM** = valid-looking input silently misinterpreted,
**LOW** = cosmetic / informational.

---

## BUG-1 (HIGH): Non-standard token counts are not rescaled — polyrhythm is impossible

**Repro:** `edge-1-polyrhythm.tap`

A bar's timing is computed as `slot_time = bar_start + token_index * slot_dur`,
where `slot_dur` is fixed by `subdivision:` (2 or 4 slots per beat). The token
count in a bar is never rescaled to fit the bar.

- 12 tokens in a 16-slot bar ("3 against 4" in `@flash`): the three notes land
  on beats 1, 2, 3 at 0.000s / 0.500s / 1.000s and beat 4 is silent. A true
  3:4 polyrhythm needs onsets at 0 / 0.667 / 1.333s — unrepresentable.
- The "polyrhythm" the notation implies is silently rendered as plain meter
  with a dead beat.

**Expected:** either rescale N tokens evenly across the bar, or reject
non-standard token counts with a warning. **Actual:** silent misplacement.

---

## BUG-2 (HIGH): Overfilled bars silently destroy notes

**Repro:** probe — 17 tokens in a 16-slot bar, token 17 a note:

```
@wesley | C4 . . . . . . . . . . . . . . . E4 | G4 . . . | vel: 70
```

The 17th token (`E4`) starts at slot 16 = exactly the next bar's downbeat
(2.000s). End-of-bar clamping (`n.end = min(n.end, bar_end)`) then sets its
end to 2.000s — a zero-duration note, dropped on MIDI write. The note
**vanishes without any error or warning**. Overflow sustains are likewise
clamped silently (`edge-1` section V2 relies on this).

**Expected:** overflow tokens rejected, or allowed to ring into the next bar.
**Actual:** silent note loss at bar boundaries.

---

## BUG-3 (MEDIUM): Mid-song tempo changes are silently ignored

**Repro:** `edge-2-tempo-shifts.tap`

`tempo: 200` and `tempo: 60` lines placed inside sections are not section
headers and don't start with `Chords:`/`Melody:`/`Lyrics:`/`@`, so the parser
skips them without a word. The compiled MIDI has a single tempo (60 BPM) for
all 6 bars; `pm.get_tempo_changes()` returns `[60.0]`.

The format has no tempo-directive syntax at all — 60 → 200 → 60 mid-song is
unrepresentable. **Expected:** per-section `tempo:` support, or at minimum a
warning that the line was unrecognized. **Actual:** silent no-op.

---

## BUG-4 (MEDIUM): Empty bars collapse, shifting all later music earlier

**Repro:** probe —

```
@wesley | C4 . . . || E4 . . . | vel: 70
```

`_parse_bar_line` skips empty segments (`if not bar_str: continue`), so the
intentionally empty bar disappears. `E4` renders at 2.000s (bar 2) instead of
4.000s (bar 3) — everything after the empty bar shifts one bar earlier.
Contrast with `| . . . . |` (dot-filled), which correctly holds a bar open.

**Expected:** an empty `| |` segment counts as a silent bar. **Actual:** the
bar is deleted and the grid silently re-indexes.

---

## BUG-5 (MEDIUM): Invalid tokens fail silently; `errors` in the compile response is always empty

**Repro:** probes and `edge-5-kitchen-sink.tap`

- Unknown chord symbol `Hq7` → treated as sustain (chord vanishes, harmony
  holds). No warning.
- Garbage melody token `hello` → treated as rest. No warning.
- `/api/compile` returns `"errors": []` in every case, including all of the
  above and BUGs 1–4. The field exists but nothing ever populates it.

**Expected:** a warnings channel listing unrecognized tokens, wrong token
counts per bar, and dropped notes. **Actual:** total silence.

---

## BUG-6 (LOW): Key name reported enharmonically

**Repro:** `edge-5-kitchen-sink.tap` declares `key: Bbm`; `/api/parse`
reports `"key": "A#m"`. The internal flat→sharp canonicalization leaks into
the API response. Musically harmless, confusing in the UI.

---

## Notes on what did NOT break

- `edge-3-dense-chords.tap`: 6-note and 8-note simultaneous chords render
  correctly; degenerate tokens (`e2-.-g2`, `c3--e3`) degrade gracefully to
  2-note chords.
- `edge-4-players-only.tap`: no `Chords:`/`Melody:`/`Lyrics:` lines — compiles
  fine, drum track correctly flagged `is_drum`.
- `edge-5-kitchen-sink.tap`: every spec feature in one file — all chord
  qualities (`sus4`, `add9`, `m6`, `9`, `aug`, `dim`, `maj7`, `7`), flats in
  note names, `vel:`, swing, multiple players/sections — compiles correctly.
  Caveat: the underfilled bridge bar (`Melody: | A4 . |`) occupies only beat 1
  rather than stretching to fill the bar (same root cause as BUG-1).
