# TapScript Studio: Architecture

This document covers how a `.tap`-style text file becomes sound
(`scripts/tapscript.py` and `scripts/tapscript_v2.py`), the notation
grammar both engines implement, and how the three web apps in this repo —
Image Gallery (5555), MIDI Studio (5556), and TapScript Studio (5557) —
relate to each other. The short version of that last point: **they don't**,
beyond writing files into overlapping folders on disk. There is no shared
library, no message bus, no service registry. Each is a self-contained
`python3 scripts/whatever.py` process you start by hand.

---

## 1. The Three Processes

| Process | Port | Framework | Entry point | Writes output to |
|---|---|---|---|---|
| Image Gallery | 5555 | `http.server.HTTPServer` (stdlib) | `scripts/gallery_v4.py` | `~/.openclaw/workspace/output/images/gallery` |
| MIDI Studio | 5556 | `http.server.HTTPServer` (stdlib) | `scripts/midi_studio.py` | `~/.openclaw/workspace/output/audio` |
| TapScript (v1) | 5557 | Flask | `scripts/tapscript.py` | `~/.openclaw/workspace/output/audio` |
| TapScript (v2) | 5557 | `http.server.HTTPServer` (stdlib) | `scripts/tapscript_v2.py` | `~/.openclaw/workspace/output/audio` |

Each file `import`s only the stdlib, `numpy`, `scipy.io.wavfile`, and
`pretty_midi` (plus Flask for `tapscript.py`) — none of these four scripts
imports another one. There's no shared `lib/` or package; anything that
looks similar between them (the GM instrument program table, the
neon-on-black CSS theme, the ADSR envelope shape) is duplicated by hand,
not factored out. If you fix a bug in `midi_studio.py`'s velocity
humanization, it does not fix the equivalent code in `tapscript.py` — you'd
have to find and fix it again.

**The only thing that connects them is the filesystem.** MIDI Studio,
TapScript v1, and TapScript v2 all default to writing into the exact same
directory, `~/.openclaw/workspace/output/audio`, and rely on distinct
filename prefixes to avoid colliding:

- MIDI Studio: `composition_<uuid8>.mid` / `..._<uuid8>.wav`
- TapScript v1: `tapscript_<md5-8>.mid` / `.wav` (hash of the raw source text)
- TapScript v2: `tapscript_v2_<md5-8>.mid` / `.wav`

Nothing enforces this — it's convention, not a contract. If two of these
scripts ever changed their prefix to match, files would silently overwrite
each other. The Image Gallery is the only one of the three that lives in
its own subtree (`output/images/gallery`), because images and audio don't
compete for names anyway.

**Practical consequence:** you can run all three simultaneously (they're
independent OS processes on independent ports) *except* for TapScript v1
and v2, which both hardcode `PORT = 5557` — see §4. Starting one after the
other is already running on 5557 will fail with an address-in-use error;
this repo doesn't have supervisor logic to detect or route around that.

---

## 2. The Compiler Pipeline

Both `tapscript.py` and `tapscript_v2.py` implement the same four-stage
shape, even though the notation and internal representation they use are
different (§4). There is no formal lexer/tokenizer class and no
grammar file (no BNF, no PEG, no parser generator) in either engine — both
are hand-written, regex-and-`str.split()` recursive-descent-ish parsers
operating directly on `text.split('\n')`.

```
   raw text
      │
      ▼
 ┌─────────────┐   line-by-line regex matches on
 │   PARSER    │   headers / [Section] / Chords:|Melody:|@name lines
 └─────────────┘
      │  builds
      ▼
 ┌─────────────┐   v1: dataclasses (TapScriptComposition → Section → Bar → …)
 │     AST     │   v2: plain nested dicts (comp → sections → bars → …)
 └─────────────┘
      │  compile_to_midi()
      ▼
 ┌─────────────┐   pretty_midi.PrettyMIDI + Instrument + Note objects,
 │    MIDI     │   one Instrument track per role/player, swing + humanized
 └─────────────┘   velocity applied here
      │  midi_to_wav()
      ▼
 ┌─────────────┐   pretty_midi.PrettyMIDI(path) is *read back*, then every
 │     WAV     │   Note becomes a NumPy-synthesized waveform (no soundfont),
 └─────────────┘   mixed, normalized, and written with wave/scipy.io.wavfile
```

