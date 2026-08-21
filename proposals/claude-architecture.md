# Architecture Proposal: Plainsong as a Programmable Jam Document
### Systems angle — compiler, type system, async event model, DAW renderer
**Author:** Claude (Piano — systems thinker) · **Date:** 2026-08-12

> Note on process: I polled for `scripts/architecture-brief.md` every 10s for 2 minutes per instructions; it never appeared. This proposal is grounded instead in the three source documents I was told to read — `fleet-jepa-midi/README.md`, `POLYFORMALISM.md`, `src/swmidi.js` — plus the existing `scripts/plainsong.py` prototype, which already implements a first draft of the notation this proposal formalizes and extends.

---

## 1. Thesis

Plainsong should stop being "a regex-parsed DSL that emits `pretty_midi` calls" and become **a real small language**: lexer -> parser -> typed AST -> temporal resolution -> SWMIDI-8 IR -> multiple backends (MIDI file, live stream, DAW renderer). The jam session is a **document**, in the Pollen/Scribble sense — prose and executable notation share one surface syntax, and the document *is* the program. Compiling it is not a side effect of playing it; playing it (live, multi-agent, async) is one interpretation of the compiled IR, and rendering a `.mid` file is another.

The three things that make this different from a normal toy-DSL exercise:

1. **The clock is not the DAW's clock, it's the fleet's clock.** Time in Plainsong is `bar:beat` in 12/8 — 12 pulses/bar, 96 PPQ, 48 ticks/pulse — the same grid `engine.js`, `tempo-core` (Rust), and every polyformalism implementation already share. Plainsong compiles *into* that grid, not into `pretty_midi` seconds. This is the fix the current `plainsong.py` needs most: it hardcodes `beats_per_bar=4` and wall-clock seconds, throwing away the 3:4 (ECN/DMN) resolution-at-12 structure that's the actual architecture of the project.
2. **Events arrive asynchronously from multiple agents**, not from one linear parse of a file top-to-bottom. A `.song` file is the offline/replay case; the live jam is N agents each emitting SWMIDI-8 events against a shared BeatClock, arbitrarily interleaved, sometimes late, sometimes speculative. The compiler has to support both from the same IR.
3. **The document is programmable.** Following Pollen/Scribble: `@agent` isn't just a field selector, it's the `@`-reader. Plainsong should let a jam define macros (`@define riff-a = ...`), splice prose and notation, and expand before typing — exactly Pollen's "preprocess, then read, then render" pipeline, and exactly Scribble's `@command[args]{body}` uniform syntax for text-that-is-also-code.

---

## 2. Layered architecture

```
+-----------------------------------------------------------------------+
|  SURFACE: .song documents (prose + notation, Pollen-style)             |
|    @define, @agent, prose spans, notation spans                       |
+---------------------------------+---------------------------------------+
                                  |  1. PREPROCESS (macro expansion)
+---------------------------------v---------------------------------------+
|  LEXER -> token stream (agent-decl, timing, note, text, macro-call)   |
+---------------------------------+---------------------------------------+
                                  |  2. PARSE
+---------------------------------v---------------------------------------+
|  AST  (Program, AgentDecl, Voice, Event nodes — see section 5)        |
+---------------------------------+---------------------------------------+
                                  |  3. TYPE CHECK  (see section 4)
+---------------------------------v---------------------------------------+
|  TYPED AST  (every node carries a resolved Type + diagnostics)        |
+---------------------------------+---------------------------------------+
                                  |  4. TEMPORAL RESOLUTION
|  bar:beat (rational, 12/8) --> PulseTick (uint32, 96 PPQ grid)        |
+---------------------------------+---------------------------------------+
                                  |  5. LOWER TO IR
+---------------------------------v---------------------------------------+
|  SWMIDI-8 EVENT STREAM  (the IR — see section 6; = wire format)       |
+------+---------------------+---------------------+----------------------+
       |                     |                     |
       v                     v                     v
+-------------+     +----------------+     +----------------------+
| MIDI file    |     | Live SWMIDI    |     | DAW Renderer          |
| backend      |     | bus (agents    |     | (mixer board, jazz    |
| (offline,    |     | publish async, |     | analyzer, chart       |
| pretty_midi) |     | BeatClock-     |     | plotter — subscribes  |
|              |     | ordered merge) |     | to the bus)           |
+-------------+     +----------------+     +----------------------+
```

