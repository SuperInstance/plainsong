# TapScript: Getting Started

TapScript is a plain-text music notation format that looks like a lead sheet
when printed and compiles to MIDI and WAV when rendered. It's part of
TapScript Studio, a small suite of independent local web apps in this repo
(see [docs/02-architecture.md](02-architecture.md) for how they fit
together).

This guide documents the notation and CLI implemented in
`scripts/tapscript_v2.py` — the engine that produces the format shown in
the project [README](../README.md) and used by every example bundled with
it (`EXAMPLES` in that file: `harbor_dawn`, `the_room_is_safe`,
`creatures_of_interval`, `neon_shadows`, `deck_work`).

> **Note:** This repo also contains `scripts/tapscript.py`, an older engine
> with a *different*, Roman-numeral/scale-degree notation. It is not what's
> described below. The two are unrelated parsers that happen to share a
> default port. See [docs/02-architecture.md](02-architecture.md) for the
> full comparison.

---

## 1. Running It

```bash
# Start the web server (default port 5557)
python3 scripts/tapscript_v2.py

# Compile a file to WAV and MIDI on the command line
python3 scripts/tapscript_v2.py --cli mysong.tap --midi out.mid --wav out.wav

# Render one of the five built-in examples directly to WAV
python3 scripts/tapscript_v2.py --example harbor_dawn --wav harbor.wav

# Run the web server on a different port
python3 scripts/tapscript_v2.py --port 8080
```

These are the only CLI flags that exist (`scripts/tapscript_v2.py`
`cli_main()`):

| Flag | Meaning |
|------|---------|
| `--cli FILE` | Parse and compile a `.tap`-style text file instead of starting the server |
| `--midi PATH` | Write a MIDI file to this path |
| `--wav PATH` | Write a WAV file to this path |
| `--example NAME` | Load one of the five built-in examples instead of a file |
| `--port N` | Web server port (default `5557`) |

With `--cli` and neither `--midi` nor `--wav` given, it prints a short
summary (title, key, tempo, section count) and still renders a WAV to the
default output directory. With `--example` and neither `--midi` nor `--wav`,
it renders a WAV. There is no `--help`-documented flag for choosing MIDI
*and* WAV output beyond passing both `--midi` and `--wav` at once.

Output files are written under `~/.openclaw/workspace/output/audio` unless
you pass an explicit path.

---

## 2. Anatomy of a TapScript File

Here's the real shape, taken directly from the `neon_shadows` example baked
into `scripts/tapscript_v2.py`:

```tapscript
**TRACK: Neon Shadows**
[MetaData]
key: Am | tempo: 75 | swing: 10% | subdivision: 16th

[V1] (Verse - 4 Bars)
Chords:  | Am    .    | F     G    |
Melody: | E4    . . . | A4    . G4 E4 |
Lyrics: | I     . . . | write . in code |
@wesley | e2-a2-c3 . . | f2-a2-c3 g2-b2-d3 | vel: 60

[C] (Chorus - Louder)
Chords:  | Am    F     C     G    | Am    F     C     G    |
Melody: | A4    C5    A4    G4   | A4    C5    D5    E5   |
Lyrics: | This  is    the   new  | syn   -     tax   for  |
@flash  | a2    f2    c2    g2   | a2    f2    c2    g2   | vel: 80
@hermes | a1    .     a1    .    | f1    .     g1    .    | vel: 75
```

### 2.1 Title (optional)

`**TRACK: Title Here**` is parsed by a regex looking for `**TRACK: ...**`
on a line by itself before `[MetaData]`. If omitted, the title is just an
empty string — nothing breaks.

### 2.2 `[MetaData]` block

A single pipe-delimited line of `key: value` pairs:

```
key: Am | tempo: 75 | swing: 10% | subdivision: 16th
```

| Field | Real parsing behavior |
|-------|------------------------|
| `key:` | Matched with `^([A-G][#b]?)(m?)$` — e.g. `Am`, `C`, `F#`, `Bbm`. Flats are normalized to their sharp equivalent internally (`Bb` → `A#`). Anything that doesn't match this pattern silently falls back to `C major`. |
| `tempo:` | Integer BPM. Default `120` if missing. |
| `swing:` | Integer percent (the `%` is optional and stripped). Default `0`. |
| `subdivision:` | Integer; the `th`/`st` suffix is stripped (`16th` → `16`). Only two things matter downstream: `<= 8` gives 2 slots per beat, anything else (including the default of `16`) gives 4 slots per beat. There's no support for triplets or other subdivisions. |

There is **no time signature field**. See §4.

### 2.3 `[Section]` headers

```
[V1] (Verse - 4 Bars)
```

The bracketed part (`V1`) is the section's identifier — must be a single
word (`\w+`). The parenthesized part is a free-text description that's
parsed but not used for anything musically; it's purely a label for humans
reading the file. Sections play in the order they appear in the file, with
no support for jumping around (no repeats, no D.C. al Fine, nothing like
that).

### 2.4 The four line types

Every line inside a section is one of:

