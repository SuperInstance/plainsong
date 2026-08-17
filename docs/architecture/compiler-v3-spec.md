# Plainsong Compiler v3 — Architecture Specification

**Status:** Draft 1  
**Date:** 2026-08-13  
**Author:** Navigation (subagent)  
**Supersedes:** `plainsong_v2.py` (1675 lines, regex-based, no temporal grid)  
**Consumes:** SWMIDI-8 Wire Format, harmony-core, slackwater-tempo, vibe-protocol, emergence-engine, stigmergy

---

## 0. Design Philosophy

Plainsong v2 is a working compiler. It parses pipe-delimited monospace notation into nested dicts, then emits `pretty_midi` calls and numpy-synthesized WAV. Its fatal limitation — documented in `docs/structural-analysis.md` — is that **the grid is a lie**: token index drives timing, pipes don't bound bars, empty bars vanish, and subdivisions are binary-only (2 or 4 slots per beat). The notation *looks* like a piano roll but behaves like a token stream.

v3 makes the grid real.

The compiler pipeline has five stages, each with exact data structures. The intermediate representation is SWMIDI-8 — an 8-byte-per-event wire format already designed for the tensor-midi project. Every backend (MIDI file, WAV, live stream) consumes the same IR. The temporal model is the tensor-midi 12-pulse architecture: 12/8 internal representation, 96 PPQ grid, convergent ECN/DMN firing patterns.

The grammar is formal. The structural analysis recommendations — slot validation, empty-bar preservation, per-section metadata, meter declaration, tuplets — are in the production rules, not bolted on.

---

## 1. COMPILER PIPELINE

```
                    Stage 1            Stage 2             Stage 3              Stage 4            Stage 5
                    LEXER              PARSER              TEMPORAL             IR LOWERING        BACKENDS
                    text → tokens      tokens → AST        AST → PulseGrid      grid → SWMIDI-8    IR → output

                    LineToken          ASTNode             PulseEvent           SWMIDIEvent        MIDIFile
                    ├─ METADATA        ├─ Composition      ├─ tick: int         ├─ bytes[8]        WAVFile
                    ├─ SECTION         ├─ Section          ├─ pulse: int       (fixed format)     LiveStream
                    ├─ CHORD_LINE      ├─ Bar              ├─ type: NoteOn     ──────────────
                    ├─ MELODY_LINE     ├─ ChordNode        ├─ type: NoteOff      Friction bitfield
                    ├─ LYRIC_LINE      ├─ NoteNode         ├─ type: CC           (8 error types)
                    ├─ PLAYER_LINE     ├─ RestNode         ├─ type: Meta
                    ├─ REPEAT_OPEN     ├─ SustainNode      ├─ type: ProgramCh    Vibe dims as Meta
                    ├─ REPEAT_CLOSE    ├─ PlayerTrack      └─ action: enum
                    ├─ COMMENT         ├─ VibeAnnotation
                    └─ BLANK_BAR       └─ ResonanceAnnot
```

### Stage 1: LEXER — text → token stream

The lexer converts raw text into a flat stream of typed tokens. It is line-oriented (like v2) but with formal token types, eliminating the ambiguous prefix-matching that lets `tempo: 200` mid-score be silently ignored.

```typescript
interface LineToken {
  type:
    | 'METADATA'      // key: Am | tempo: 75 | swing: 10%
    | 'SECTION'       // [V1] (Verse - 4 Bars)
    | 'CHORD_LINE'    // Chords: | Am  .  | F  G  |
    | 'MELODY_LINE'   // Melody: | E4  .  | A4 .  |
    | 'LYRIC_LINE'    // Lyrics: | I   .  | write |
    | 'PLAYER_LINE'   // @wesley | a2 . | f2 . | vel: 60
    | 'REPEAT_OPEN'   // ||:
    | 'REPEAT_CLOSE'  // :||
    | 'VOLTA'         // [1.  or  [2.
    | 'KEY_CHANGE'    // **key: G**
    | 'COMMENT'       // % this is a comment
    | 'BLANK_BAR'     // _____
    | 'RESONANCE'     // [resonance: warm, high-tension]
    | 'VIBE_ANNOT'    // [vibe: energy: 0.8, tension: 0.3]
    | 'EMPTY'
  lineNumber: number;
  raw: string;         // original line text
  payload?: any;       // pre-parsed structure (see grammar)
}

interface LexerConfig {
  preserveComments: boolean;   // keep COMMENT tokens in stream
  strictMode: boolean;         // emit error tokens instead of silent skips
}
```

**Lexer rules:**
- Lines are classified by first non-whitespace character(s)
- `%` → COMMENT (like Pollen/Racket)
- `||:` and `:||` → REPEAT markers
- `[1.` / `[2.` → VOLTA brackets
- `_____` (5+ underscores) → BLANK_BAR (stigmergy deposit)
- `[resonance:` → RESONANCE annotation
- `[vibe:` → VIBE annotation  
- `[` + alphanumeric → SECTION header
- `Chords:` / `Melody:` / `Lyrics:` → typed line
- `@` + word → PLAYER_LINE
- `**key:` → KEY_CHANGE
- Everything else in metadata block → METADATA

**Output:** `LineToken[]` — a flat array preserving order, including EMPTY tokens for blank lines (the parser skips them but they maintain line numbers for error reporting).

### Stage 2: PARSER — tokens → typed AST

The parser consumes `LineToken[]` and builds a typed tree. It uses LALR(1) via `lark` (Python) or `tree-sitter` for incremental parsing. The AST captures hierarchical structure: Composition → Sections → Bars → Events.

