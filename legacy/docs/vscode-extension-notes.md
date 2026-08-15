# VS Code Extension — Design Notes & Findings

## Overview

Built a VS Code extension for TapScript at `vscode-extension/`. The extension provides syntax highlighting (TextMate grammar), snippets, and basic linting (pipe delimiter balance checking) for `.tap` files.

## Files Created

| File | Purpose |
|------|---------|
| `package.json` | Extension manifest — language contribution, grammar, snippets, commands |
| `language-configuration.json` | Bracket matching, comment toggles, auto-closing pairs, folding |
| `syntaxes/tapscript.tmLanguage.json` | TextMate grammar — the core syntax highlighting definition |
| `snippets/tapscript.json` | 15 snippets covering both v1 and v2 notation patterns |
| `src/extension.js` | Extension entry point — pipe balance diagnostics + command |
| `README.md` | Install instructions and feature documentation |
| `.vscodeignore` | Packaging exclusions |

## Dual Notation Support

The grammar handles **both** TapScript notation variants:

### v2 (Labeled / Absolute Pitch)
- `**TRACK: Title**` headers
- `[MetaData]` blocks with `key:`, `tempo:`, `swing:`, `subdivision:`
- Explicit track labels: `Chords:`, `Melody:`, `Lyrics:`
- `@player` instrument lines with `vel: N`
- Scientific pitch notation: `C4`, `Bb2`, `F#5`
- Letter-name chord symbols: `Am`, `Cmaj7`, `Gsus4`

### v1 (Unlabeled / Relative Pitch)
- `Key:` / `Tempo:` / `Meter:` headers (loose key-value lines)
- Roman numeral chords: `i`, `IV`, `V7`, `bIII`, `vii°`
- Scale-degree melodies: `1`, `5`, `b3`, `#4` with `^`/`_` octave shifts
- No track labels — lines are auto-detected by the compiler

### Print Refinement Extensions
- `Dyn:` dynamics line (`pp`, `p`, `mp`, `mf`, `f`, `ff`)
- `Art:` articulation line (staccato `.`, accent `>`, tenuto `-`, slur `(...)`)
- `Rest:` multi-bar rest line with `R4` notation
- `[KeyChange]` blocks for mid-song modulation
- Repeat markers: `||:`, `:||`, `[1.`, `[2.`
- Time signature inline markers: `4/4`, `7/8`
- Navigation markers: `D.S. al Coda`, `Fine`, `Coda`

## Grammar Design Decisions

### 1. Pitch token ordering matters
Scientific pitch notation (`C4`, `Bb2`) is matched as a **3-capture group** (letter + accidental + octave) to allow theme authors to color each component independently. The grammar places the SPN match **before** chord symbols and scale degrees to prevent mis-highlighting.

### 2. Roman numerals vs. scale degrees
v1 notation mixes both on separate unlabeled lines. The grammar distinguishes:
- **Roman numerals**: `i`, `IV`, `vii°`, `bIII` — matched via `I{1,3}|IV|VI{0,3}` patterns (case-sensitive for major/minor)
- **Scale degrees**: `1`, `5`, `b3`, `#4` — matched as `[#b]?\d` with negative lookbehind to avoid matching inside note names

### 3. Sustain dot vs. staccato dot
The humble `.` is ambiguous in TapScript:
- In a `Chords:`/`Melody:` line: it means "sustain/rest" (hold previous note)
- In an `Art:` line: it means "staccato"
- In a `c2-e2-g2` chord cluster: it's a placeholder (`c2-.-g2` = skip middle note)

The grammar uses **context-sensitive** matching: the sustain-dot pattern uses `(?<=\s)\.(?=\s|\||$)` to only match standalone dots between other tokens. Staccato dots in articulation lines are handled by the articulation-line rule.

### 4. Hyphenated chord clusters
v2 notation supports `c2-e2-g2` (C major triad as hyphenated tokens), `c2-.-g2` (skip middle note), and `c3--e3` (double-hyphen variant). The grammar matches these as a single `entity.name.chord-cluster` token to prevent the hyphen from being interpreted as a tie.

## Open Questions Revealed by the Grammar

### Q1: Should `Key:` and `key:` be case-insensitive?
v1 uses `Key: Am` (capitalized), v2 uses `key: Am` (lowercase). The metadata-directives pattern uses `(?i)` for case-insensitivity, but this means `Key:` and `key:` highlight the same. **Decision: case-insensitive is correct** — both engines parse them identically.

### Q2: How should `||:` repeat markers interact with bar counting?
The linting feature counts bar segments by splitting on `|`. A line like `||: C G | Am F :||` has the repeat markers contributing extra pipe characters, which inflates the bar count and triggers false-positive bar-count warnings. **Current approach:** the linter flags mismatches as `Information` severity (not warnings/errors) to avoid being annoying. A future version could strip repeat markers before counting.

### Q3: The `.` sustain token vs. decimal numbers
The grammar pattern for sustain dots `(?<=\s)\.(?=\s|\||$)` correctly avoids matching the dot in `4/4.` or in floating-point tempo values, but it **also won't match** a dot that's the first or last character on a line. This is acceptable because well-formed TapScript always pads dots with spaces.

### Q4: Chord quality regex completeness
The chord quality pattern `maj\d?|min\d?|m\d?|dim\d?|aug\d?|sus[24]?|add\d+|dom7|maj7|min7|\d+m?\+?` handles all qualities found in the example files:
- Simple: `Am`, `C`, `F`, `G`
- Extended: `Cmaj7`, `Am7`, `F7`, `Gsus4`, `Ddim`, `Aaug`, `Cadd9`, `Am6`, `G9`, `Gbmaj7`
- Edge: `Esus4`, `Cadd9`

**Not yet matched:** slash chords with bass notes (`C/E`, `Am/G`), which appear in the architecture spec but not in any example file. These would need a separate pattern.

### Q5: v1 `@name:` (colon) vs v2 `@name` (no colon)
v1 uses `@wesley: piano | chords | vel: 60` (colon after name, then role).
v2 uses `@wesley | c2-e2-g2 . . | vel: 60` (no colon, tokens are literal notes).

The grammar matches `^@(\w+)` for the player name in both cases, but doesn't distinguish the colon variant. A more sophisticated grammar could use `^@(\w+):\s*(\w+)\s*\|` to highlight the v1 instrument/role separately.

### Q6: Multi-note chords in parentheses
The architecture spec shows `e2-a2-c3` (hyphenated) for simultaneous notes, but some notations use `e2,a2,c3` (comma-separated) or `(e2 a2 c3)` (parenthesized). The grammar only handles the hyphenated form, which is what the example files use.

## Validation Results

All files pass validation:
- ✅ `package.json` — valid JSON
- ✅ `language-configuration.json` — valid JSON
- ✅ `syntaxes/tapscript.tmLanguage.json` — valid JSON
- ✅ `snippets/tapscript.json` — valid JSON
- ✅ `src/extension.js` — valid JavaScript (node --check)

## Future Enhancements

1. **MIDI preview** — Webview-based audio player for `.tap` files
2. **Compiler integration** — Call the TapScript v2 compiler from VS Code tasks
3. **Auto-formatting** — Align columns across Chords/Melody/Lyrics lines
4. **Color theme** — Custom theme that highlights musical elements distinctly
5. **Outline view** — Document symbol provider for sections (`[V1]`, `[Chorus]`, etc.)
6. **Bracket completion** — Auto-insert matching `|` when typing in musical lines
7. **Hover tooltips** — Show note frequencies or chord intervals on hover
8. **Transposition command** — Shift all notes by N semitones via command palette