- **`Chords:`** — chord symbols per bar, e.g. `Am`, `F`, `C`, `G`, `Cmaj7`,
  `Dm7`, `Gsus4`. Parsed by matching `^([A-G])([#b]?)(.*)$` against a table
  of ~16 chord shapes (`maj`, `m`, `7`, `m7`, `maj7`, `dim`, `dim7`, `aug`,
  `sus2`, `sus4`, `add9`, `6`, `m6`, `9`, `m9`). Anything with an
  unrecognized quality suffix falls back to a plain major triad.
- **`Melody:`** — absolute pitch tokens for a default, un-assigned melody
  voice, rendered on its own separate MIDI/WAV track named `"melody"`.
- **`Lyrics:`** — text syllables per slot. **These are parsed into the
  composition and kept nowhere near the audio renderer — see §4.**
- **`@name`** — a named performer/track, e.g. `@wesley`, `@flash`,
  `@hermes`. Everything after the name up to the first `|` is ignored;
  after that, `|`-delimited segments are either more bars of notes or a
  `vel: N` field setting that track's base MIDI velocity (default `70`).

All four are pipe-delimited: everything before the first `:` is the label,
everything after is split on `|` into one token-list per bar, and each bar
is further split on whitespace into individual tokens.

### 2.5 Note tokens (absolute pitch notation)

Pitches are scientific pitch notation, matched with
`^([A-Ga-g])([#b]?)(\d+)$`:

- `C4` = MIDI 60 (middle C). Case doesn't matter for the letter — `c4` and
  `C4` are identical.
- `#`/`b` before the octave number applies a sharp/flat: `C#4`, `Eb3`.
- A run of hyphen-joined notes is a **chord voicing** for that slot, e.g.
  `e2-a2-c3` sounds three notes together.
- `.` — **sustain**: extend the previous note/chord in that track through
  this slot.
- `-` — **rest**: silence in `Melody:` and `@player` lines. (Its behavior
  in `Chords:` lines is different — see §4.)
- Anything that isn't `.`, `-`, or a valid pitch pattern is treated as a
  rest.

Each token occupies one subdivision slot (2 or 4 per beat, per
`subdivision:` above); there's no per-token duration override.

---

## 3. Transposing

`POST /api/transpose` (or the `keySelect` dropdown in the web UI) rewrites
every absolute pitch token by the semitone distance between the old and new
key, using simple key-letter arithmetic — it does **not** reason about
scale degrees or key signatures. See §4 for what it does and doesn't touch.

---

## 4. Real Quirks (Not Bugs You'll Find Documented Elsewhere)

These come directly from reading `scripts/tapscript_v2.py`; each one is
easy to trip over if you assume the notation behaves the way it looks like
it should.

**Lyrics never render to audio.** `Lyrics:` lines are fully parsed and
stored on each bar (`bar["lyrics"]`), and the web UI can display them, but
`compile_to_midi()` never reads `bar["lyrics"]` for anything. There is no
lyric-to-audio path at all — lyrics are structurally decorative.

**`Chords:` lines cannot hold a true rest.** In a `Chords:` line, a `-`
token is parsed as a `"rest"` event, but the chord renderer
(`_render_chord_bar`) only ever *starts* a note on a `"chord"` event; every
`"sustain"` and `"rest"` event it encounters afterward just extends the
*previous* chord's held duration by one more slot. In other words, once a
chord is sounding, writing `-` after it does exactly what `.` does — it
holds the chord, it does not silence it. The only way to get real silence
in a `Chords:` line is to have no chord token at all before that point in
the bar (i.e., a leading `-`/`.` with nothing preceding it).

**Transpose skips `Chords:` and `Lyrics:` lines entirely.**
`transpose_text()` explicitly passes those two line types through
untouched:
```python
if stripped.startswith('Chords:') or stripped.startswith('Lyrics:'):
    result_lines.append(line)
    continue
```
Only `Melody:` and `@player` lines get their absolute pitch tokens shifted.
This means transposing a piece changes the key label and every melody/player
note, but leaves the chord symbols exactly as written — `Am` stays `Am`
even if you transpose everything else up a fourth. You have to re-voice
`Chords:` lines by hand after transposing.

**Everything is hardcoded to 4/4.** `compile_to_midi()` sets
`beats_per_bar = 4` as a literal constant; there is no time-signature field
in `[MetaData]` and no way to write a bar of 3/4 or 6/8. `subdivision:`
only changes how many note slots fit inside that fixed 4-beat bar (2 or 4
per beat), it does not change the meter itself.

**No soundfont, despite what you might expect.** WAV rendering
(`midi_to_wav`) does not load a `.sf2` file or call out to a synthesizer —
it generates raw waveforms in NumPy per instrument family (piano, bass,
strings, flute, guitar, drums) with hand-written ADSR envelopes, then mixes
and normalizes. What you hear is a lightweight built-in synth, not sampled
instruments.

**Default AI composition, if configured, is DeepSeek, not Claude.** The
`POST /api/compose` endpoint (and the "✨ Compose" button in the web UI)
only appears if a `DEEPSEEK_API_KEY` is found in `~/.bashrc` or the
environment; it calls `api.deepseek.com` directly. There's no fallback
composer.

---

## 5. Try It

```bash
python3 scripts/tapscript_v2.py --example deck_work --wav deck.wav
```

Then open the file in any audio player, or start the web server and load
"Deck Work" from the example dropdown to see the notation and audio side by
side.