```typescript
interface Composition {
  title: string;
  metadata: Metadata;
  sections: Section[];
  keyChanges: KeyChange[];
  sourceText: string;        // for round-tripping
  warnings: CompilerWarning[];
}

interface Metadata {
  key: string;               // 'Am', 'C', 'F#'
  keyQuality: 'major' | 'minor';
  tempo: number;             // BPM
  swing: number;             // 0–100 (percentage)
  subdivision: 8 | 16;       // 8th or 16th notes
  meter: TimeSignature;      // default 4/4
  groove: GrooveConfig;      // optional humanization
  energy: GameState;         // Adagio | Andante | Allegro | Presto
}

interface TimeSignature {
  numerator: number;         // 3, 4, 6, 12
  denominator: number;       // 4, 8
}

interface GrooveConfig {
  swingAmount: number;       // 0.0–1.0
  pushAmount: number;        // ahead of beat
  dragAmount: number;        // behind beat
  humanize: number;          // timing jitter (ms)
}

interface Section {
  name: string;              // 'V1', 'C', 'Bridge', 'Outro'
  description: string;       // 'Verse - Fog Lifting - 4 Bars'
  bars: Bar[];
  repeats?: RepeatMarker;
  localTempo?: number;       // per-section override (recommendation #3)
  localMeter?: TimeSignature;
  localSwing?: number;
  localEnergy?: GameState;
}

interface Bar {
  index: number;             // 0-based within section
  chordEvents?: ChordToken[];
  melodyEvents?: MelodyToken[];
  lyrics?: LyricToken[];
  playerTracks: Map<string, PlayerToken[]>;
  vibeAnnotations: VibeAnnotation[];
  resonanceAnnotations: ResonanceAnnotation[];
  isBlank: boolean;          // _____ → stigmergy deposit
  slotCount: number;         // validated against meter × subdivision
}

interface ChordToken {
  type: 'chord' | 'sustain' | 'rest';
  symbol?: string;           // 'Am', 'F', 'Cmaj7'
  root?: number;             // semitone 0–11
  intervals?: number[];      // [0,4,7] for major
  octave?: number;           // voicing octave (default 4, recommendation #6)
  slotIndex: number;         // position within bar
}

interface MelodyToken {
  type: 'note' | 'sustain' | 'rest' | 'tuplet';
  pitches: number[];         // MIDI numbers for notes
  slotIndex: number;
  slotSpan: number;          // how many slots this token occupies
  tupletRatio?: [number, number]; // [3, 2] for triplets
}

interface PlayerToken {
  type: 'note' | 'sustain' | 'rest';
  pitches: number[];
  slotIndex: number;
  velocity: number;
  player: string;
}

interface VibeAnnotation {
  dimensions: Partial<VibeVector>;  // any of 16 dims
  scope: 'section' | 'bar';
}

interface VibeVector {
  warmth: number;    tension: number;   mystery: number;
  energy: number;    order: number;     openness: number;
  intimacy: number;  novelty: number;   brightness: number;
  density: number;   rhythm: number;    resonance: number;
  gravity: number;   friction: number;  clarity: number;
  depth: number;
}

interface ResonanceAnnotation {
  tags: string[];           // ['warm', 'high-tension']
  scope: 'section' | 'bar';
}

interface RepeatMarker {
  voltaFirst: number;       // repeat count for [1.
  voltaSecond: number;      // repeat count for [2.
  totalRepeats: number;
}

interface CompilerWarning {
  line: number;
  code: string;             // 'SLOT_UNDERFILL', 'BAR_COUNT_MISMATCH'
  message: string;
  severity: 'info' | 'warn' | 'error';
}

type GameState = 'Adagio' | 'Andante' | 'Allegro' | 'Presto';
```

**Parser correctness guarantees (addressing structural-analysis findings):**
1. **Slot validation.** Every bar's token count is checked against `slotsPerBar = (beatsPerBar × subdivisionFactor)`. Underfill → warning. Overfill → warning + truncation policy.
2. **Empty bar preservation.** `| |` segments count as bars of implicit rests (not skipped).
3. **Bar-count agreement.** Within a section, `Chords:`, `Melody:`, and `@player` lines must have the same bar count. Mismatch → warning naming lines and counts.
4. **Per-section metadata.** Section headers carry optional overrides: `[C] (Chorus - tempo: 200 - swing: 20%)`.
5. **Meter declaration.** `meter: 3/4` in metadata. Default 4/4.

### Stage 3: TEMPORAL RESOLUTION — AST → PulseTick grid (96 PPQ)

This is where the grid becomes real. The temporal resolver walks the AST and assigns every note, rest, sustain, and chord an absolute tick position on the 96 PPQ grid. This stage integrates with slackwater-tempo's `BeatClock` for tempo maps, swing curves, and groove humanization.

```typescript
interface PulseGrid {
  ppq: 96;                         // constant
  pulsesPerBar: number;            // 12 (see §3: The 12-Pulse Model)
  ticksPerPulse: 8;               // 96 / 12 = 8
  ticksPerBar: number;            // depends on meter (see §3)
  totalTicks: number;              // song length
  tempoMap: TempoMapEntry[];       // BPM changes over time
  events: PulseEvent[];
}

interface TempoMapEntry {
  startTick: number;
  bpm: number;
  gameState?: GameState;
  transitionCurve?: TransitionCurve; // smooth ramp between tempos
}

interface PulseEvent {
  tick: number;                    // absolute position, 96 PPQ
  pulse: number;                   // which of the 12 pulses (0–11)
  bar: number;                     // absolute bar number (0-based)
  beatInBar: number;               // beat position
  type:
    | 'NoteOn'
    | 'NoteOff'
    | 'CC'
    | 'ProgramChange'
    | 'Meta'
    | 'PheromoneDeposit';          // for blank bars (stigmergy)
  pitch?: number;                  // MIDI note number
  velocity?: number;               // 0–127
  channel?: number;                // 0–15
  ccNumber?: number;
  ccValue?: number;
  program?: number;
  metaType?: number;
  metaValue?: string | number[];
  action?: ActionType;             // conversation | build | creative | system
  friction?: number;               // friction bitfield (0–255)
  vibe?: Partial<VibeVector>;      // embedded vibe dimensions
  player?: string;                 // which player/track
  pheromoneId?: string;            // for stigmergy deposits
}

type ActionType = 'conversation' | 'build' | 'creative' | 'system';
```

**Temporal resolution algorithm:**

1. **Compute bar tick counts** based on meter:
   - 4/4 → 96 ticks/bar (4 beats × 24 ticks/beat)
   - 3/4 → 72 ticks/bar
   - 6/8 → 72 ticks/bar (but 12 pulses/bar, 6 ticks/pulse — see §3)
   - 12/8 → 96 ticks/bar (native 12-pulse representation)

2. **Walk sections in order**, expanding repeats:
   - `||:` ... `:||` → iterate the section body `totalRepeats` times
   - Volta brackets select which bars play on which repeat pass

3. **Within each bar**, assign slot positions:
   ```
   slotTicks = ticksPerBar / slotCount
   for each token at slotIndex i:
     event.tick = barAbsoluteStart + i × slotTicks
   ```

4. **Apply swing**: off-beat slots (odd indices within a beat) shift later by `swingAmount × slotTicks × 0.5`

5. **Apply groove humanization**: each event tick gets a Gaussian jitter of `±humanize/2` ticks (clamped)

6. **Compute note durations**: a note's duration extends from its NoteOn to the next rest/explicit NoteOff/end-of-slot-group. Sustains (`.`) extend the active note. Rests (`-`) terminate active notes.

7. **Generate NoteOff events**: for every NoteOn, emit a corresponding NoteOff at `tick + duration`.

8. **Emit Meta events** from vibe/resonance annotations at the bar or section start tick.

9. **Emit PheromoneDeposit events** for blank bars (`_____`) at the bar's start tick — these are the stigmergy trail markers for multi-agent collaboration.

### Stage 4: IR LOWERING — grid → SWMIDI-8 event stream

The SWMIDI-8 wire format IS the intermediate representation. This stage converts `PulseEvent[]` into packed 8-byte events. The IR is binary — language-agnostic, transport-ready, and directly streamable.