The MIDI step and the WAV step are genuinely separate: `midi_to_wav()`
takes a path on disk and reopens it with `pretty_midi`, it doesn't reuse
the in-memory `PrettyMIDI` object from `compile_to_midi()`. That's why
`compile_to_midi()` always does `pm.write(output_path)` before returning —
the WAV stage depends on that file actually existing.

### 2.1 Parsing

Both parsers are single-pass, line-oriented, and stateful: they walk
`lines = text.split('\n')` with an index `i`, mutating a "current section"
variable as they go. There's no backtracking and no lookahead beyond
`re.match` on the current line. A line is routed by prefix-matching:

- v1 (`tapscript.py`): a `[...]` line opens a section; an `@name: ...`
  line (colon after the name) registers an instrument; anything else with
  a `|` in it, or that a heuristic (`is_chord_line`/`is_melody_line`,
  scoring what fraction of tokens look like Roman numerals vs. digits)
  identifies as musical, gets split on `|` into bars.
- v2 (`tapscript_v2.py`): a `[...]` line opens a section; lines are
  dispatched by explicit prefix — `Chords:`, `Melody:`, `Lyrics:`, or
  `@name` — no heuristic guessing needed because the format is
  self-labeling.

This difference (heuristic classification vs. explicit line labels) is the
single biggest usability gap between the two notations: v1's parser can be
fooled by any melody line whose tokens don't cross the 40%-look-like-digits
threshold in `is_melody_line`, silently dropping notes with no error.
v2 can't have that class of bug because every line says what it is.

### 2.2 AST

v1 builds real Python objects — `@dataclass` types
(`KeySignature`, `Header`, `ChordSymbol`, `NoteEvent`, `Bar`, `Section`,
`InstrumentAssignment`, `TapScriptComposition`). Chord and note meaning is
deferred: a `ChordSymbol` stores a scale *degree* (1–7) and quality flags,
not a pitch — it only resolves to actual notes later, against whatever
`KeySignature` is active, via `ChordSymbol.resolve()`. This is what makes
v1 notation relative: the same `IV` means a different absolute chord in
every key, by construction.

v2 builds a plain nested `dict` (`comp["sections"][i]["bars"][j]["chords"]`
etc.) and every note is parsed straight to an absolute MIDI number at parse
time (`parse_absolute_note`). There's no scale-degree indirection — `Am`
means MIDI pitch-class A-minor everywhere, in every key, because the
notation never expressed a relationship to the key in the first place. The
`key:` field in `[MetaData]` is almost cosmetic for v2: it's read, stored,
and shown in the parsed-info bar, but nothing during MIDI compilation
consults it to transform a note or chord.

### 2.3 MIDI Compilation

Both engines build one `pretty_midi.PrettyMIDI` object, iterate bars in
section order accumulating a running `current_time` (bar duration derived
from tempo and a beats-per-bar that's hardcoded to 4 in both — see §5 in
[docs/01](01-getting-started.md) and the equivalent in v1), and append
`pretty_midi.Note` objects to per-role `Instrument` tracks. Both apply:

- **Swing** — a fractional delay added to notes that land on the "off"
  part of a beat, proportional to the `swing` percentage.
- **Humanized velocity** — a small random jitter (`±8` in v1, `±5` in v2)
  added to each note's velocity, drawn from a *seeded* RNG (`seed=42` in
  both), so re-rendering the same input twice always produces the same
  "human" variation, not fresh randomness each time.

