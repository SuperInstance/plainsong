# PLAINSONG PERF — Performance-Annotation Layer

**Status: DRAFT SPECIFICATION. Nothing here is implemented.** Every fenced
block in this document is tagged ` ```plainsong-proposed ` because all of it is
proposed syntax. Per the house rule (AGENTS.md, *Do not invent the language*),
none of these blocks will compile until the spec ships; when it does, the
implementation must land behind a setting and default to no-change behaviour for
files that contain no perf blocks.

Written 2026-08-25; **revised same day to v0.2 after the cross-model seminar** (recursion → v2, the cue seam now consumed §8.4, one feature truth §9.5, drum-map rows + complement selectors §4.1/§4.3, fuzzy-rebase budget §4.2, Q5/Q8 closed §17 — full ledger: `plainsong-mcp/docs/seminar-response.md`).

Source directive (Casey, verbatim intent):

> "we need ways to annotate everything about a player's performance — full MIDI
> performance notes, velocity AND modulation in more than one dimension, pedals,
> etc. — a tensor of dimensions for every note beyond pitch and timing. A
> turing-complete acoustic coding language that doesn't limit variables, but
> leaves room for emergent new variables, categories and connections — just like
> our fabric and quilt projects."

Design constraints from Lucineer are incorporated and, in four places, refined
with disagreements flagged inline and summarised in
[§16 Disagreements with the brief](#16-disagreements-with-the-brief).

---

## 1. Why this exists

Plainsong's grid answers *what is played*: voice, onset, pitch, duration. It
says almost nothing about *how*. Real performance is a tensor — velocity,
pedal state, bow pressure, breath, stage position, mood — and most of those
dimensions move *continuously* while the note sounds. MIDI has the channels for
this (CC, pitch bend, aftertouch, sysex) but no notation that makes them
writable as music rather than as producer trivia.

PERF turns the grid into the **address space** of an open, turing-complete
annotation language:

- The lead sheet stays a lead sheet. A musician can still read it at a glance.
- Every note carries an **open key–value tensor** — known keys compile to MIDI
  streams today; unknown keys are first-class semantic data, queryable now and
  renderable by renderers that do not exist yet.
- Expressions are **pure functions of time and state**, sandboxed by
  construction, turing-complete within a fuel budget.
- Voices **link** to each other through declared, read-only contracts, so a
  score becomes a small dependency graph — the quilt move. Cells, dependencies,
  strata: the score becomes a reactive sheet evaluated at compile time.

This is the river principle made notational: the system does not record a
performance, it *creates the conditions under which a performance can be
specified, linked, and re-heard* — and it leaves room for dimensions nobody has
named yet.

### Lineage

| Idea | From |
|---|---|
| Everything is a cell; open kinds; reactive graph | quilt (L3 core model) |
| Voices as owned cells, links as declared contracts, async iteration | plainsong-mcp ensemble + the agent-ensemble pattern |
| Conditions, not compositions; emergence over templates | docs/proposals/00-FOUNDING-PHILOSOPHY.md |
| Written times are arrivals; emission is solved backwards | docs/performance.md (`[Stage]`) |
| 16 numbers per bar as a voice's perceivable state | `analyze_features` (plainsong-mcp) |
| Conductor directives as macro input streams | `plainsong.perform.conduct` / fleet-jepa-midi vocabulary |

---

## 2. The ten-minute version

A piano lead sheet stays exactly as it is. Performance lives in a `[Perf]`
section (or a sidecar file, §5):

```plainsong-proposed
**TRACK: Last Ferry Home**
[MetaData]
key: Am | tempo: 96 | time: 4/4

[V1] (Verse - 4 Bars)
Chords: | Am . . . | F . . . | C . . . | G . . . |
Melody: | A4 . C5 E5 | F4 . A4 C5 | E4 . G4 C5 | D4 . F4 B4 |
@piano  | a2-e3 . c4-e4 | f2-a3 . c4-f4 | c3-e3 . b3-d4 | b2-d3 . a3-d4 |

[Perf]
!version 1
!voice @piano

# una corda for the whole verse; half-pedal breathing with the bars
V1:* @piano *   ped.soft: 1
V1:* @piano *   ped.sust: = 0.9 - 0.4 * frac($T / 4)

# melody notes get the ache; comping stays glassy
V1:* @piano Melody   vel: = 64 + 18 * ($beat == 1)
                    bright: = 0.3 + 0.4 * $vel / 127
                    ache: 0.8