```typescript
// SWMIDI-8 Event: exactly 8 bytes
// This is the IR. Every backend consumes this format.
interface SWMIDIEvent {
  // Byte layout (see tensor-midi/src/swmidi.js for canonical implementation)
  // 
  // Byte 0: [status:4][channel:4]
  // Byte 1: [data1:8]   (pitch / CC number / program)
  // Byte 2: [data2:8]   (velocity / CC value)
  // Byte 3: [tickHigh:8] (upper 8 bits of 24-bit tick)
  // Byte 4: [tickMid:8]
  // Byte 5: [tickLow:8]
  // Byte 6: [friction:4][action:4]
  // Byte 7: [metaType:4][flags:4]
  
  status: number;     // 0x9=NoteOn, 0x8=NoteOff, 0xB=CC, 0xC=ProgramCh, 0xFF=Meta
  channel: number;    // 0–15
  data1: number;      // pitch (0–127) | CC number | program number
  data2: number;      // velocity (0–127) | CC value
  tick: number;       // 0–16777215 (24-bit, 96 PPQ)
  friction: number;   // 0–15 (4-bit, see bitfield below)
  action: number;     // 0–15 (4-bit ActionType)
  metaType: number;   // 0–15 (Meta sub-type)
  flags: number;      // 0–15 (reserved)
}

// Friction Bitfield (4 bits in v3, expanded from 8 in full SWMIDI-8)
// The 4-bit compact version maps to the 8 most important error types:
// Bit 0: Timing drift (tempo instability)
// Bit 1: Dissonance (harsh intervals, unresolved tension)  
// Bit 2: Density overflow (too many voices)
// Bit 3: Energy mismatch (vibe vs. actual output)
// 
// Full 8-bit version (in Meta events for detailed analysis):
// Bit 4: Cadence disruption
// Bit 5: Flow break (Hurst exponent < 0.5)
// Bit 6: Predictability collapse (entropy spike)
// Bit 7: Phase desync (ECN/DMN convergence failure)
```

**Lowering rules:**

| Source (PulseEvent) | IR (SWMIDI-8) | How |
|---|---|---|
| NoteOn | status=0x9, data1=pitch, data2=velocity | Direct |
| NoteOff | status=0x8, data1=pitch, data2=0 | Direct |
| CC | status=0xB, data1=ccNumber, data2=ccValue | Direct |
| ProgramChange | status=0xC, data1=program, data2=0 | Direct |
| Meta (vibe dims) | status=0xFF, metaType=0x1, data bytes encode dimension values | See §2 |
| Meta (tempo) | status=0xFF, metaType=0x2 | Standard MIDI tempo meta |
| PheromoneDeposit | status=0xFF, metaType=0x3, encodes pheromone trail ID + strength | See §2.5 |

### Stage 5: BACKENDS — IR → output

All three backends consume `SWMIDIEvent[]` (plus a header with tempo map and track names). No backend touches the AST or PulseGrid. See §5 for full specs.

---

## 2. THE INTERMEDIATE REPRESENTATION

### 2.1 Note → SWMIDI-8

A Plainsong note like `E4` travels through the pipeline as:

```
Source text:    "E4"
Lexer:          MELODY_LINE payload: [{token: "E4", slotIndex: 0}]
Parser:         MelodyToken { type: 'note', pitches: [64], slotIndex: 0 }
Temporal:       PulseEvent { tick: 0, type: 'NoteOn', pitch: 64, velocity: 80 }
IR:             SWMIDIEvent { status: 0x9, channel: 0, data1: 64, data2: 80,
                             tick: 0, friction: 0, action: 2 (creative) }
```

Chord notes (`e2-a2-c3`) expand into multiple NoteOn events at the same tick, different pitches, slightly staggered velocities for realism.

### 2.2 Tempo / Swing / Groove Integration

slackwater-tempo's `BeatClock` and `GrooveEngine` feed into Stage 3 (Temporal Resolution). The integration is read-only — Plainsong queries the tempo engine for timing, it doesn't modify it.

```typescript
interface TempoIntegration {
  // From slackwater-tempo BeatClock:
  beatClock: {
    getBPMAt(tick: number): number;
    getTickAtTime(seconds: number): number;
    getTimeAtTick(tick: number): number;
  };
  
  // From GrooveEngine:
  groove: {
    getSwingOffset(slotIndex: number, beatsPerBar: number): number;  // in ticks
    getHumanizedTick(tick: number, seed: number): number;
    getPushDrag(tick: number): number;  // negative = push, positive = drag
  };
  
  // From EnergyAdapter (maps player behavior to BPM):
  energy: {
    detectGameState(eventDensity: number, avgVelocity: number): GameState;
    getTempoForState(state: GameState): number;
    // Adagio: 40–60 BPM, Andante: 60–90, Allegro: 90–140, Presto: 140–200
  };
}
```