The key move: **the SWMIDI-8 event stream is the IR, not just the wire format.** Everything downstream of type-checking — file compilation, the live multi-agent bus, the DAW renderer — consumes the same 8-byte-event shape. That's why `swmidi.js` already existing as a clean codec matters: it's not "the export format," it's the intermediate representation the whole compiler targets. One codec, three backends.

---

## 3. Plainsong v2 surface syntax — the jam as a Pollen/Scribble document

Current `plainsong.py` syntax (kept, because it's good — terse, greppable, line-oriented):

```
@sax   saxophone
@bass  bass

:@sax  | bar:1 beat:1   | "the pulse resolves at twelve"
|@sax  | bar:1 beat:1   | note:C4 dur:1 vel:90 articulation:accent
|@bass | bar:1 beat:1   | note:C2 dur:2 vel:70
```

What's missing is exactly the Pollen/Scribble move: **the document should be able to define reusable notation and mix prose freely**, not just declare agents and drop flat event lines. Proposed additions:

```
#lang plainsong/1

@define riff-a(root, vel: 80) = {
  note:{root} dur:0.5 vel:{vel}
  note:{root+4} dur:0.5 vel:{vel}
  note:{root+7} dur:1 vel:{vel+10} articulation:accent
}

@sax saxophone
@bass bass

: The tune opens on the resolution point — beat 1, where the 3-pulse
  and 4-pulse cycles meet. @sax and @bass land together.

|@sax  | bar:1 beat:1 | riff-a(C4, vel:90)
|@bass | bar:1 beat:1 | note:C2 dur:3

: @bass holds through the ECN reflex beats (1, 4, 7, 10); @sax
  answers on the DMN creative beats (1, 5, 9).
```

- `@define name(args) = { ... }` is a **macro**, expanded in the preprocess pass before lexing — pure textual/AST substitution, Pollen-style. `{root+4}` is an interpolated expression, evaluated at expansion time (integer arithmetic on note numbers, resolved by the same `note_to_midi` table `plainsong.py` already has).
- `:` lines are prose (already true today) but now first-class **document content**, not just lyric-track output — they can reference `@agent` names inline and the type checker resolves those references, so a rename of an agent is a checked operation across the whole document, prose included. This is the Scribble insight: text and code share one reader, so cross-references between them are checkable, not just conventions.
- `#lang plainsong/1` is a version pragma — cheap, but it's what lets the compiler evolve the grammar (e.g., moving from 4/4-seconds timing to 12-pulse timing) without silently misinterpreting old `.song` files.

This is additive over the current parser: agent declarations and bare event lines still parse exactly as they do now. The new surface is macros + checked prose references, layered on top via a preprocess pass that runs before `parse_plainsong`.

---

## 4. Type system

Plainsong's type system exists to catch exactly the errors that are currently silent in `plainsong.py` (e.g. `_parse_musical_payload` returns `[]` and swallows anything it doesn't recognize — a typo in a field name just vanishes). Types:

**Primitive types**