```

Read the annotation lines as: *at this address, these dimensions have these
values or curves*. `ped.sust` is a full-down-to-half-pedal sawtooth synced to
the bar. `vel` is an expression evaluated at onset. `ache` is nothing the
compiler has ever heard of — it is stored, queried, and published anyway.

Everything else in this document is that idea made precise.

---

## 3. The model of a note: an open tensor

**Definition.** After arrangement, every note event is

```
note := (voice, onset, pitch, duration) ⊕ attrs
attrs := { key → value }        # open dictionary
```

`attrs` is unordered, open, and append-only in spirit: any dotted lowercase
name is a legal key. The compiler partitions keys into three bands:

1. **Physical keys** — known MIDI mappings (§9.2). `vel`, `mod`, `bright`,
   `pb`, `touch`, `ped.sust`, `cc74`, `sysex`, `prog`, …
2. **Semantic keys** — everything else. `ache`, `brush.tight`,
   `emotion.valence`, `stage.pan`. First-class data: stored in the tensor
   artifact, published to listeners, queryable, and never silently dropped.
3. **Meta keys** — annotations about annotations: `fallback`, `blend`, `unit`,
   `publish`, `comment`. Reserved, prefixed syntax (§7.4).

A key becomes a category by being used. The **category ledger** (§10.2)
records every distinct key with provenance: first file, first author, unit if
declared, use count. New categories emerge by naming them — no schema change,
no compiler release. This is the quilt cell doctrine applied to performance:
*the schema is the set of names that have been used, plus the ones that will
be.*

Values (§7) are scalars with optional units, strings, tags, breakpoint curves,
or expressions. Because expressions are functions of time, an attribute is not
a number but a **stream**: a value per control-tick while its anchor is active.
Velocity is the one degenerate case — an onset scalar (an expression applied to
`vel` is evaluated at the note's onset tick only).

---

## 4. Addressing: anchors

Annotations must point at notes precisely, readably, and *survive edits to the
score* — a rebase, not a break.

### 4.1 Anchor grammar

```
anchor      := scope? locus voice target? where-cl?
scope       := IDENT ":"                       # section name: "V1:"
locus       := "*" | span
span        := barloc ( "-" barloc | "+" INT )?
barloc      := INT "." ( INT | "*" )           # bar.beat, 1-based; beat may be "*"
voice       := "@" word | rowkind | "*"
rowkind     := "Melody" | "Chords" | "Lyrics"  # labelled rows are addressable
target      := ( pitchset | complement )? ( "#" INT )? role?
pitchset    := pitch ( "-" pitch )*
complement  := "*" "-" ( rowkind | pitchset )     # * - Melody: what the row does NOT cover
role        := "." ( "first" | "last" | "min" | "max" | "loud" | "long" | "downbeat" )
             | "." instrument                    # .ride .kick — drum-map roles (§4.3)
where-cl    := "where" expr
```

Examples:

| Anchor | Means |
|---|---|
| `V1:3.2 @bass g2` | the `g2` nearest beat 2 of bar 3 in section V1, voice `@bass` |
| `3.1-3.4 @strings *` | every note of `@strings` from bar 3 beat 1 through beat 4 (inclusive span) |
| `2.1+8 @piano *` | 8 beats starting at bar 2 beat 1 |
| `@bass g2#3` | the third `g2` in `@bass` anywhere in the piece |
| `V1:* @piano Melody` | all melody-row notes in V1 (melody is a voice like any other) |
| `@drums ride .last` | the final ride hit, by instrument role from the parseable drum-map row (§4.3) |
| `V1:* @piano * - Melody` | **complement selector**: every piano note the melody row does not own |
| `@piano * where $dur >= 2` | every piano note held two beats or longer |

Snap rule: a `bar.beat` snaps to the nearest onset in that voice inside that
bar (tolerance: half a subdivision slot — a bar's tokens divide it, so onsets
sit at k/n positions; §notation). If the voice has no onset in that bar, the
anchor is a fuzzy candidate (§4.2). Pitch match is case-insensitive scientific
notation. A pitch set (`a2-e3`) selects stacked-chord members. **Complement
selectors** resolve to the voice's own notes minus the named row/pitch-set — the
compiler already knows the difference; nobody should enumerate eleven chord
tones to mean "everything that isn't the melody" (seminar A3). Predicates in
`where` use the expression language over onset-time context.

### 4.2 Re-versioning: the anchor ledger and rebase

Hand-written anchors stay short and human. **Signatures are the compiler's
job.** On first successful compile, every anchored annotation is recorded in
the anchor ledger (stored in the perf sidecar, §5.3) with a resolve signature:

```
sig := (section, bar, beat, voice, pitch, prev_pitch, next_pitch, ordinal_in_voice)
```

When the score later changes, `plainsong perf rebase` replays annotations onto
the new arrangement in tiers, like a git rebase:

1. **Exact** — signature matches outright.
2. **Context** — same section, voice, pitch, and neighbour pitches; bar within
   ±4. Accept, record `Δbars` in the diagnostic.
3. **Fuzzy** — same voice and pitch, nearest onset within ±8 bars; neighbours
   ignored. Accept with a warning — **but fuzzy has a budget** (seminar S-P1):
   default cap 5 reattachments or 15% of the file's annotations, whichever is
   smaller. Past the cap, rebase **halts**: remaining fuzzy candidates are parked
   like orphans and listed for confirmation. Warnings normalized into noise is a
   failure this project has already paid for once; the cap is the tripwire.
4. **Orphaned** — no candidate. The annotation is **parked, never dropped**:
   kept in the file, listed in diagnostics, and excluded from compilation
   until a human or agent re-anchors it. (House rule: a silently dropped
   melody is worse than a warning; so is a silently dropped pedal curve.)

Transposition-aware: `plainsong transpose` rewrites pitches, so rebase maps
ledger pitches by the same interval before matching — annotations follow the
music into the new key.

Ambiguity (two candidates equidistant) parks the annotation and names both
candidates. Rebase is idempotent: running it twice changes nothing the second
time (property-tested, §14).

### 4.3 Drum maps: parseable rows, not comments

The evidence's drum map lives in a *comment* (`# kick=c1 brush-snare=d2 ride=a3`)
— convention, not data; one rename away from silently re-binding every drum
annotation (seminar A3). In perf, a drum map is a **parseable row**:

```plainsong-proposed
@drums: kick=c1 brush-snare=d2 ride=a3
```

The row declares instrument roles for the voice; anchors may target them
(`@drums ride .last`, `CH:* @drums kick vel: 64`), and the ledger records the
map as part of the file. A raw pitch annotation (`@drums a3`) still works and
resolves through the map — the alias is data now, not folklore.

---

## 5. Where perf lives

One grammar, three containers. All of them are line-oriented text that diffs
cleanly; none of them touch the lead-sheet rows.

### 5.1 `[Perf]` sections (in-file, human scale)

A `[Perf]` section inside a `.song` file is read, not played — the same
contract as `[Stage]`. Meant for annotations a human wants to see *next to the
music*: pedal scenes, one-line velocity rules, tags. **Guideline with teeth:**
`plainsong check` emits an info diagnostic when a `[Perf]` section exceeds 40
lines or 25% of the file — past that, the right home is a sidecar. The grid
stays readable (Lucineer constraint 1); this is the enforcement mechanism.