The `TempoMapEntry[]` in the PulseGrid is built by querying the BeatClock at each section boundary. Per-section tempo overrides in the AST create new TempoMapEntry records. Transition curves between tempos (from slackwater-tempo's `TransitionCurve`) interpolate smoothly across bars.

Swing is applied per-slot: odd-indexed slots within a beat shift forward by `swingAmount × 0.5 × slotDuration`. This is the same formula as v2 but applied at the tick level (96 PPQ granularity) rather than the seconds level, making it sample-accurate and BPM-independent.

Groove humanization adds Gaussian jitter. The RNG seed is deterministic (hash of the source text), so the same Plainsong file always compiles to the same output — critical for reproducible builds.

### 2.3 Friction Bitfield from Notation

The Friction bitfield captures musical "roughness" — moments where the flow state is disrupted. This feeds into harmony-core's Φ (flow friction) computation and the flow state protector.

**Notation → Friction mapping:**

| Notation | Friction bits set | Meaning |
|---|---|---|
| `[resonance: high-tension]` | Bit 1 (dissonance) | Harmonic tension flagged |
| `[resonance: density-overflow]` | Bit 2 (density overflow) | Too many simultaneous voices |
| `[resonance: energy-mismatch]` | Bit 3 (energy mismatch) | Vibe descriptor contradicts output |
| Tempo change > 30 BPM | Bit 0 (timing drift) | Abrupt tempo shift |
| Dissonant chord (dim, aug) | Bit 1 (dissonance) | Inherent chord roughness |
| Polyrhythm / tuplet | Bit 4 (cadence disruption) | Rhythmic disruption |
| Bar with > 4 simultaneous players | Bit 2 (density overflow) | Voice count exceeds threshold |
| `[resonance: flow-break]` | Bit 5 (flow break) | Explicit Hurst < 0.5 marker |
| `[resonance: entropy-spike]` | Bit 6 (predictability collapse) | Shannon entropy spike |
| `[resonance: phase-desync]` | Bit 7 (phase desync) | ECN/DMN convergence failure |

Composers can set friction explicitly:

```
[resonance: high-tension, flow-break]
Chords:  | Am(dim5)  .  | .  .  |
```

This sets friction bits 1 and 5 on every event in that bar. The harmony-core flow state protector can then decide whether to mask the friction (smooth the transition) or let it through (for dramatic effect).

### 2.4 Vibe-Protocol Dimensions as Meta Events

The 16 vibe-protocol dimensions embed as SWMIDI-8 Meta events with `metaType: 0x1`. Each dimension is a float 0.0–1.0, packed into two bytes (scaled to 0–65535 for precision):

```typescript
// Vibe Meta event encoding:
// data1 = dimension ID (0–15)
// data2 = quantized value (0–127 for compact, or use Meta payload for full float)
//
// For full-precision embedding, Meta events carry a payload:
// Byte layout for Meta with payload > 8 bytes:
//   Use consecutive SWMIDI-8 events with metaType 0x1,
//   each carrying one dimension. The receiver reassembles.
//
// Vibe dimension IDs:
// 0=warmth, 1=tension, 2=mystery, 3=energy, 4=order, 5=openness,
// 6=intimacy, 7=novelty, 8=brightness, 9=density, 10=rhythm,
// 11=resonance, 12=gravity, 13=friction, 14=clarity, 15=depth
```

**Notation syntax:**
```
[vibe: tension: 0.8, energy: 0.6, warmth: 0.2]
```

This annotation attaches to the current bar (or section if placed in the header). The compiler emits 3 Meta events at the bar's start tick, one per specified dimension. Unspecified dimensions inherit from the section or composition default.

The emergence-engine's `PredictabilityEstimator` can consume these Meta events during live performance to adjust its emergence detection — if a composer marks a section `[vibe: novelty: 0.9]`, the emergence engine raises its threshold for flagging unexpected patterns.

### 2.5 Blank Bars → Stigmergy Pheromone Deposits

The `_____` syntax creates a **blank bar** — a placeholder for async collaboration. In the IR, this becomes a PheromoneDeposit Meta event:

```typescript
// PheromoneDeposit Meta event:
// status: 0xFF, metaType: 0x3
// data1: pheromone trail ID (hashed from bar position + section name)
// data2: deposit strength (0–127, default 64)
//
// Payload (via consecutive Meta events):
//   - trail type: 'build' | 'creative' | 'conversation'
//   - trail TTL: how many bars before the pheromone decays
//   - depositing agent ID
//   - vibe dimensions at deposit time
```

The stigmergy system uses these deposits to coordinate multiple agents. When agent B encounters a pheromone trail left by agent A, it can:
- **Reinforce** the trail (add its own deposit at the same bar)
- **Follow** the trail (improvise in the same key/tempo/vibe)
- **Decay** the trail (if TTL expires, the blank bar becomes a true rest)

This is how multi-agent jam sessions work: blank bars are the collaboration substrate, and pheromone trails are the coordination mechanism.

---

## 3. THE TEMPORAL MODEL

### 3.1 The 12-Pulse Architecture

The internal temporal representation is **12/8 time with 12 pulses per bar**. This is not a musical style choice — it's a mathematical one. The number 12 is the least common multiple of 3 and 4, which means:

- **4/4 fits natively**: 12 pulses ÷ 3 pulses/beat = 4 beats. Each beat = 3 pulses.
- **3/4 fits natively**: 12 pulses ÷ 4 pulses/beat = 3 beats. Each beat = 4 pulses.
- **6/8 fits natively**: 12 pulses ÷ 2 = two groups of 6 (two dotted-quarter beats).
- **12/8 is native**: 12 pulses = 1 bar, four dotted-quarter beats of 3 pulses each.

At 96 PPQ, each pulse = 8 ticks (96 ÷ 12 = 8). This gives sub-pulse resolution for swing, humanization, and micro-timing.

### 3.2 The 3:4 Polyrhythm: ECN and DMN

The tensor-midi architecture defines two neural circuits that fire on different subdivisions of the 12-pulse bar:

```
Pulse:    1  2  3  4  5  6  7  8  9  10  11  12
ECN fire: ●        ●        ●         ●          (pulses 1, 4, 7, 10)
DMN fire: ●           ●           ●              (pulses 1, 5, 9)
Converg:  ●                                   ← (pulse 1 only)
```

- **ECN (Executive Control Network)** fires every 3 pulses (quarter-note level in 4/4). This is the "reflex" circuit — it handles rhythm, structure, repetition. It processes the predictable grid.
- **DMN (Default Mode Network)** fires every 4 pulses (dotted-quarter level in 12/8). This is the "creative" circuit — it handles melody, exploration, novelty. It processes the expressive layer.
- **Convergence** at pulse 1 is the **relay bridge** — the moment when both networks synchronize. This is the **flow state**, where reflex and creativity align.

**Plainsong mapping:** Chord changes and structural events tend to align with ECN pulses (1, 4, 7, 10). Melodic peaks and expressive gestures align with DMN pulses (1, 5, 9). The convergence at pulse 1 is where key changes, section boundaries, and dramatic shifts naturally fall.

The compiler doesn't *enforce* this alignment — but the temporal resolver can optionally snap events to the nearest ECN or DMN pulse, and the friction bitfield flags events that fall *between* both networks (pulses 2, 3, 6, 8, 11, 12) as potentially "awkward" for the flow state.

### 3.3 Bar → Tick Mapping by Meter

| Meter | Beats/bar | Pulses/beat | Ticks/bar | Ticks/beat | Native? |
|-------|-----------|-------------|-----------|------------|---------|
| 4/4   | 4         | 3           | 96        | 24         | Yes     |
| 3/4   | 3         | 4           | 96        | 32         | Yes     |
| 2/4   | 2         | 6           | 96        | 48         | Yes     |
| 6/8   | 2         | 6           | 96        | 48         | Yes     |
| 12/8  | 4         | 3           | 96        | 24         | Yes (native) |
| 5/4   | 5         | —           | 120       | 24         | Extended |
| 7/8   | 3.5       | —           | 84        | 24         | Extended |

For the extended meters (5/4, 7/8), the bar no longer fits the 12-pulse grid exactly. The resolver extends the grid: 5/4 uses 15 pulses (120 ticks), 7/8 uses 10.5 pulses (84 ticks). The ECN/DMN firing pattern adapts proportionally.

### 3.4 Swing

Swing delays the off-beat. In the 12-pulse grid:

```
Straight 8ths:   pulse 1 ─── pulse 4 ─── pulse 7 ─── pulse 10 ───
Swung 8ths:      pulse 1 ────── pulse 4 ────── pulse 7 ────── pulse 10 ───
                              ↑ shifted later                    ↑ shifted later
```

At 96 PPQ with 4/4 (3 pulses/beat, 24 ticks/beat):
- Straight: on-beat at tick 0, off-beat at tick 12
- 50% swing: off-beat shifts to tick 18 (¾ of the beat)
- 100% swing: off-beat shifts to tick 24 (next beat — becomes a dotted rhythm)

**Formula:** `swingOffset = swingAmount × 0.5 × ticksPerBeat`

For 16th-note swing (the off-beat is the 2nd or 4th 16th within a beat), the same formula applies at half resolution.

### 3.5 Groove Humanization

slackwater-tempo's `GrooveEngine` adds three humanization layers:

1. **Push/drag**: consistent timing bias. "Pushed" drummers play slightly ahead of the beat; "dragging" bassists play behind. Applied as a constant tick offset per-track.
2. **Humanize**: Gaussian random jitter per-note. `σ = humanizeAmount × 2 ticks` (about ±5ms at 120 BPM).
3. **Velocity humanization**: `velocity ± rand(0, velocityRange)` where `velocityRange` defaults to 5 (matching v2's `rng.randint(-5, 5)`).

The RNG seed is the MD5 hash of the source text (same as v2), ensuring deterministic builds.

---

## 4. LANGUAGE DESIGN — Formal Grammar

### 4.1 EBNF Grammar

```ebnf
(* Plainsong v3 Grammar — EBNF *)

composition    = title-line, metadata-block, { section } ;

(* Title *)
title-line     = "**TRACK:", SP, title-text, "**" ;
title-text     = { ? printable characters ? } - "**" ;

(* Metadata *)
metadata-block = "[MetaData]", NL, { metadata-pair }, { section-break } ;
metadata-pair  = key-pair, { "|", key-pair } ;
key-pair       = "key:" SP key-value
               | "tempo:" SP integer
               | "swing:" SP integer [ "%" ]
               | "subdivision:" SP ( "8th" | "16th" | integer [ "th" ] )
               | "meter:" SP numerator "/" denominator
               | "groove:" SP groove-spec
               | "energy:" SP game-state
               | "chord_octave:" SP integer ;
key-value      = pitch-class, [ "m" ] ;
game-state     = "Adagio" | "Andante" | "Allegro" | "Presto" ;
groove-spec    = "swing:" real, "push:" real, "drag:" real, "humanize:" real ;

(* Sections *)
section        = section-header, { section-meta }, NL, { bar-line } ;
section-header = "[", section-name, "]", [ "(", section-desc, ")" ], NL ;
section-name   = letter, { letter | digit } ;
section-desc   = { ? printable chars except ')' ? } ;
section-meta   = "- tempo:" SP integer
               | "- swing:" SP integer [ "%" ]
               | "- meter:" SP numerator "/" denominator
               | "- energy:" SP game-state ;

(* Bar lines *)
bar-line       = chord-line | melody-line | lyric-line | player-line
               | repeat-open | repeat-close | volta
               | key-change | comment | blank-bar
               | resonance-annot | vibe-annot | empty-line ;

chord-line     = "Chords:", bar-sequence ;
melody-line    = "Melody:", bar-sequence ;
lyric-line     = "Lyrics:", bar-sequence ;
player-line    = "@", player-name, bar-sequence, [ "vel:" SP integer ] ;
player-name    = letter, { letter | digit | "_" } ;

(* Bar structure *)
bar-sequence   = { "|", bar-content } ;
bar-content    = { slot-token, SP }, [ SP ] ;
slot-token     = chord-symbol | note-token | "."" | "-"
               | tuplet-token ;
chord-symbol   = pitch-class, [ chord-quality ], [ "@" octave ] ;
chord-quality  = "m" | "7" | "m7" | "maj7" | "M7" | "dim" | "dim7"
               | "aug" | "sus2" | "sus4" | "add9" | "6" | "m6"
               | "9" | "m9" | { letter | digit } ;
note-token     = pitch-class, [ accidental ], octave
               | pitch-class, octave, { "-", pitch-class, octave } ;  (* chords via hyphens *)
pitch-class    = "A" | "B" | "C" | "D" | "E" | "F" | "G"
               | "a" | "b" | "c" | "d" | "e" | "f" | "g" ;
accidental     = "#" | "b" ;
octave         = digit, [ digit ] ;   (* 0–10 *)
tuplet-token   = "[", note-token, { "-", note-token }, "]", "/", integer ;

(* Repeats *)
repeat-open    = "||:" ;
repeat-close   = ":||" ;
volta          = "[", integer, "." ;

(* Key change *)
key-change     = "**key:", SP, key-value, "**" ;

(* Blank bar *)
blank-bar      = "_____" , { "_" } ;

(* Annotations *)
resonance-annot = "[resonance:", SP, tag-list, "]" ;
tag-list        = tag, { ",", SP, tag } ;
tag            = { ? lowercase letters, hyphens ? } ;
vibe-annot     = "[vibe:", SP, dim-list, "]" ;
dim-list       = dim-pair, { ",", SP, dim-pair } ;
dim-pair       = dim-name, ":", SP, real ;
dim-name       = "warmth" | "tension" | "mystery" | "energy" | "order"
               | "openness" | "intimacy" | "novelty" | "brightness"
               | "density" | "rhythm" | "resonance" | "gravity"
               | "friction" | "clarity" | "depth" ;

(* Comments *)
comment        = "%", { ? printable chars ? } ;

(* Common *)
empty-line     = NL ;
section-break  = NL, NL ;
integer        = digit, { digit } ;
real           = digit, { digit }, [ ".", digit, { digit } ] ;
numerator      = integer ;
denominator    = integer ;
NL             = ? newline ? ;
SP             = ? whitespace ? ;
```

### 4.2 Notation Examples (Validated Against Grammar)

**Basic song:**
```
**TRACK: Harbor Dawn**
[MetaData]
key: Am | tempo: 60 | swing: 0% | subdivision: 8th | meter: 4/4

[V1] (Verse - 4 Bars)
Chords:  | Am    .    | .     .    | F     .    | C     .    |
Melody: | A4    .    .   .  | E4    .    F4   .  | C4    .    A3   .  | E4    .    .    .  |
Lyrics: | dawn  .    .   .  | breaks slow       | over still water  | waking the harbor  |
@wesley | a2    .    .   .  | e2    .    f2   .  | c2    .    a1    .  | e2    .    .    .  | vel: 55
```

**With annotations:**
```
[C] (Chorus - Light Spreading - tempo: 90 - energy: Allegro)
% This section lifts the energy
[resonance: warm, high-tension]
[vibe: energy: 0.8, tension: 0.6, brightness: 0.7]
Chords:  | Am    F     | C     G     |
```

**With repeats and voltas:**
```
[V1] (Verse)
||:
Chords:  | Am    .    | F     .    |
:||

[B] (Bridge)
||:
Chords:  | Dm    .    | Am    .    |
[1. Melody: | D4    .    | C4    .    |
[2. Melody: | A4    .    | G4    .    |
:||
```

**With blank bars (stigmergy):**
```
[J] (Jam Room - 4 Bars)
Chords:  | Am    .    | _____ | F     .    | _____ |
```

**With tuplets:**
```
Melody: | [E4-G4-B4]/3 . . . | A4 . . . |
```

**With key change:**
```
[C] (Chorus)
**key: G**
Chords:  | G    .    | C    .    |
```

### 4.3 Token Semantics

| Token | Meaning | Duration |
|-------|---------|----------|
| `E4` | Note E4 (MIDI 64) | 1 slot |
| `e2-a2-c3` | Chord (A2, C3, E3) | 1 slot |
| `.` | Sustain previous | extends previous note |
| `-` | Rest | terminates previous note |
| `[E4-G4-B4]/3` | Triplet | occupies 2 slots, plays 3 notes |
| `Am` | A minor chord | from symbol table |
| `Am@3` | A minor, voiced in octave 3 | from symbol table, custom octave |
| `_____` | Blank bar | full bar of silence + pheromone deposit |
| `%` comment | Ignored by compiler | — |
| `[resonance: ...]` | Resonance annotation | attaches to bar/section |
| `[vibe: ...]` | Vibe dimensions | attaches to bar/section |

---

## 5. BACKEND SPECS

### 5.1 MIDI File Backend

Consumes `SWMIDIEvent[]` → produces Standard MIDI File (Format 1, multiple tracks).

```typescript
interface MIDIFileBackend {
  format: 1;                    // multi-track
  division: 96;                 // PPQ (matches our grid)
  tracks: MIDITrack[];
  tempoMap: TempoMapEntry[];    // from PulseGrid
}

interface MIDITrack {
  name: string;                 // 'chords', 'melody', 'wesley', etc.
  channel: number;              // 0–15
  program: number;              // GM program (0–127)
  isDrum: boolean;
  events: MIDIFileEvent[];
}

interface MIDIFileEvent {
  tick: number;                 // delta or absolute (configurable)
  status: number;               // standard MIDI status byte
  data1: number;
  data2: number;
  metaType?: number;            // for Meta events
  metaValue?: Uint8Array;
}
```

**Conversion from SWMIDI-8:**
1. **Group events by channel** (each channel = one track)
2. **Sort by tick** within each track
3. **Convert delta times** (SWMIDI uses absolute ticks; SMF uses delta)
4. **Expand Meta events**: vibe dimensions → standard MIDI text meta events or custom SysEx
5. **Insert tempo changes** from TempoMap as standard MIDI tempo meta events (0xFF 0x51 0x03)
6. **Drop PheromoneDeposit events** (no MIDI equivalent — used only by live backend)
7. **Write SMF** using `pretty_midi` (Python) or `midi-file` (JS)

**Track assignment:**
- Channel 0: Chords track (if present)
- Channel 1: Melody track (if present)
- Channels 2+: One per @player, assigned in order of first appearance
- Channel 9 (10th): Drum tracks (GM standard)

### 5.2 WAV Backend

Consumes `SWMIDIEvent[]` → produces 16-bit PCM WAV via numpy synthesis.

```typescript
interface WAVBackend {
  sampleRate: number;           // 44100 default
  bitDepth: 16;
  channels: 1;                  // mono (stereo = future)
  masterVolume: number;         // 0.85 (matches v2)
  instruments: Map<string, SynthFn>;
}

type SynthFn = (
  frequency: number,            // Hz
  duration: number,             // seconds
  sampleRate: number,
  velocity: number              // 0.0–1.0
) => Float64Array;
```

**Synthesizer functions (ported from v2):**

| Instrument | Function | Harmonics | ADSR |
|-----------|----------|-----------|------|
| Piano | `synth_piano` | 1:1.0, 2:0.4, 3:0.2, 4:0.1 (signed sine) | A:0.005 D:0.3 S:0.3 R:0.2 |
| Bass | `synth_bass` | 1:1.0, 2:0.3 (sine) | A:0.02 D:0.15 S:0.5 R:0.1 |
| Strings | `synth_strings` | Detuned sawtooth (3 oscillators ±0.5%) | A:0.15 D:0.1 S:0.7 R:0.3 |
| Flute | `synth_flute` | Sine with vibrato (5.5 Hz, ±2%) | A:0.08 D:0.05 S:0.8 R:0.15 |
| Guitar | `synth_guitar` | 1:1.0, 2:0.5, 3:0.3, 4:0.15 (exp decay) | A:0.003 D:0.4 S:0.2 R:0.3 |
| Drums | `synth_drum` | Kick: pitch-drop sine; Snare: noise+tone; Hat: noise | Exponential decay |

**Conversion pipeline:**
1. **Compute song duration** from last NoteOff tick → seconds via TempoMap
2. **Allocate buffer**: `np.zeros(totalSamples, dtype=np.float64)`
3. **For each NoteOn event**: determine instrument from channel/track, synthesize waveform, apply ADSR, scale by velocity/127
4. **Mix into buffer** at the correct sample offset
5. **Normalize** to peak 0.85
6. **Convert to int16** and write WAV

The synthesis functions are identical to v2 — they produce good results. The improvement is that they now consume SWMIDI-8 events instead of re-parsing a MIDI file from disk (eliminating the v2 round-trip through `pretty_midi`).

### 5.3 Live Stream Backend

Consumes `SWMIDIEvent[]` → real-time WebSocket bus for multi-agent jam sessions.

```typescript
interface LiveStreamBackend {
  transport: 'websocket';
  url: string;                  // ws://relay.example.com/jam/{roomId}
  mode: 'sequencer' | 'reactive';
  tickWindow: number;           // how far ahead to schedule (ticks)
  
  // Sequencer mode: plays the IR on a clock, sending events in real-time
  // Reactive mode: waits for stigmergy signals, improvises in response
}

interface LiveEvent {
  event: SWMIDIEvent;           // the 8-byte IR
  timestamp: number;            // wall-clock delivery time (ms)
  agentId: string;              // which agent sent this
  roomId: string;
}
```

**Architecture:**
```
Agent A (TypeScript)                Agent B (Python)           Agent C (Rust)
     │                                   │                          │
     ▼                                   ▼                          ▼
 Plainsong ──► SWMIDI-8 ──► WS ──► Relay Server ◄── WS ◄── SWMIDI-8 ◄── Plainsong
                                (Cloudflare Worker)
                                     │
                                     ▼
                              Stigmergy Engine
                              (pheromone trails,
                               decay/reinforce,
                               emergence detection)
```

The relay server is a Cloudflare Worker (already deployed: `lucineer-relay`). It receives SWMIDI-8 events from each agent, merges them by tick position, and broadcasts the merged stream back to all participants.

**PheromoneDeposit events** are processed by the stigmergy engine running alongside the relay. When an agent encounters a pheromone trail, the engine can:
- Modify the agent's vibe dimensions (warm the room when a trail is reinforced)
- Adjust the energy adapter (speed up or slow down based on trail density)
- Trigger emergence events (Synergy, PhaseTransition) when trails converge

**Clock synchronization:** The relay maintains a master clock (96 PPQ). Agents report their tick positions; the relay computes drift and sends correction factors. This is the same mechanism as MIDI Clock / Song Position Pointer, but over WebSocket.

---

## 6. IMPLEMENTATION PLAN

### 6.1 Language Assignments

| Component | Language | Library | Rationale |
|-----------|----------|---------|-----------|
| Lexer | Python | `lark` (Earley/LALR) | Fastest to build, excellent error messages, supports EBNF grammar directly |
| Parser | Python | `lark` (same grammar) | Shares grammar file with lexer; `lark` handles both stages |
| Temporal Resolution | Python | `slackwater-tempo` (Python) | BeatClock, GrooveEngine, EnergyAdapter are already Python |
| IR Codec (SWMIDI-8) | Python | new `swmidi8.py` | Port from JS implementation; pure Python encode/decode |
| MIDI File Backend | Python | `pretty_midi` (already a dependency) | Proven, well-tested, handles SMF correctly |
| WAV Backend | Python | `numpy` + `scipy.io.wavfile` | Already implemented in v2; port synthesis functions directly |
| Live Stream Backend | TypeScript | `ws` (WebSocket) | Real-time I/O is TS's strength; relay is already a CF Worker |
| Stigmergy Integration | TypeScript | existing `stigmergy` package | Already TS; plugs into live backend |

### 6.2 Package Structure

```
plainsong/
├── docs/
│   └── architecture/
│       └── compiler-v3-spec.md       ← this document
├── src/
│   └── plainsong/
│       ├── __init__.py
│       ├── grammar/
│       │   └── plainsong.lark        ← formal grammar (EBNF → Lark syntax)
│       ├── lexer.py                  ← Stage 1: text → LineToken[]
│       ├── parser.py                 ← Stage 2: LineToken[] → Composition AST
│       ├── temporal.py               ← Stage 3: AST → PulseGrid (96 PPQ)
│       ├── ir.py                     ← Stage 4: PulseGrid → SWMIDIEvent[]
│       ├── swmidi8.py                ← SWMIDI-8 codec (encode/decode)
│       ├── backends/
│       │   ├── __init__.py
│       │   ├── midi_backend.py       ← Stage 5a: SWMIDI → SMF
│       │   ├── wav_backend.py        ← Stage 5b: SWMIDI → WAV
│       │   └── live_backend.py       ← Stage 5c: SWMIDI → WebSocket (stub, full impl in TS)
│       ├── instruments.py            ← synth_piano, synth_bass, etc. (ported from v2)
│       ├── chord_shapes.py           ← chord symbol → interval mapping (ported from v2)
│       ├── note_utils.py             ← parse_absolute_note, midi_to_note_name, transpose
│       ├── compiler.py               ← orchestrates all 5 stages
│       ├── cli.py                    ← --cli mode entry point
│       └── web.py                    ← web UI server (port 5557, backward compatible)
├── tests/
│   ├── test_lexer.py                 ← tokenization tests
│   ├── test_parser.py                ← AST construction tests
│   ├── test_temporal.py              ← tick assignment, swing, groove
│   ├── test_ir.py                    ← SWMIDI-8 encode/decode round-trip
│   ├── test_midi_backend.py          ← compare against v2 MIDI output
│   ├── test_wav_backend.py           ← compare against v2 WAV output
│   ├── test_golden.py                ← golden file tests (5 example compositions)
│   └── fixtures/
│       ├── harbor_dawn.song
│       ├── the_room_is_safe.song
│       ├── creatures_of_interval.song
│       ├── neon_shadows.song
│       └── deck_work.song
├── scripts/
└── live/
    └── relay/                        ← TypeScript live backend
        ├── package.json
        ├── tsconfig.json
        ├── src/
        │   ├── relay.ts              ← WebSocket relay (CF Worker)
        │   ├── stigmergy.ts          ← pheromone trail engine
        │   └── clock.ts              ← master clock synchronization
        └── test/
            └── relay.test.ts
```

### 6.3 Test Strategy

**Unit tests** — each stage tested in isolation:
- Lexer: every token type, edge cases (empty lines, malformed input, comments mid-line)
- Parser: every grammar production, bar-count validation, meter parsing, annotation attachment
- Temporal: tick math for each meter, swing offsets, groove humanization determinism
- IR: SWMIDI-8 encode/decode round-trip, friction bitfield correctness, Meta event encoding
- Backends: MIDI file structure (format, division, track count), WAV sample rates, live event ordering

**Integration tests** — full pipeline:
- Compile each of the 5 golden compositions through all 5 stages
- Compare MIDI output against v2 output (pitch-identical, timing may differ due to grid improvements)
- Compare WAV output (audio similarity threshold, not byte-identical, due to humanization RNG changes)

**Regression tests:**
- All edge cases from `examples/edge-cases/` must produce no silent failures
- BUG-1 through BUG-5 from `BUGS.md` must be fixed and tested

**Golden file tests:**
- `fixtures/*.song` files are the canonical test inputs
- `fixtures/*.expected.mid` and `*.expected.wav` are committed expected outputs
- CI runs `compiler.py --cli fixture.song --midi out.mid` and diffs against expected

### 6.4 Migration Path from v2

**Phase 1: Parallel operation (Week 1–2)**
- Build lexer + parser. Keep v2 running on port 5557.
- v3 runs on port 5558.
- Both consume the same `.song` files.
- Comparison: compile same file in both, diff the MIDI output.

**Phase 2: Backend porting (Week 2–3)**
- Port synthesis functions from v2 to v3 (`synth_piano`, `synth_bass`, etc.)
- Port chord shapes table.
- Implement SWMIDI-8 codec.
- v3 now produces both MIDI and WAV.

**Phase 3: Temporal model (Week 3–4)**
- Implement PulseGrid resolution with 12-pulse model.
- Integrate slackwater-tempo BeatClock for tempo maps.
- Add per-section metadata support.
- Add meter declaration support.
- All edge cases pass without silent failures.

**Phase 4: Live backend (Week 4–5)**
- TypeScript WebSocket relay.
- Stigmergy engine integration.
- Multi-agent jam testing.

**Phase 5: Cutover (Week 6)**
- v3 takes over port 5557.
- v2 is archived.
- All examples, tests, and documentation updated.

### 6.5 SWMIDI-8 Codec API (Python)

```python
# src/plainsong/swmidi8.py

from dataclasses import dataclass
from typing import List

@dataclass
class SWMIDIEvent:
    status: int       # 0x9=NoteOn, 0x8=NoteOff, 0xB=CC, 0xC=ProgramCh, 0xFF=Meta
    channel: int      # 0-15
    data1: int        # pitch / CC# / program / meta-subtype
    data2: int        # velocity / CC value
    tick: int         # 0-16777215 (24-bit at 96 PPQ)
    friction: int     # 0-15 (4-bit)
    action: int       # 0-15 (conversation=0, build=1, creative=2, system=3)
    meta_type: int    # 0-15
    flags: int        # 0-15

    def encode(self) -> bytes:
        """Pack to exactly 8 bytes."""
        b0 = (self.status << 4) | (self.channel & 0x0F)
        b1 = self.data1 & 0xFF
        b2 = self.data2 & 0xFF
        b3 = (self.tick >> 16) & 0xFF
        b4 = (self.tick >> 8) & 0xFF
        b5 = self.tick & 0xFF
        b6 = ((self.friction & 0x0F) << 4) | (self.action & 0x0F)
        b7 = ((self.meta_type & 0x0F) << 4) | (self.flags & 0x0F)
        return bytes([b0, b1, b2, b3, b4, b5, b6, b7])

    @classmethod
    def decode(cls, data: bytes) -> 'SWMIDIEvent':
        """Unpack 8 bytes to SWMIDIEvent."""
        assert len(data) == 8
        status = (data[0] >> 4) & 0x0F
        channel = data[0] & 0x0F
        data1 = data[1]
        data2 = data[2]
        tick = (data[3] << 16) | (data[4] << 8) | data[5]
        friction = (data[6] >> 4) & 0x0F
        action = data[6] & 0x0F
        meta_type = (data[7] >> 4) & 0x0F
        flags = data[7] & 0x0F
        return cls(status, channel, data1, data2, tick,
                   friction, action, meta_type, flags)


def encode_stream(events: List[SWMIDIEvent]) -> bytes:
    """Encode a list of events to a binary stream."""
    return b''.join(e.encode() for e in events)


def decode_stream(data: bytes) -> List[SWMIDIEvent]:
    """Decode a binary stream to a list of events."""
    assert len(data) % 8 == 0
    return [SWMIDIEvent.decode(data[i:i+8]) for i in range(0, len(data), 8)]
```

### 6.6 Compiler Entry Point

```python
# src/plainsong/compiler.py

from typing import Optional
from .lexer import lex
from .parser import parse
from .temporal import resolve_temporal
from .ir import lower_to_swmidi
from .backends.midi_backend import write_midi
from .backends.wav_backend import write_wav

def compile_plainsong(
    source: str,
    output_midi: Optional[str] = None,
    output_wav: Optional[str] = None,
    tempo_override: Optional[int] = None,
    swing_override: Optional[int] = None,
    key_override: Optional[str] = None,
) -> CompilationResult:
    """
    Full 5-stage compiler pipeline.
    
    Stage 1: lex(source) → LineToken[]
    Stage 2: parse(tokens) → Composition AST  
    Stage 3: resolve_temporal(ast) → PulseGrid
    Stage 4: lower_to_swmidi(grid) → SWMIDIEvent[]
    Stage 5: backends write from SWMIDIEvent[]
    """
    # Stage 1: Lex
    tokens = lex(source)
    
    # Stage 2: Parse  
    ast = parse(tokens)
    
    # Apply overrides
    if tempo_override:
        ast.metadata.tempo = tempo_override
    if swing_override is not None:
        ast.metadata.swing = swing_override
    if key_override:
        ast = transpose_composition(ast, key_override)
    
    # Stage 3: Temporal Resolution
    grid = resolve_temporal(ast)
    
    # Stage 4: IR Lowering
    ir = lower_to_swmidi(grid)
    
    # Stage 5: Backends
    result = CompilationResult(ast=ast, grid=grid, ir=ir)
    if output_midi:
        result.midi_path = write_midi(ir, grid.tempoMap, output_midi)
    if output_wav:
        result.wav_path = write_wav(ir, grid.tempoMap, output_wav)
    
    return result


@dataclass
class CompilationResult:
    ast: Composition
    grid: PulseGrid
    ir: List[SWMIDIEvent]
    midi_path: Optional[str] = None
    wav_path: Optional[str] = None
    warnings: List[CompilerWarning] = field(default_factory=list)
```

---

## 7. APPENDIX — Friction → harmony-core Integration

The Friction bitfield on every SWMIDI-8 event feeds into harmony-core's Φ (flow friction) computation:

```rust
// harmony-core (Rust) — consumes SWMIDI-8 friction bits

pub fn compute_phi(events: &[SWMIDIEvent], window: usize) -> f64 {
    // Φ = weighted sum of friction bit densities over the window
    // Higher Φ = more flow disruption = flow state protector may intervene
    
    let window_events = &events[..window.min(events.len())];
    let total = window_events.len() as f64;
    
    let timing_drift = count_bit(window_events, 0) / total;
    let dissonance = count_bit(window_events, 1) / total;
    let density = count_bit(window_events, 2) / total;
    let energy = count_bit(window_events, 3) / total;
    
    // Weighted combination (weights from harmony-core calibration)
    0.3 * timing_drift + 0.25 * dissonance 
    + 0.2 * density + 0.25 * energy
}

pub fn detect_flow_state(events: &[SWMIDIEvent], phi: f64) -> FlowState {
    // State machine: Calm → Engaged → Flow → Stressed → Overwhelmed
    // Transition based on Φ threshold and Hurst exponent of event timing
    let hurst = hurst_exponent(&event_intervals(events));
    let entropy = shannon_entropy(&event_velocities(events));
    
    match (phi, hurst, entropy) {
        (p, h, _) if p < 0.2 && h > 0.7 => FlowState::Flow,
        (p, h, _) if p < 0.3 && h > 0.6 => FlowState::Engaged,
        (p, _, _) if p < 0.15 => FlowState::Calm,
        (p, _, _) if p < 0.5 => FlowState::Stressed,
        _ => FlowState::Overwhelmed,
    }
}
```

The flow state protector can then modify the PulseGrid in real-time (during live performance): if Φ exceeds the flow threshold, it can simplify dense passages, remove dissonant notes, or slow the tempo — restoring the flow state without human intervention.

---

## 8. REFERENCES

- **SWMIDI-8 Wire Format**: `tensor-midi/src/swmidi.js` (canonical JS implementation, 210 lines)
- **harmony-core**: `slackwater-rust` (Rust crate, Hurst exponent + Shannon entropy + Φ)
- **slackwater-tempo**: Python package (BeatClock, GrooveEngine, EnergyAdapter, GameState)
- **vibe-protocol**: TS/Python/Rust (16-dimensional room descriptors)
- **emergence-engine**: Python (PredictabilityEstimator, 5 emergence types)
- **stigmergy**: TypeScript (Pheromone trails, decay/reinforcement)
- **Plainsong v2**: `scripts/plainsong_v2.py` (1675 lines, the compiler this replaces)
- **Structural Analysis**: `docs/structural-analysis.md` (bugs, limitations, recommendations)
- **Edge Cases**: `examples/edge-cases/BUGS.md` (BUG-1 through BUG-5)

---

*End of specification. This document is the build contract — every line of code in the v3 compiler should trace back to a section here.*
