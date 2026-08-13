# TapScript v2 — Structural & Spatial Analysis

Navigation officer's play-test report. Based on reading `scripts/tapscript_v2.py`
and compiling the five boundary-condition compositions in
`examples/edge-cases/` through the live API. Findings cross-referenced with
`examples/edge-cases/BUGS.md`.

## 1. How the pipe/space/grid system actually works

The format looks spatial — monospace columns, pipe-delimited bars, one token
per grid cell — but the grid is **syntactic, not temporal**. The compiler
derives time from *token index*, not from any property of the bar:

```
slot_dur   = beat_dur / (2 if subdivision <= 8 else 4)   # fixed per song
slot_time  = bar_start + token_index * slot_dur          # per token
```

Consequences:

- **The pipe does not bound time.** A bar is whatever number of tokens you
  typed. 12 tokens in a 16-slot bar end at beat 3 (BUG-1); 17 tokens overrun
  the bar line, and the overrun notes are clamped to zero duration and dropped
  (BUG-2). The visual `|` suggests a wall; the compiler treats it as a label.
- **Empty bars vanish.** `| |` between pipes is skipped during splitting, so
  the bar array re-indexes and all later bars shift earlier (BUG-4). Only
  dot-filled bars (`| . . . . |`) genuinely hold space.
- **Subdivision is binary.** `subdivision: 8th` → 2 slots/beat; anything else
  → 4 slots/beat. There is no 3. Triplets, 6/8, 12/8, and true polyrhythm are
  outside the representable set — not wrong, just silently approximated.
- **Whitespace inside a bar is meaningless** beyond token separation. The
  pleasing column alignment in the examples is purely for the human reader;
  aligning `E4` above `Am` has no effect on timing. The format *looks* like a
  piano roll grid but behaves like a token stream.

### Non-standard subdivisions: the verdict

The grid handles exactly two cases well (8 tokens/bar, 16 tokens/bar in 4/4).
Every other token count produces one of three silent failure modes:
compression (underfill), truncation/clamping (overfill), or bar deletion
(empty). Nothing warns.

## 2. Where the parser is fragile vs robust

**Robust — genuinely hard to crash:**

- Note parsing: case-insensitive, sharps and flats, any octave. Degenerate
  chord tokens (`e2-.-g2`, `c3--e3`) degrade to fewer notes instead of
  erroring.
- Chord vocabulary: 16 qualities plus a longest-prefix fallback; unknown
  qualities fall back to major triad rather than failing.
- Missing line types: players-only compositions compile fine; chord/melody
  tracks are only created when content exists.
- Missing metadata: every field has a sane default (C major, 120 BPM, no
  swing, 16th).
- Unknown players get piano; `drums` in the name flips to a GM drum track.

**Fragile — fails *silently*, which is worse than failing loudly:**

- **No validation anywhere.** Token-count mismatches, unrecognized lines
  (`tempo: 200` mid-score — BUG-3), unknown chord symbols (`Hq7` → sustain),
  garbage tokens (`hello` → rest) all pass without a whisper. The compile
  API's `errors: []` field is vestigial.
- **Bar-count skew across line types.** `Chords:` with 4 bars next to
  `Melody:` with 3 simply extends/shrinks per line; nothing checks that lines
  in a section agree on bar count or slot count.
- **Zero-duration note destruction at bar boundaries** (BUG-2).
- **Single global tempo/meter**, hardcoded 4 beats/bar. Form and groove are
  fixed at parse time with no per-section override.
- **Chord voicing is pinned to octave 4** regardless of key or context —
  cosmetic, but it means `Chords:` and `@player` chords live in different
  registers with no author control.

The pattern: the parser is robust against *malformed* input and fragile
against *meaningful but non-standard* input — precisely the input a composer
writes when pushing the notation.

## 3. Recommendations: making the format spatially regular

In priority order, cheapest first:

1. **Validate slot counts; populate `errors`.** For each bar of each line,
   compare `len(tokens)` against `slots_per_bar` (8 or 16). Underfill →
   warning; overfill → warning + explicit policy (reject, or truncate with
   notice). Emit unrecognized lines and tokens as warnings. This converts
   every silent failure above into a visible one without changing the format.
2. **Preserve empty bars.** Count empty `| |` segments as bars of implicit
   rests instead of skipping them. One-line change in `_parse_bar_line`;
   makes the pipe structure honest.
3. **Per-section metadata.** Let a section header carry overrides —
   `[C] (Chorus - tempo: 200 - swing: 20%)` — parsed into the section dict and
   applied at compile time via tempo changes in the MIDI. This makes
   `edge-2-tempo-shifts.tap` representable.
4. **Declare beats-per-bar.** A `meter: 3/4` metadata field (default 4/4)
   fixes slot math for waltzes and 6/8, and makes slot-count validation
   meter-aware.
5. **Tuplets, minimally.** Rather than free rescaling (which breaks the
   one-token-one-slot mental model), add a bracketed tuplet token:
   `[E3:G3:B3]/3` occupying one slot's bar-fraction. This keeps grid
   regularity while admitting 3-against-4 — the `edge-1` case.
6. **Optional chord octave.** `Chords@3:` or a metadata `chord_octave: 3` so
   pad chords and player chords can share register.

## 4. Enforcing alignment between Chords / Melody / Lyrics / @player

Alignment today is by **bar index only**, and only within a section. To make
the visual grid enforceable:

- **Bar-count agreement per section.** After parsing a section, every line
  should have the same number of bars (or be allowed to omit trailing bars
  explicitly). Mismatch → warning naming the lines and counts.
- **Slot-count agreement per bar.** Chords/Melody/@player bars should carry
  exactly `slots_per_bar` tokens; Lyrics should be exempted or given their own
  rule (see below) since syllables don't map 1:1 to slots.
- **Lyrics need a separate contract.** They're free text today — tokens are
  stored but never rendered to MIDI, so lyric timing is decorative. Either
  document that ("lyrics are aligned by convention, one token per slot, `-`
  for melisma"), or give lyrics a checked subset: same slot grid, warnings on
  overrun. The examples already follow this convention; the parser just
  doesn't know it.
- **A `--strict` / lint mode** in the CLI and a "Lint" button in the web UI
  would let authors opt into all of the above without breaking existing
  scores. The parse API already computes most of what's needed (sections,
  bars, players); the check layer is additive.

The deeper point: TapScript's appeal is that the text *is* the score — you
can see the groove in the columns. Right now that spatiality is a convention
the compiler ignores. Validation (recs 1–2, alignment checks) closes most of
the gap at near-zero format cost; per-section metadata and tuplets (recs 3–5)
extend the grid to the music people will actually try to write in it.

---

*Test artifacts: `examples/edge-cases/edge-1..5-*.tap`, bug details in
`examples/edge-cases/BUGS.md`. All compiles run against `localhost:5557`,
2026-08-13.*