v1 additionally infers what each track plays from free-text `role`
matching (`"chord" in role_lower`, `"walking" in role_lower`, etc.) with a
fallback heuristic if no keyword matches. v2 has no such inference: a
`@name` track plays exactly the tokens on its own line, full stop; the
`Melody:` and `Chords:` lines separately become their own dedicated
`"melody"` / `"chords"` tracks if present anywhere in the piece.

### 2.4 WAV Synthesis

Neither engine touches a `.sf2` soundfont or an external synth — both
`midi_to_wav()` implementations generate raw waveforms in NumPy:

- v1: waveform choice (`sine`/`triangle`/`sawtooth`) is guessed from the
  *instrument track name string* (`"bass" in n` → sine, etc.), one
  ADSR shape for everything, plus a simple **delay-line reverb** pass
  (`audio + 0.3 * delayed_copy`) applied to the whole mix at the end.
- v2: each instrument family gets its own hand-written synth function
  (`synth_piano`, `synth_bass`, `synth_strings`, `synth_flute`,
  `synth_guitar`, plus a noise-based `synth_drum`), each with distinct
  harmonic content and its own ADSR curve. There is **no reverb** in v2 —
  the mix is just summed, peak-normalized to `0.85`, and written directly.

Both convert to 16-bit PCM mono at 44.1kHz via `wave`/`scipy.io.wavfile`.

---

## 3. Notation Spec Summary

This is a compact reference; [docs/01-getting-started.md](01-getting-started.md)
teaches v2 (the notation actually shown in the README and used by every
bundled example) in full, with worked examples and quirks. The table below
exists so you can tell at a glance which engine a piece of TapScript text
is written for.

| | **v1 — `tapscript.py`** | **v2 — `tapscript_v2.py`** |
|---|---|---|
| Header | Loose lines: `key: A minor`, `tempo: 75`, `swing: 10`, `time: 4/4` (`time:` is parsed but bars are still built at whatever `time_sig[0]` says — no hardcode there, unlike v2) | `**TRACK: Title**` then `[MetaData]` with one pipe-delimited line: `key: Am \| tempo: 75 \| swing: 10% \| subdivision: 16th` |
| Section header | `[V1]` | `[V1] (Verse - 4 Bars)` — parenthesized description is decorative |
| Chord line | Unlabeled — a line of mostly Roman numerals (`i`, `IV`, `bVII°`, `V7`) is *detected* as a chord line by a heuristic | Explicitly labeled `Chords:` — letter names (`Am`, `F`, `Cmaj7`) |
| Melody line | Unlabeled — a line of mostly digits (`1`, `5^`, `b3_`) is *detected* as a melody line; digits are **scale degrees**, `^`/`_` shift octave, `,`/`:` separators pack multiple notes into one slot | Explicitly labeled `Melody:` — absolute pitches (`E4`, `A4`) |
| Lyrics | Not a distinct concept — a lyric-like line just fails to parse as chords or notes and silently contributes nothing | Explicitly labeled `Lyrics:` — parsed and stored, **never used in audio** (see docs/01 §4) |
| Instrument/player line | `@name: instrument \| role \| vel: N` (colon after name; role is free text used for heuristic track-behavior selection) | `@name \| bar tokens \| vel: N` (no colon; tokens are literal notes, not inferred from a role) |
| Pitch representation | Relative — scale degree + accidental + octave, resolved against the active key at compile time | Absolute — scientific pitch notation (`C4`, `e2`), resolved once at parse time |
| Chord representation | Relative — Roman numeral degree + quality, resolved against the active key's diatonic triads | Absolute — letter + quality (`Am`, `Cmaj7`), resolved directly, independent of `key:` |
| Transpose | Rewrites the `key:` line, re-parses the *entire* raw text unchanged otherwise — correct by construction, because notation is relative | Walks every line, regexes out every absolute pitch token and shifts it by a computed semitone offset, **except** `Chords:` and `Lyrics:` lines, which are passed through verbatim (see docs/01 §4) |
| Time signature | Configurable via `time: N/M` in the header, actually respected by `compile_to_midi` | Fixed 4/4, no field exists |
| Web transport | Flask (`/api/parse`, `/api/compile`, `/api/render`, `/api/transpose`, `/api/example[/<name>]`, `/audio/<file>`) | stdlib `http.server` (`/api/parse`, `/api/compile`, `/api/transpose`, `/api/compose`, `/api/status`, `/api/examples`, `/api/example/<name>`, `/api/download?path=&type=`) |
| AI composition | None | `/api/compose` calls the DeepSeek chat API if `DEEPSEEK_API_KEY` is set (env or `~/.bashrc`) |
| Built-in examples | `harbor_dawn`, `the_room_is_safe`, `open_mic` (3) | `harbor_dawn`, `the_room_is_safe`, `creatures_of_interval`, `neon_shadows`, `deck_work` (5) |