### 5.2 Sidecar files (`.perf.md`, machine and ensemble scale)

A piece `last-ferry.song` may name a companion `last-ferry.perf.md`:

```
last-ferry.song
last-ferry.perf.md
```

…linked from the score's `[MetaData]` with `perf: last-ferry.perf.md`, or
passed on the command line (`plainsong compile --perf …`). The sidecar is
markdown whose fenced ` ```plainsong-perf ` blocks are perf language; prose
around them is the *performance notes a player would actually write* — "brushes
tighten when the bass gets anxious; let the last chorus fall apart" — and it
diffs as cleanly as code. CI compiles fenced blocks in markdown already
(`plainsong check docs`); perf blocks join that contract behind the setting.

### 5.3 The sidecar's sidecar (generated, never hand-edited)

```
last-ferry.perf.md
last-ferry.anchors.json     # anchor ledger: signatures, rebase results (generated)
last-ferry.tensor.jsonl     # the resolved tensor artifact (generated, §10.1)
```

Ensemble sessions follow their own layout (§11.8): perf parts live beside
voice parts, `parts/bass.perf`, owned exactly like `parts/bass.song`.

---

## 6. The perf language, by line

```
perf-file   := { directive | definition | fn-def | listen | publish | suggest | annotation | comment | blank }
directive   := "!" word ( value )?                 # !version 1  !voice @piano  !rate 96  !fuel 10000
                                             #   !epochs 3  !bendrange 24  !embed meta
definition  := IDENT "=" expr                      # let-style, pure
fn-def      := "fn" IDENT "(" params ")" "=" expr  # recursion allowed (self-visible)
listen      := "listen" refpath "as" IDENT ( "react" )?
refpath     := voice "." stream                     # "@bass.features.tension" | "@piano.drive"
publish     := "publish" key ( "as" IDENT )?
suggest     := "suggest" anchor key ":" value string?   # routed to the log, never applied (§8.3)
annotation  := anchor { key ":" value }+
comment     := "#" text
```

`!voice @piano` sets a default voice so subsequent anchors may omit it.
Definitions and functions are pure and file-scoped. Directives are per-file;
sidecar and `[Perf]` section merge (section first, sidecar second; collisions
on the same (voice,key) follow §9.4).

---

## 7. Values and the expression language

### 7.1 Value grammar

```
value       := scalar | list | breakpoints | expr-lit
scalar      := NUMBER unit? | STRING | "#" word            # 88 | 0.6 | 90ms | 0.3st | "smoky" | #dark
unit        := "ms" | "s" | "st" | "dB" | "hz" | "raw"
list        := "[" expr ("," expr)* "]"
breakpoints := shape? "{" point ("," point)* "}"           # time -> value
shape       := "smooth" | "step" | "loop"                  # default: linear
point       := expr "->" expr
expr-lit    := "=" expr
```

Units are documentation plus coercion: `0.3st` into `pb` is semitones; `90ms`
as a breakpoint key is note-local seconds; `raw 64` into `ccN` is the raw 7-bit
integer where the canonical form is 0..1. Coercion mismatches (a `st` value
into `vel`) are errors, not warnings.

### 7.2 Expression grammar (PEx)

```
expr    := "fn" "(" params ")" "->" expr                  # anonymous
         | "let" IDENT "=" expr "in" expr
         | "if" expr "then" expr "else" expr
         | expr bop expr                                   # + - * / % ^ and or == != < <= > >=
         | "not" expr | "-" expr
         | call | atom