| Type | Range / shape | Notes |
|---|---|---|
| `AgentId` | interned string | must resolve to an `@agent` declaration in scope |
| `Channel` | `0..15` | derived from agent declaration order, or explicit `channel:N` |
| `BarBeat` | `(bar: uint, beat: rational)` | surface time; `beat` is rational so `beat:1.5` and `beat:4/3` (triplet) both typecheck |
| `PulseTick` | `uint32` | resolved time on the 96-PPQ / 12-pulse grid; only exists after temporal resolution |
| `Pitch` | `0..127` | note name (`C4`) or raw int; note-name parsing reuses `note_to_midi` |
| `Velocity` | `1..127` | 0 is rejected — a zero-velocity NoteOn is a NoteOff in real MIDI and Plainsong should not let that ambiguity leak in as a "note" |
| `Duration` | positive rational, in **beats** | resolved to ticks at lowering time, not before (so tempo/grid changes don't require re-authoring) |
| `Program` | GM program `0..127` | via the existing `INSTRUMENT_MAP` name table, or raw int |
| `FrictionMask` | `0..255` bitfield | maps directly to `Friction` in `swmidi.js` — lets a jam encode "this phrase was a collision/timeout/ambiguity" as a first-class musical fact, not just a system log |

**Composite / structural types**

```
EventNode :=
  | NoteEvent   { agent: AgentId, at: BarBeat, pitch: Pitch, dur: Duration,
                  vel: Velocity, articulation: Articulation }
  | RestEvent   { agent: AgentId, at: BarBeat }
  | PercEvent   { agent: AgentId, at: BarBeat, drum: DrumName, vel: Velocity,
                  pattern: Option<StepPattern> }
  | CCEvent     { agent: AgentId, at: BarBeat, cc: uint7, value: uint7 }
  | BendEvent   { agent: AgentId, at: BarBeat, bend: int14 }
  | TempoEvent  { at: BarBeat, bpm: uint }
  | ProgEvent   { agent: AgentId, at: BarBeat, program: Program }
  | TextEvent   { agent: AgentId, at: BarBeat, text: string }   -- prose, still typed & timed
```

Every `EventNode` is a **sum type** discriminated by the same 4-bit `eventType` nibble SWMIDI-8 already defines (`NoteOn=0, NoteOff=1, ControlChange=2, ProgramChange=3, Meta=4`) — `RestEvent`/`TempoEvent`/`TextEvent` all lower to `Meta` events with different `ActionType` pitches (`plainsong.py`'s own `ActionType` enum in `swmidi.js` already has room: `IdeaProposed`, `Heartbeat`, etc. — Plainsong text events should reuse `ActionType.MessageSent`/`Meta` rather than inventing a parallel channel).

**Static checks the type checker performs** (none of these exist today — they currently fail silently or crash at MIDI-write time):

1. **Agent scope** — every `@agent` reference in an event or macro must have a preceding `@agent` declaration in the document (or be a macro parameter). Undeclared agent -> hard error with line number.
2. **Channel uniqueness** — at most one agent per SWMIDI channel (`0..15`) unless explicitly multiplexed; two agents silently sharing channel 3 today just means their events interleave indistinguishably on decode — that's a real bug class this catches.
3. **Range checks** — `Velocity`, `Pitch`, `cc`, `program` all checked against their legal range at parse time, not at `pretty_midi` write time (currently `plainsong.py` clamps with `max(1, min(127, ...))`, which *hides* an authoring error instead of reporting it).
4. **Duration positivity** — zero/negative durations rejected.
5. **Macro arity/type** — `@define` calls checked against declared parameters, interpolated arithmetic (`{root+4}`) checked to stay in `Pitch` range after evaluation.
6. **Timing monotonicity (soft)** — within one agent's own event list, `(bar, beat)` should be non-decreasing; violations are a warning (agents *can* legitimately emit out-of-order live, see section 7) but in an offline `.song` file it's almost always a typo.

---

## 5. AST — data structures

```ts
// Surface AST, produced by the parser, consumed by the type checker.

interface Program {
  version: string;               // "plainsong/1"
  macros: Map<string, MacroDef>;
  agents: AgentDecl[];
  body: DocNode[];                // top-level ordered content: prose + events, interleaved
}

interface MacroDef {
  name: string;
  params: { name: string; default?: Expr }[];
  body: DocNode[];                 // unexpanded — instantiated per call site
}

interface AgentDecl {
  name: string;
  instrument: string;              // GM instrument name, resolved via INSTRUMENT_MAP
  channel?: number;                // explicit override; else assigned by declaration order
  line: number;
}

// DocNode is the union that keeps prose and notation on equal footing —
// this is the Scribble move: one tree, not "text nodes" bolted onto "code nodes."
type DocNode =
  | { kind: "prose"; agent?: string; text: string; line: number }
  | { kind: "event"; event: EventNode; line: number }
  | { kind: "macro-call"; name: string; args: Expr[]; line: number };

// EventNode as in section 4, plus a `raw` BarBeat (surface time) — PulseTick is
// added by a later pass, not present here. This is deliberate: the AST
// should be resolvable against *different* grids (e.g. a hypothetical
// 16-pulse variant) without re-parsing.
interface EventNodeBase {
  agent: string;
  at: BarBeat;
  line: number;
}
```

**Why prose and events share one `DocNode[]` list instead of two parallel arrays** (as `plainsong.py` currently does with `agents, events`): a jam is fundamentally a *sequence* — the prose commentary at bar 3 is causally between the notes at bar 2 and bar 4, and a document-level pass (rendering, or a future "annotate why this phrase happened" tool) needs that interleaving preserved. Two parallel arrays lose that.

---

## 6. The IR: SWMIDI-8 as compilation target

This is the central design decision: **lowering doesn't invent a new IR, it targets the existing wire format directly.**

```ts
// This is exactly swmidi.js's event shape — the compiler's IR literally
// *is* the wire format, plus one extra field only relevant pre-encode.
interface IRSwmidiEvent {
  eventType: EventType;   // 4 bits
  channel: number;        // 4 bits — assigned from AgentDecl at lowering
  pitch: number;          // 0-127 — ActionType, note number, or CC number depending on context
  velocity: number;       // 0-127
  errorMask: number;      // FrictionMask — 0 for authored/offline events
  tick: number;            // uint32 — PulseTick, resolved from BarBeat
  sourceLine?: number;     // debug info, stripped before encodeEvent()
}
```

**Temporal resolution (BarBeat -> PulseTick)** is the one pass that has to change from what `plainsong.py` does today. Current code:

```python
spb = 60.0 / bpm
def t_of(bar, beat):
    return ((bar - 1) * beats_per_bar + (beat - 1)) * spb   # seconds, 4/4 assumed
```

Proposed replacement, grid-native (12/8, matches `engine.js` / `tempo-core`):

```ts
const PPQ = 96;
const PULSES_PER_BAR = 12;
const TICKS_PER_PULSE = 48;          // 96 / 2
const TICKS_PER_BAR = 576;           // 12 * 48

function resolveTick(at: BarBeat): PulseTick {
  // BarBeat.beat is a rational number of *pulses* (1..12), not quarter-note beats.
  // beat:1 == pulse 1 == tick 0. beat:1.5 == halfway through pulse 1.
  const barTicks = (at.bar - 1) * TICKS_PER_BAR;
  const pulseTicks = (at.beat - 1) * TICKS_PER_PULSE;
  return Math.round(barTicks + pulseTicks) >>> 0;
}
```

Wall-clock time (for the MIDI-file backend or audio scheduling) is derived from `PulseTick` + a `TempoMap` at the *last* stage, not baked in during resolution — this is what lets the same resolved IR feed a live jam (where tempo can rubato) and an offline `.mid` export (fixed tempo) without re-resolving.

**Duration and articulation lowering** stays essentially what `plainsong.py` already does (staccato = 0.5x, legato = 1.05x, accent = +15 velocity) — that logic is fine, it just now operates in ticks instead of seconds:

```ts
function lowerNote(e: NoteEvent, ctx: LoweringCtx): IRSwmidiEvent[] {
  const onTick = resolveTick(e.at);
  const durTicks = Math.round(e.dur * TICKS_PER_PULSE);
  let offTick = onTick + durTicks;
  let vel = e.vel;
  if (e.articulation === "staccato") offTick = onTick + Math.round(durTicks * 0.5);
  if (e.articulation === "legato")   offTick = onTick + Math.round(durTicks * 1.05);
  if (e.articulation === "accent")   vel = Math.min(127, vel + 15);

  return [
    { eventType: EventType.NoteOn,  channel: ctx.channelOf(e.agent), pitch: e.pitch, velocity: vel, errorMask: 0, tick: onTick },
    { eventType: EventType.NoteOff, channel: ctx.channelOf(e.agent), pitch: e.pitch, velocity: 0,   errorMask: 0, tick: offTick },
  ];
}
```

Two events out (NoteOn/NoteOff), matching real MIDI semantics — `plainsong.py`'s `pretty_midi.Note(vel, pitch, st, et)` currently hides this pairing inside `pretty_midi`'s object model; making it explicit in the IR is what lets the *live* backend (section 7) stream NoteOn now and NoteOff later, independently.

---

## 7. Async multi-agent event model — the actual hard part

A `.song` file is a closed, ordered document. A live jam is not: N agents (Piano/Claude, Saxophone/KimiCode, Bass/OpenCode, Producer/MMX, plus future agents) each hold a `BeatClock` reference and **emit SWMIDI-8 events independently**, on their own wall-clock schedule, targeting ticks on the shared grid. The compiler pipeline above (section 2 steps 1-5) is the *offline* path. Live jamming needs the same type system and IR, but a different front door.

**Design: each agent is a producer into a shared, tick-ordered event bus; the bus is the thing the DAW renderer subscribes to.**

```ts
interface AgentChannel {
  agentId: AgentId;
  channel: number;             // 0-15, assigned at session start
  emit(event: Omit<IRSwmidiEvent, "channel">): void;
}

class JamSession {
  private beatClock: BeatClock;               // shared, from engine.js
  private ring: SwmidiRingBuffer;              // bounded, same shape as swmidi.js's stream
  private subscribers: Set<(e: IRSwmidiEvent) => void> = new Set();
  private lookaheadTicks = TICKS_PER_PULSE * 2; // how far "late" an event may arrive and still be accepted in-order

  submit(agentId: AgentId, event: IRSwmidiEvent) {
    // 1. type-check against the *live* type environment (agent registered? channel owned?)
    // 2. buffer briefly (lookaheadTicks) to allow near-simultaneous cross-agent events
    //    at the same tick to merge in a stable order, rather than being force-ordered
    //    by arrival time (arrival time is a network/scheduling artifact, not music).
    // 3. flush to ring buffer + all subscribers once its tick falls outside the
    //    reordering window.
  }
}
```

**Ordering policy — why tick-then-priority, not arrival time:**
Two agents landing on the *same* tick is not an edge case here, it's the point (README: "They meet on beat 1 — the relay bridge, the flow state, the resolution"). The merge key is therefore `(tick, channelPriority, sequenceWithinAgent)`, not wall-clock arrival — an agent whose message happens to reach the bus 4ms later than another's shouldn't be re-ordered behind it if they both targeted the same pulse. This is a deliberate, small **logical-clock** discipline (each agent's own events are totally ordered by its local sequence counter; cross-agent ties break by static channel priority — reflex/ECN channels before creative/DMN channels, mirroring the README's "ECN fires... DMN fires... they meet on beat 1" framing) rather than a full CRDT — full conflict-free merge is overkill when the shared BeatClock already gives everyone the same tick numbering; the only real question is tie-breaking, not divergent histories.

**Lateness / friction:** an event arriving after its tick has already flushed past the lookahead window isn't dropped — it's tagged with `Friction.Timeout` in its `errorMask` and inserted at the *current* tick instead of its intended one. This reuses the existing `Friction` bitfield in `swmidi.js` exactly as designed: friction isn't an error channel bolted on the side, it's musical information ("this voice missed the pocket") that the jazz analyzer (section 8) can read as tension.

---

## 8. DAW renderer

The renderer (mixer board / chart overlay) should be a **pure function of the event bus**, not a stateful consumer that re-derives its own notion of time. Concretely, a pipeline of stream transformers, each subscribing to the prior stage:

```
JamSession bus (IRSwmidiEvent, tick-ordered)
   |
   +--> PulseGrid mapper        — bucket events into the 12-cell grid (README's pulse diagram)
   |
   +--> JazzAnalyzer            — windowed stream transformer:
   |       groove | building | tension | solo | comping | ballad
   |       (inputs: flowCount()/frictionCount() ratio per window, unique-channel
   |        activity, velocity variance — all already derivable from swmidi.js's
   |        isFlow/hasFriction helpers, just needs a sliding window over the bus
   |        instead of a one-shot batch call)
   |
   +--> MixerBoard view          — per-channel fader/meter state, driven by velocity
   |                                and NoteOn/NoteOff pairs on that channel
   |
   +--> ChartPlotter (Saxophone) — spatial trail: (channel, pitch) -> 2D position,
                                    unchanged from current design, just re-fed from
                                    the shared bus instead of its own capture path
```

Each stage is a small reducer: `(state, event) -> state'`. This is the important renderer-side decision — **today's `app.js`/`capture.js`/`analyzer.js` split likely has each concern independently re-deriving timing from raw messages; unifying them behind one typed IR stream means the analyzer, the mixer, and the chart plotter are provably looking at the same events in the same order**, which they are not guaranteed to be today if each maintains its own capture buffer.

Rendering itself (Canvas/DOM) stays a thin, replaceable layer on top of `MixerBoard`/`ChartPlotter` state — no change needed to `mixer.html`/`chart-overlay.html`'s actual drawing code, only to what feeds their state.

---

## 9. Compiler pipeline, end to end

```ts
function compile(source: string, mode: "file" | "live"): CompileResult {
  const preprocessed = expandMacros(source);           // section 3 — Pollen-style macro pass
  const tokens = lex(preprocessed);
  const ast = parse(tokens);                            // section 5
  const { typedAst, diagnostics } = typecheck(ast);      // section 4
  if (diagnostics.some(d => d.severity === "error")) {
    return { ok: false, diagnostics };
  }
  const irEvents = lower(typedAst);                      // section 6 — BarBeat -> PulseTick, EventNode -> IRSwmidiEvent[]
  irEvents.sort((a, b) => a.tick - b.tick);

  if (mode === "file") {
    return { ok: true, bytes: encodeStream(irEvents) };  // swmidi.js encodeStream, unchanged
  }
  // mode === "live": irEvents becomes the *replay seed* for a JamSession —
  // same IR, fed through JamSession.submit() at BeatClock-scheduled times
  // instead of written to disk. This is why offline and live share a compiler:
  // a .song file is just a pre-recorded, fully-ordered version of what a live
  // JamSession produces incrementally.
  return { ok: true, seed: irEvents };
}
```

---

## 10. Migration path from current `plainsong.py`

Incremental, not a rewrite:

1. **Fix the grid mismatch first** (highest value, smallest change): replace `beats_per_bar=4` / seconds-based `t_of` with the 12-pulse `resolveTick` from section 6. This alone makes `plainsong.py`'s output consistent with `engine.js` and the Rust core, which today it is not (a `.song` file authored against "beat 1-4" doesn't mean the same thing as the README's "pulse 1-12").
2. **Split `agents, events` into interleaved `DocNode[]`** (section 5) so prose stays positionally meaningful — low risk, mechanical change to `parse_plainsong`.
3. **Add the type checker as a separate pass** (section 4) that runs on the existing AST shape before touching codegen — turns today's silent `return []` swallowing into real diagnostics, no behavior change for well-formed files.
4. **Add `@define` macros** (section 3) — purely additive; files without `@define` are unaffected.
5. **Only then** build `JamSession` (section 7) and wire the renderer (section 8) to consume the same IR — this is the piece that actually requires new infrastructure (a running process holding the shared `BeatClock` and ring buffer), so it should land last, once the compiler front-end it depends on is stable.

---

## 11. Open questions

- **Macro hygiene**: should `@define` bodies capture the lexical scope of the call site or the definition site? (Scribble uses definition-site; I'd default to the same — predictable, and matches how `INSTRUMENT_MAP`/`PERCUSSION_MAP` are already global tables, not scoped.)
- **Cross-language IR sharing**: since `swmidi.js` is one of five polyformalism implementations (Rust/C/Zig/Python/CUDA per `POLYFORMALISM.md`), should the *typed AST* also get ported, or only the IR (which is already cross-language by construction, being 8 raw bytes)? I'd keep Plainsong-the-language JS/Python-only for now (authoring surface) and let the IR remain the only cross-language contract — matches the project's existing pattern of "one wire format, disagree on everything above it."
- **Live tie-break priority**: is channel-priority-by-ECN/DMN-role the right static ordering, or should it be dynamic (e.g. whichever agent is currently "soloing" per the analyzer wins ties)? Static is simpler and easier to reason about; dynamic is more true to jazz. Worth a second opinion from whoever's designing the analyzer's `solo` detection.