Note the name collision: both engines ship an example called
`harbor_dawn` and one called `the_room_is_safe`, but they are two
*independently written* pieces of text in two different notations, living
as Python string literals inside their respective script — not the same
file transformed, not shared data.

---

## 4. Why Two Engines, One Port

Nothing in the repo picks between `tapscript.py` and `tapscript_v2.py` at
runtime — you choose by which command you type. Both hardcode
`PORT = 5557`. The commit history (`git log --oneline`) shows `tapscript.py`
landed first as a Roman-numeral/relative-notation system, and
`tapscript_v2.py` ("TapScript v2: full parser, MIDI compiler, WAV renderer,
web app with 5 examples") landed later as an absolute-pitch rewrite. The
README's Quick Start still names `scripts/tapscript.py` for the port-5557
entry, but the notation sample directly underneath it, and every worked
example elsewhere in this repo's docs and knowledge base, is v2 syntax.
Treat `tapscript_v2.py` as the notation in active use; treat `tapscript.py`
as a still-functional but separate legacy engine you'd only reach for
deliberately, e.g. if you specifically want key-relative Roman-numeral
notation and easy modulation.

If you want both running at once for comparison, start one with `--port`
overridden:

```bash
python3 scripts/tapscript.py           # 5557 (Roman-numeral engine)
python3 scripts/tapscript_v2.py --port 5558   # absolute-pitch engine, moved aside
```

---

## 5. How the Three Web Apps Relate

Restated plainly, because it's easy to assume more coupling than exists:

- **Image Gallery (5555)** — Stable Diffusion 1.5 (local) + DeepInfra FLUX
  (cloud) image generation, img2img, album management. Talks to a local
  SD backend and the DeepInfra API. Has zero awareness that MIDI or
  TapScript exist.
- **MIDI Studio (5556)** — procedural multi-track MIDI generation from
  `(tempo, key, scale, chords, layers)` parameters, optionally chatting
  with the DeepSeek API for composition suggestions. Has zero awareness of
  TapScript notation — it never parses a `.tap` file, it builds MIDI
  directly from structured JSON.
- **TapScript Studio (5557)** — the notation compiler documented above.
  Has zero awareness of images or of MIDI Studio's generation parameters.

They are three separate `git`-tracked scripts that a human (or an agent)
starts independently, each serving its own bespoke HTML+JS single-page
app inlined as a Python string (MIDI Studio loads its HTML from an
external `midi_studio.html` file instead; the other two inline it). The
"suite" framing in the README is a UX/workflow framing — *you*, the human,
move a MIDI file MIDI Studio generated into a TapScript `@player` line by
hand, or drop a TapScript WAV into an Image Gallery prompt for mood
reference — not something the software does for you. If you kill one
process, the other two are entirely unaffected, short of a filename
collision in the shared `output/audio` directory (§1).