call    := IDENT "(" expr ("," expr)* ")"
atom    := NUMBER unit? | STRING | context | IDENT | prev | "(" expr ")"
context := "$" word ( "." word )*                          # $t $vel $prev.pitch $conduct.energy
prev    := "prev" "(" key ")"                              # own stream, one tick back
```

Precedence is conventional; `if/then/else`, `let`, and `fn` extend to the end
of their bodies. **v1 is first-order (seminar A1): no recursion.** Named `fn`
bodies may not reference themselves (enforced at parse); PEx ships as a
Lustre-class synchronous-dataflow language, which is what every worked example
already is. Recursion — and the fuel apparatus it drags in — is deferred to
**v2**, admitted only when a real perf file demonstrates a need the category
ledger can point at. Turing-completeness remains the brief's ambition; it is a
v2 door, not a v1 debt.

### 7.3 Context variables

| Var | Meaning |
|---|---|
| `$t`, `$ts` | time since the anchor's onset — beats / seconds |
| `$dur`, `$durs` | the anchored note's (or span's) duration — beats / seconds |
| `$T`, `$Ts` | global time — beats / seconds, tempo-map aware |
| `$bar`, `$beat` | current bar (int) and beat-in-bar (float) at evaluation time |
| `$pitch`, `$vel`, `$onset`, `$voice` | the anchored note's MIDI number, pre-perf baseline velocity, onset, voice name |
| `$prev.pitch` `$prev.onset` `$prev.vel` `$gap` | previous note in the same voice; silence gap in beats |
| `$key.tonic`, `$key.mode`, `$tempo` | header context |
| `$conduct.energy` `$conduct.tension` `$conduct.last` | live conductor-directive streams (fleet-jepa vocabulary) |
| `$cue.kind` `$cue.payload` `$cue.wants.*` `$cue.keep_empty` | live **ensemble cue context** (§8.4): published per cue fire when the target includes this voice; `keep_empty` lists the spans the cue asks to leave silent |
| `$feat.*` | this voice's own feature tensor (16 per bar), when perf is compiled in a context that has run `analyze_features` |

`$vel` is always the **pre-perf baseline** (row `vel:` options included), so
`vel: = 1.1 * $vel` means "10% over what the sheet says" — the sheet stays
authoritative for the base, perf is the interpretation on top.

### 7.4 Builtins

Math: `sin cos tan sqrt exp log log2 abs sign floor ceil round min max clamp
lerp quantize frac`. Time/shape: `step smoothstep pulse env glide lag(tau)
integ(x, reset?) diff hold once count rising falling barspan`. The envelope
is a call: `env(attack, decay, sustain, release, t)` with `t` the progress
argument. Deterministic noise: `hash(n)` (integer hash → 0..1), `noise(
seed )` and `noise2(seed, x)` (value-noise interpolation of `hash` — the only
"randomness" in the language, fully seeded). Conversions: `sec beats bpm`.

Meta-keys on annotation lines: `fallback:` (value used if the expression
errors or exhausts fuel), `blend:` (`replace` default | `add` | `max` |
`min`), `unit:` (declare a semantic key's unit for the ledger), `publish`.

### 7.5 The sandbox statement

PEx is **safe by construction — first-order in v1, with structural termination**:

- **Pure.** No I/O, no imports, no wall clock, no network, no host calls — the
  grammar has nowhere to write them. The only nondeterminism would be user
  error, and there is no unseeded random to be wrong with.
- **Deterministic.** Same file, same bytes out. Evaluation order is total:
  voices alphabetical, keys sorted, streams in topological order (§8.2).
  `prev(k)` is the only self-reference and costs exactly one tick of delay.
- **Bounded, structurally (v1).** With recursion deferred (§7.2), termination is
  structural: bounded grammar, total builtins, no self-reference. A compile-wide
  evaluation budget remains as a safety net against pathological data shapes
  (huge breakpoint lists, adversarial spans); **tripping it is a compile error** —
  the compile fails loudly and the file is rewritten (seminar S-P4: an open
  question is not a mitigation; with recursion gone there is no honest case for
  silent neutral). `fallback:` still covers per-tick *domain* errors (NaN,
  out-of-range) inside an otherwise-sound compile — those are warned and tallied
  per key, never silent.
- **Streaming memory.** Evaluation is per-tick over a bounded window; ring
  buffers for `prev`/`lag`/`integ` are capped (`integ` has an overflow guard
  and a `reset` argument). Memory is O(active streams), never O(corpus) —
  the fleet's critical-path rule, inherited.

Bit-exactness across platforms is qualified: `sin` et al. come from libm,
which may differ in the last ulp between platforms. The fingerprint therefore
hashes **output-space quantised streams** (7-bit CC values, 14-bit bend), where
a 1e-15 difference almost never flips a bit — and `perf.libm = "builtin"`
selects table-driven implementations for provable bit-exactness when it
matters (§17, open question 1).

---

## 8. Connections between voices

The quilt move. A score under PERF is a **graph of published streams with
declared, read-only dependencies**, evaluated in strata at compile time. It is
quilt's reactive sheet — but build-time and deterministic, not a live runtime
(disagreement 4, §16).

### 8.1 What a voice publishes

By default a voice publishes:

- its **feature tensor** — the 16 per-bar numbers `analyze_features` already
  produces (`tension`, `density`, `register`, `syncopation`, `dynamics`, …),
  held/interpolated across the bar;
- every key explicitly `publish`ed: `publish vel as drive`.

Written score events are readable as context (`$prev`, `$feat`) but *not*
cross-voice: another voice's notes are reachable only through what that voice
publishes. This keeps the contract surface explicit and small.

### 8.2 `listen` edges and strata

```
listen @bass.features.tension as T       # read edge: this compile's value
listen @bass.features.tension as T2 react # react edge: previous stratum's value
```

- **read edges** must form a DAG. A cycle is a compile error that prints the
  cycle and suggests marking one edge `react`.
- **react edges** read the previous evaluation stratum — "the musician hears
  the last pass." Strata run until all react edges have a value, at most
  `!epochs` (default 3). This gives cycles a deterministic, musical
  resolution: not a fixpoint solver, a *conversation with one verse of lag*.

This mirrors the ensemble protocol exactly: each agent owns a voice, links are
declared contracts, and iteration is asynchronous. `react` is the notation's
memory of the band's second take.

### 8.3 Ownership: suggestions, never writes

In an ensemble session, perf annotations are owned by the target voice's owner
— the drummer writes `@drums` perf, nobody else. Want to change another
player's performance? Write a suggestion:

```
suggest @piano V1:2.3 vel: 92 "brighter on the turn"
```

Suggestions are routed to the change log (`record_decision`) verbatim, exactly
like the producer-relayed asks in the agent-ensemble pattern. One concrete ask
per iteration survives as the protocol rule; the notation now carries it.

### 8.4 The cue seam: consuming the engine's `intent_directive`

The ensemble engine's cue schema emits an `intent_directive` (`wants:
{feature, dir, window}`, `keep_empty: ["9.2-9.4"]`). Perf is its consumer — the
handshake now has a hand (seminar A2):

- **`$cue.*` context.** When a cue fires whose target includes this voice, the
  engine publishes the directive into the compile context; expressions read
  `$cue.kind`, `$cue.payload`, `$cue.wants.feature/dir/window`, `$cue.keep_empty`.
- **`keep_empty` compiles to a rest overlay.** At fold time (§9.1 step 7), notes
  whose onsets fall inside a keep-empty span are dropped, and the drop is
  recorded in the tensor as `cut_by: <cue_id>` — the silence is attributable,
  never ambient.
- **`wants` is advisory context, not a solver.** Expressions may shape streams on
  `$cue.wants.dir`; the engine's referee (ADJUDICATE) then scores whether the
  features moved as wanted — on the post-perf trace (§9.5). Wanting is the
  engine's job; becoming is the perf file's.
- **No engine, no cue.** Compiling outside a session, `$cue.*` is unbound;
  referencing it is an unmet-contract warning — the same grammar for absence as
  `listen` (§11.2).

```plainsong-proposed
!voice @drums
# cushion the landing the bandleader cued, then leave the asked-for space
V1:8-9 @drums *   vel: = if $cue.kind == "landing" then 44 + 12 * rising($T) else $vel
                  # keep_empty spans ("9.2-9.4") are folded by the compiler as the rest overlay
