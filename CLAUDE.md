# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

TapScript is a plain-text music notation that reads like a lead sheet and compiles to MIDI/WAV. The repo holds two independent compiler engines, three unrelated local web apps, a large corpus of `.tap` notation (fake book, songs, training material), and a VS Code extension.

## Setup and commands

There is no `requirements.txt`, no packaging, no lockfile. Install by hand:

```bash
pip install numpy scipy pretty_midi flask pytest   # CI installs only numpy flask pytest
```

`pretty_midi` is optional — tests skip MIDI compilation without it. `scripts/tapscript_v2.py` imports `scipy` and `pretty_midi` at module load and will not start without them.

```bash
# Tests (CI runs this on Python 3.10/3.11/3.12)
python3 -m pytest tests/ -v --tb=short

# One test class / one test
python3 -m pytest tests/test_tapscript.py::TestParseChordToken -v
python3 -m pytest tests/test_tapscript.py::TestTransposition::test_transpose_changes_key -v

# src/test_swmidi8.py is NOT collected by CI (it lives in src/, not tests/)
python3 -m pytest src/test_swmidi8.py -v

# Compile notation from the CLI
python3 scripts/tapscript_v2.py --cli docs/fakebook/03-hallelujah.tap --midi out.mid --wav out.wav
python3 scripts/tapscript.py --example harbor_dawn --wav harbor.wav

# Web apps (each is a standalone process; start by hand)
python3 scripts/gallery_v4.py      # 5555  (gallery_v5.py is the newer three-panel version)
python3 scripts/midi_studio.py     # 5556
python3 scripts/tapscript_v2.py    # 5557  — pass --port to move it aside
python3 scripts/tapscript.py       # 5557  — same hardcoded port, cannot run alongside v2
```

`tests/` adds `scripts/` to `sys.path` and imports `tapscript` directly — module-level symbols in `scripts/tapscript.py` (including the `EXAMPLES` string constants) are part of the test surface.

## Architecture

`docs/02-architecture.md` is accurate and detailed; read it before any nontrivial change. The essentials:

**Nothing is shared.** Every script under `scripts/` is self-contained and imports only stdlib + numpy/scipy/pretty_midi (+ Flask for `tapscript.py`). The GM program table, the CSS theme, the ADSR envelope, and the velocity humanization exist in duplicate. Fixing a bug in one engine does not fix it in the other. The three web apps are coupled only by writing into `~/.openclaw/workspace/output/audio`, kept apart by filename prefix convention (`composition_*`, `tapscript_*`, `tapscript_v2_*`) — nothing enforces it.

**Compiler pipeline** (both engines, four stages): hand-written line-oriented regex parser → AST → `compile_to_midi()` → `midi_to_wav()`. The WAV stage reopens the `.mid` from disk with `pretty_midi` rather than reusing the in-memory object, which is why `compile_to_midi()` always writes the file before returning. No soundfont is involved — WAV is synthesized in NumPy (v1: waveform guessed from track name + delay-line reverb; v2: per-instrument `synth_piano`/`synth_bass`/… functions, no reverb). Velocity humanization uses a seeded RNG (`seed=42`), so renders are deterministic.

**Two engines, two notations:**

| | `scripts/tapscript.py` (v1) | `scripts/tapscript_v2.py` (v2) |
|---|---|---|
| Pitch | Relative — Roman numerals + scale degrees, resolved against the key at compile time | Absolute — scientific pitch (`C4`, `e2`), resolved at parse time |
| Line typing | Heuristic (`is_chord_line`/`is_melody_line` score token shapes) — can silently drop notes | Explicit `Chords:` / `Melody:` / `Lyrics:` / `@name` prefixes |
| AST | `@dataclass` types (`TapScriptComposition → Section → Bar → …`) | Plain nested dicts |
| Transpose | Rewrite `key:`, re-parse — correct by construction | Regex-shift every pitch token; `Chords:` and `Lyrics:` pass through verbatim |
| Time sig | `time: N/M` honored | Fixed 4/4 |
| Web | Flask | stdlib `http.server`, plus `/api/compose` via DeepSeek |

v2 is the notation in active use — the README sample, every `.tap` file in `docs/fakebook/`, `docs/songs/`, and `examples/` uses it. v1 is legacy but still live, and the newest feature (duration-by-spacing, `C4~~~` where each sustain char adds an eighth) landed **only in v1**; see `docs/melody-spacing-design-decisions.md` and `proposals/melody-duration-spacing.md`. Both engines ship examples named `harbor_dawn` and `the_room_is_safe` that are unrelated pieces of text.

**`src/`** is separate from the compilers — Python ports of other fleet projects (`pulse_grid.py`: 96 PPQ timing grid; `swmidi8.py`: fixed 8-byte wire-format codec from tensor-midi; `groove_tracker.py`: port of `groove.rs`). Nothing in `scripts/` imports them yet.

## Content directories

`docs/fakebook/` (~3,800 `.tap` transcriptions across a dozen languages), `docs/songs/`, `docs/prose/`, `docs/traditions/`, `docs/training/`, `academy/` (five graded levels + assessments) are notation and prose corpora, mostly generated. `scripts/fakebook_generator.py` bulk-generates them via DeepSeek and enforces a hard copyright policy: full melody+lyrics only for public-domain material, chord-chart skeletons for copyrighted songs, with `Lyrics:`/`Melody:` lines stripped as a safety net. Do not loosen that.

## Known rough edges

- `examples/edge-cases/BUGS.md` documents reproduced v2 parser bugs (non-standard token counts silently misplaced, overfilled bars destroying notes). They are open; check it before "fixing" surprising timing behavior.
- Hardcoded absolute paths: output goes to `~/.openclaw/workspace/output/`, and `scripts/fakebook_generator.py` hardcodes `/home/eileen/projects/tapscript-studio`.
- API keys (`DEEPSEEK_API_KEY`) are read by grepping `~/.bashrc` before falling back to the environment.
- `vscode-extension/` declares a `test` script pointing at `test/runTest.js`, which does not exist. Its one real feature is the `tapscript.checkPipeBalance` linter in `src/extension.js`.