```

---

## 9. Compilation

### 9.1 Resolution order (the pipeline)

```
 1. parse score ──────────────► arrangement (unchanged plainsong pipeline)
 2. parse perf (sections + sidecars)
 3. merge & validate keys/units/directives
 4. resolve anchors ─────────► (exact → context → fuzzy → parked), update ledger
 5. build graph: voices × keys, listen edges, prev edges
    └─ cycle check; stratum assignment (read = DAG topo; react = +1 stratum)
 6. evaluate streams per stratum, per tick (fuel-bounded, deterministic)
 7. fold streams into note events ──► physical keys to MIDI lanes,
                                      semantic keys to the tensor artifact
 8. stage pass (existing [Stage] solver) ──► emission times for events
 9. diagnostics; fingerprint (perf namespace); optional meta embed
```

Steps 1 and 8 are the existing compiler, untouched. Perf slots in between, and
a file with no perf blocks never enters steps 2–7 — zero change, byte-for-byte,
which is what keeps this additive rather than breaking.

### 9.2 Physical key → MIDI mapping (today)

| Key | Range | MIDI |
|---|---|---|
| `vel` | 1–127 (onset scalar) | note-on velocity |
| `mod` `breath` `expr` `bright` `pan` `port` | 0..1 | CC 1 / 2 / 11 / 74 / 10 / 65 |
| `ped.sust` `ped.sost` `ped.soft` | 0..1 | CC 64 / 66 / 67 — fractional values are half-pedal (0.5 ≈ 64); `ped.soft` = una corda |
| `touch` | 0..1 | channel pressure; poly aftertouch per note when the target declares support (§13 fallback) |
| `pb` | ±`!bendrange` st (default 2) | pitch wheel, 14-bit; RPN 0 sets range when `!bendrange` ≠ 2 |
| `ccN` | 0..1 (or `raw` int) | arbitrary controller |
| `prog` | int | program change (respects existing `inst:` guessing unless overridden) |
| `sysex` | hex string | raw bytes; `sysex_roland(addr, data)` computes Roland checksums |

Curves sampled on the control grid (`!rate`, default 96 Hz, quantised to MIDI
ticks). Bandwidth policy: emit on ≥1 LSB change (7-bit keys) / ≥2 LSB (bend),
plus a per-second event budget per voice (default 300); over budget thins by
minimum-audible-delta and warns. Streams are **note-local by default**: a
note-anchored stream emits only while its note sounds, then the lane returns
to neutral. Span-anchored streams hold across the span.

### 9.3 `[Stage]` interplay

Streams are defined on the **written (arrival) timeline**. The existing stage
solver shifts each voice's emissions by its constant per-voice correction, so
CC and bend events move with the track they belong to — curves keep their
phase relative to the notes they interpret. No new solver semantics; one test
asserts a `[Stage]` file's curve-to-note offset is invariant under
compensation on and off.

### 9.4 Collision policy

One writer per (voice, physical key). A second annotation writing the same
key is an error unless one declares `blend: add|max|min` (combinable streams)
or the later line explicitly `blend: replace`s within a smaller span. Two
`blend: add` curves both writing `cc74` is legal and additive — this is how a
section writes "registration plus vibrato".

### 9.5 One feature truth: features are post-perf

Once perf exists there are two possible feature worlds — pre-perf (the
arrangement as written) and post-perf (what the room hears). This spec picks
one, once (seminar A4 + Turbo 4): **features are computed on the post-perf
arrangement wherever perf is present.** Concretely: in ensemble sessions, perf
compiles at **commit time** — each `perf_write_part` lands compiled, so the
engine's referee (ADJUDICATE), its `features_moved` verification, and SIMULATE
all score the same music the renderer plays. In live rooms (yard-band), players
commit bar events with attrs already folded; the realizer applies cue transforms
at freeze and never re-runs this compiler. "POCKET LOCKED" refers to the room,
not the map.

---

## 10. The semantic layer

### 10.1 Artifacts

- **`name.tensor.jsonl`** — one record per (note, key) at onset (scalars) plus
  stream records (sampled or breakpoint-compressed) for curves. This is the
  open tensor, materialised.
- **MIDI meta embed** (`!embed meta`) — each note's semantic attrs serialised
  into a text meta event beside it. DAWs ignore it; future tools read the
  performance out of the MIDI file itself. Off by default (file bloat, §13).
- **Streams view** — `plainsong perf streams` prints the resolved graph:
  voice, key, anchor, stratum, event counts, fuel used.

### 10.2 The category ledger

```bash
$ plainsong perf categories last-ferry.perf.md
key            first seen                     author            uses  unit
ache           V1:2.3 @piano (last-ferry)     pianist-turbo        6  0..1 (declared)
brush.tight    CH:* @drums  (last-ferry)      drummer-glm          9  0..1 (inferred)
emotion.val    V1:* @vocal  (last-ferry)      vocalist-glm52      14  —
```

Provenance comes from the ensemble log when present, else the file. The ledger
is how an emergent category becomes a *shared* one: the second agent to use
`ache` finds it in the ledger with its unit and history — onboarding through
retrieval, not re-living.

**Meaning drift is versioned, never overwritten (seminar S-P2).** Provenance
says who started a category, not whether it still means what it meant. When a
key's *interpretation* changes (a renderer maps `stage.dist` to a panner; `ache`
goes from private feeling to fleet standard), the ledger appends a
`meaning_version` row — `ache v1 (0..1, "private ache") → v2 (0..1, "audible
longing")` — with per-version first-seen provenance. Files compile under the
meaning version current at their compile; renderers pin a version. Semantic
drift becomes a visible break instead of a quiet one.

### 10.3 Queries

```bash
plainsong perf query 'ache > 0.7 and voice = "@piano"' last-ferry
plainsong perf query 'key = "brush.tight" and value > 0.5 and $bar >= 9'
```

Query predicates are PEx over tensor records. This is the surface a future
renderer — a lighting desk, a live-visuals engine, fleet-twin's memory —
subscribes to.

---

## 11. Worked examples

All blocks ` ```plainsong-proposed `.

### 11.1 Smoky piano: half-pedal, una corda, and the ache

```plainsong-proposed
[Perf]
!version 1
!voice @piano

# una corda down for the whole solo
V1:* @piano *   ped.soft: 1

# full pedal on each downbeat, easing to half by the barline: a breathing legato
V1:* @piano *   ped.sust: = 0.9 - 0.4 * frac($T / 4)

# melody: sing it; comping: glass.  ache is not a MIDI word — it persists anyway.
V1:* @piano Melody   vel: = 64 + 18 * ($beat == 1) + 6 * hash($onset)
                     bright: = 0.25 + 0.5 * $vel / 127
                     ache: 0.8
                     unit ache = 0..1
                     publish ache
V1:* @piano * - Melody   vel: = 46 + 6 * hash($onset)
                         bright: 0.3
```

The comping line uses a **complement selector** (§4.1): everything the piano
plays that the melody row does not own. Under the collision policy (§9.4) the
two writers own disjoint targets with no conflict — and nobody hand-enumerates
eleven pitches to mean "the rest of the row" (seminar A3); the compiler already
knows.

Note `hash($onset)` — deterministic per-note "human error" in the velocity,
seeded by the onset, so the same file swings identically forever.

### 11.2 The drummer whose brushes tighten as the bass tension rises

```plainsong-proposed
[Perf]
!version 1
listen @bass.features.tension as T
!voice @drums

@drums: kick=c1 brush-snare=d2 ride=a3      # parseable drum-map row (§4.3)

CH:* @drums *            brush.tight: = clamp(T($T) * 1.2, 0, 1)
                         publish brush.tight
CH:* @drums ride         vel: = 52 + 30 * T($T)
CH:* @drums brush-snare  vel: = 48 + 26 * T($T) * (1 - 0.5 * ($beat == 3))
```

If `@bass` is absent or publishes nothing, the diagnostic is an **unmet
contract** — named, not fatal: `listen @bass.features.tension: no such
published stream; stream held neutral` — and the drummer still plays.

### 11.3 A singer's portamento map

```plainsong-proposed
[Perf]
!version 1
!voice @vocal
!bendrange 12          # a singer glides whole octaves; RPN 0 is set accordingly

V1:* @vocal *   port: 1
                pb: = ($prev.pitch - $pitch)
                       * (1 - smoothstep(0, 0.12, $ts))
                       * ($gap < 0.25)
                touch: = 0.3 + 0.4 * env(0.05, 0.3, 0.8, 0.4, $t / $dur)
```

Each note begins at the previous note's pitch — `pb` starts one semitone-gap
wide and glides home over 120 ms — but only when the notes are
near-contiguous (`$gap < 0.25`): leaps across silence are clean re-attacks,
which is what singers actually do.

### 11.4 Vibrato that grows with the note and the dynamic (strings)

```plainsong-proposed
[Perf]
!voice @strings

fn vib_depth(vel, age) =
  (0.15 + 0.25 * vel / 127) * (1 - exp(-age / 0.6))

V1:* @strings *   pb: = 0.35 * vib_depth($vel, $ts)
                        * sin(2 * pi * $ts * (5.2 + 0.8 * $vel / 127))
                  touch: = 0.2 + 0.5 * vib_depth($vel, $ts)
                  publish touch as warmth
```

Depth and rate both scale with written dynamics and note age: a soft entry
blooms late, a forte note shivers early. `warmth` is published for whoever
wants to listen to it.

### 11.5 Emergent category, first use to shared vocabulary

Session one, the pianist invents `ache` (11.1) — and `publish`es it, which is
why it is audible at all: only features and published keys cross voices
(§8.1). Session two, the violinist reads the ledger, adopts it, and links to
it:

```plainsong-proposed
listen @piano.ache as A
!voice @strings

V1:* @strings *   ache: = 0.6 + 0.3 * A($T)
                  stage.dist: = 1 + A($T)
```

Nobody released a compiler in between. The category ledger is the only
coordination point, and it is generated. `stage.dist` has no MIDI mapping
today; the tensor carries it, and the day a spatial renderer exists, every old
file already speaks it.

### 11.6 Organ registration that swells (multi-dimensional drawbars)

```plainsong-proposed
!voice @organ

CH:1.1-CH:4.4 @organ *   cc16: = 0.8                       # 16' drawbar
                        cc17: = 0.4 + 0.4 * ($T / 16)      # 8'  opens across the chorus
                        cc18: = 0.2 + 0.3 * sin($T / 2)
                        cc19: = 0.1
                        prog: 19
                        sysex: "F0 41 10 42 12 40 00 41 55 F7"
```

Four controller lanes plus a program change plus one literal sysex —
registration as a *time-varying tensor*, not a setting.

### 11.7 Conductor directives as input streams

The fleet-jepa bandleader's JSON already drives `plainsong.perform.conduct`.
PERF expressions can read the same macro state, so notation and conductor
agree on one vocabulary:

```plainsong-proposed
!voice @drums
CH:* @drums *   vel: = 1.0 + 0.3 * $conduct.energy
                brush.tight: = clamp($conduct.tension, 0, 1)
                # the conductor's last word, as a published stream for whoever
                # reacts to narrative
                cue: = $conduct.last
                publish cue
```

### 11.8 Ensemble session: contracts, ownership, rebase

```
<workspace>/ensemble/last-ferry/
    manifest.json
    parts/bass.song     parts/bass.perf
    parts/drums.song    parts/drums.perf
    score.song          (generated)
    log.jsonl
```

The drummer's perf part (ownership = the voice, `base_version` = the part's,
identical to `write_part`; a stale write is refused and handed current state):

```jsonc
{"name": "perf_write_part", "arguments": {
  "session": "last-ferry", "voice": "@drums", "agent": "drummer-glm",
  "base_version": 7,
  "content": "[Perf]\nlisten @bass.features.tension as T\nCH:* @drums a3  vel: = 52 + 30 * T($T)",
  "summary": "ride tightens with bass tension — that's the one ask"}}
// -> isError: base_version 7 ≠ 9.  Refused with current part to rebase, exactly
//    like a part write. The drummer rebases and lands at version 10.
//
// perf_write_part runs the perf compiler server-side at COMMIT (§9.5): a part
// that does not compile is refused with diagnostics — so every part in the
// session carries post-perf features by the time the referee reads it.
```

And the piano's request to the drummer rides the log as a suggestion (§8.3),
relayed verbatim — one concrete ask per iteration, still the rule.

### 11.9 The score changed under the annotations: rebase in action

A bar is inserted before bar 9. `plainsong perf rebase last-ferry`:

```
annotations   52
reattached-exact   44
reattached-context  6   (V1:9.2 @bass g1 -> V1:10.2, Δbar +1 … 6 lines)
reattached-fuzzy    1   (V1:12.3 @bass e2 -> V1:13.3, Δbar +1, neighbours changed)
orphaned            1   (V1:14.1 @horns e4 — no e4 within ±8 bars; parked, listed)
ledger updated      last-ferry.anchors.json
```

Nothing was dropped. The one orphan is visible in `check` until someone
re-anchors it — the same contract the parser gives a melody it cannot read.

---

## 12. Compiler architecture

```
plainsong/
  perf/
    parse.py        perf line grammar → raw AST (annotations, defs, edges)
    anchors.py      anchor resolution, snap rule, ledger read/write, rebase
    pex.py          expression parser + evaluator (fuel-metered, pure)
    graph.py        voice×key nodes, prev edges, listen edges, strata, cycles
    streams.py      tick-grid evaluation, thinning, event budget
    emit.py         physical keys → MIDI lanes; merge with existing writer
    tensor.py       semantic keys → jsonl artifact, category ledger
    queries.py      perf query / categories / streams
```

The evaluator is a synchronous-dataflow interpreter (Lustre lineage): every
key is a stream, every expression a stream function, `prev` is the unit delay,
and fuel is checked per sample. That shape is what makes determinism, cycle
detection, and O(active-streams) memory all fall out of one design instead of
being three patches. The whole package imports nothing outside the standard
library — the house rule, kept.

### Guarantees the implementation is tested against

1. A file with no perf blocks compiles to **byte-identical** output (MIDI and
   audio) with perf support on or off.
2. Compile twice → identical artifacts (hash equality, §14).
3. Rebase is idempotent; rebase after transpose re-anchors by interval.
4. Fuel exhaustion never hangs: bounded by construction, diagnosed per key.
5. Every diagnostic is one of error/warning/info, joined to the existing
   `check` surface and `--json` shape.

---

## 13. Failure modes

| Failure | Behaviour |
|---|---|
| Anchor orphaned by score edit | Parked (kept, uncompiled), listed in `check`, never dropped |
| Two rebase candidates equidistant | Parked with both candidates named |
| `listen` names an unpublished stream | Warning: **unmet contract**; stream held neutral |
| Cycle without `react` | Error; prints the cycle; suggests marking an edge `react` |
| Fuel exhaustion | Error for that key; `fallback:` value or neutral emitted for the span; rest of piece compiles |
| Second writer on a (voice, key) | Error unless `blend:` declared |
| Unit coercion mismatch (`st` into `vel`) | Error at validation, before evaluation |
| Event budget exceeded | Thin by minimum audible delta; warning with the count |
| NaN / division by zero | That tick emits neutral; warning with a per-key tally |
| Poly aftertouch on an unsupported target | Fallback to channel pressure; info diagnostic |
| `!embed meta` bloat | Hard cap (64 KB/event, 2 MB/file); over → embed off + warning |
| Cross-platform hash mismatch on re-verify | Error with quantised-stream diff; suggests `perf.libm = "builtin"` |

---

## 14. Testing and the determinism harness

- **Golden streams**: hand-computed CC/bend sequences for every worked example
  above (the examples in this document become the first golden files).
- **Determinism**: every CI run compiles each perf fixture twice and compares
  output-space hashes; a third pass with `perf.libm = "builtin"` asserts
  bit-exactness where the default allows last-ulp drift.
- **Anchor fuzz**: programmatically mutate scores (insert/delete/transpose
  bars, revoice chords) and assert rebase results: exact/context/fuzzy/orphan
  counts, idempotence, no drops.
- **Graph fuzz**: random listen/prev edge sets; assert cycle detection is
  exact and stratum assignment is unique.
- **Listening pass (seminar S-P3).** Golden files earn the name twice: once by
  hash, once by ear. Before a fixture becomes golden, its rendered audio gets a
  review — human first; later a designated listener agent whose only question is
  "does this sound like what the annotation claims" — recorded in the fixture
  header. Determinism plus one independent ear; a self-consistent compile that
  sounds like nothing anyone intended is a failure the hash cannot see by
  construction. Residual risk, named: the first ears still belong to this
  project's household.
- **Spec-first** (house rule for notation changes): each syntax feature lands
  with a failing-then-passing test, a `CHANGELOG.md` entry, and the whole
  `plainsong check` corpus green — including the thousands of existing files
  that must not notice perf exists.

---

## 15. CLI and MCP surface (proposed)

```bash
plainsong perf check file.perf.md           # diagnostics, joined with check
plainsong perf rebase last-ferry            # §4.2, writes the ledger
plainsong perf query 'ache > 0.7' last-ferry
plainsong perf categories last-ferry.perf.md
plainsong perf streams last-ferry           # the resolved graph
plainsong compile --perf last-ferry.perf.md …
```

MCP additions (plainsong-mcp): `perf_read`, `perf_write_part` (voice-scoped,
`base_version`, refused-and-rebased like parts), `perf_query`,
`perf_categories`, `perf_suggest` (log-routed, never applied). The ensemble
session grows `parts/*.perf` with ownership inherited from the voice claim.

---

## 16. Disagreements with the brief

Lucineer's six constraints, refined rather than obeyed:

1. **Grid readable — agreed, and given teeth.** Readability guidance without
   enforcement rots; the 40-line/25% diagnostic (§5.1) is the enforcement.
2. **Open tensor — agreed, with two additions**: units (coercion-checked, not
   decorative) and the category ledger with provenance, so emergent categories
   *coordinate* rather than fragment (`ache` means one thing across the fleet).
3. **Addressing — refined.** Fuzzy matching alone loses provenance and makes
   rebases unauditable. The compiler-maintained anchor ledger (§4.2) carries
   signatures; humans write short anchors, machines remember the rest. Pure
   fuzzy is the fallback tier, not the mechanism.
4. **Turing-complete — deferred honestly (seminar A1).** v1 ships first-order:
   Lustre-class synchronous dataflow, structural termination, purity and
   determinism untouched (§7.5). Recursion and fuel move to v2, admitted only by
   a demonstrated need the category ledger can point at. A terminating sandbox
   now; the hang-free turing-complete sandbox remains the ambition, behind a
   door that opens for evidence.
5. **Connections — refined twice.** (a) Cross-voice reads flow through
   *published streams* only — explicit contracts, not open access to another
   voice's notes. (b) Cycles resolve by `react` strata with one pass of lag,
   not a fixpoint search — matching the ensemble's asynchronous iteration, and
   evaluating at **compile time**, not as a live reactive runtime. Quilt's
   engine inspired the shape; perf is deliberately not a runtime.
6. **Markdown-native — agreed, one amendment.** `.song` files are not
   markdown; there the same grammar lives in `[Perf]` sections, and fenced
   ` ```plainsong-perf ` blocks are for markdown sidecars and docs. One
   language, two containers, no third syntax.

---

## 17. Open questions (two closed this revision — kept visible, not buried)

1. **Determinism at the last ulp.** Libm differs across platforms; quantised
   hashing makes it almost never matter. Almost. Ship `perf.libm = "builtin"`
   day one, or only when a real cross-platform CI failure forces it?
2. **What may reinterpret a semantic key later.** `ache` is data today and a
   mapping tomorrow — but *whose* mapping? A renderer that interprets
   `stage.dist` changes what old files mean. Does the ledger need a
   renderer-registry so interpretation is versioned and attributable?
3. **React latency semantics.** One `react` edge = one stratum = one compile.
   But musically, "the last pass" might want to be *one bar*, or *one ensemble
   iteration* (a whole session take). Which clock owns react?
4. **Control rate vs MIDI bandwidth.** 96 Hz with thinning is fine for CC; it
   is marginal for fast bend gestures and hopeless for sysex-heavy
   registration changes on real hardware. Is per-key rate override enough, or
   do we need perceptual scheduling (emit where the ear will notice)?
5. **The sidecar default for agents — RESOLVED (seminar A5).** `perf_write_part`
   accepts sidecar-style parts only, full stop. The evidence already answered it
   (every ensemble `write` in the corpus is a part write); the 40-line
   diagnostic guards humans, and the section-then-sidecar merge-order ambiguity
   dies for the entire agent population.
6. **Feature tensor cadence.** Features are per-bar, zero-order-held; a
   drummer "reacting to tension" gets staircase input. Interpolate linearly
   by default? Or publish features at the control grid and pay the compute?
7. **Poly aftertouch reality.** Soundfonts and hardware support it unevenly;
   per-note channels multiply the 16-channel budget. Is channel-pressure
   fallback the honest default forever, or does `touch` deserve per-note
   channels when a target declares support?
8. **Fuel as error vs clamp — RESOLVED (seminar A1/S-P4).** Recursion is
   deferred; the budget that remains trips a compile error, never a silent
   neutral span. `perf streams` output still shows every warned key. The
   question returns with recursion, if recursion ever returns.

---

## 18. Implementation order (if accepted)

1. Parser + anchors (complement selectors, drum-map rows) + ledger + rebase
   with the fuzzy budget — the tensor artifact exists, nothing compiles to new
   MIDI yet.
2. PEx first-order (no recursion, no fuel machinery; the global budget errors),
   physical keys → MIDI.
3. `listen` read edges + features publication + the cue seam (`$cue.*`,
   keep-empty rest overlay, §8.4).
4. Ensemble integration: commit-time compile (§9.5), suggestions, MCP tools.
5. Category ledger provenance + meaning versions, queries, embed meta.

(v2, evidence-gated: recursion + fuel + react strata — none of it built until a
real perf file demands it.)

Each step leaves `plainsong check` green over the whole corpus and the
fingerprint namespace extended (`fingerprint --perf`), never rewritten.

---

*Draft v0.2 by the design foreman after the cross-model seminar, 2026-08-25.
Nothing here is committed to the compiler. The examples are golden-file
candidates, not working code — yet.*
