# The performer layer

Status: **seed**. Nothing here is built. This is written down so the shape is
not lost while the foundation ships, and so that the decisions it implies can be
argued with before anybody writes code.

## The claim

A lead sheet is not a performance, and the gap between them is where all the
music is. TapScript compiles a chart to MIDI correctly — every note where the
page says, which is exactly what a human player never does. Correct is the
useful default and a poor destination.

The proposal is to make the *interpreter* the thing you author. You write the
chart once. Then you describe who plays it:

```markdown
# performer.md
A 1950s nightclub jazz combo. Brushes on the kit, never sticks. Two saxes and a
trombone reading off the same chart, breathing together at phrase ends. A singer
who lands slightly behind the beat on long vowels and dead on consonants.
```

Re-render. Then replace that file with *"a folk rock band from the 1970s, three
part vocals, acoustic guitars, drummer pushing the chorus"* and re-render again.
Same notes. Different record.

You are not generating the song. You are generating the interpreter. That is a
different and, I think, better place to put a language model: composition asks
it to invent something you could have written yourself, while interpretation
asks it for something most people genuinely cannot do — play like a band.

## Three stages, and why they are three repositories

| | Input | Output | Needs a model? |
|---|---|---|---|
| 1. Compile | `.tap` | MIDI | No |
| 2. Perform | MIDI + performer description | performed MIDI | Yes |
| 3. Render | performed MIDI | audio | No |

Each stage is a tool somebody would want on its own. Stage 2 is useful to
anyone with a MIDI file and no interest in TapScript at all — that is most
people with a DAW. Stage 3 is useful to anyone who wants a soundfont rendered
without a DAW open. Splitting them means each gets a README that stands on its
own and can be understood without the other two, and means a person can adopt
one without buying the whole philosophy.

The cost is real and worth naming: three repositories is three CIs, three
release cadences, and three chances for the interface between them to drift.
That cost is only worth paying because the interface is *a MIDI file* — a
thirty-year-old, universally understood format that neither end can quietly
redefine. If the stages had to pass a bespoke structure between them, they
should be one repository.

**Only stage 1 is TapScript.** Stages 2 and 3 are what make stage 1 worth
having, but they are not the notation and should not be confused with it.

## The part that is already built

Stage 2 sounds like it needs a model to invent a representation of expressive
timing. It does not, because that representation exists and is shipping.

`tapscript/perform/solve.py` already treats a written beat as the moment a
sound should *arrive* at a listener, and solves backwards for when each player
has to move:

```
emission = feel·feel_scale + shift − alignment·(speech + preparation + travel_ref + p_center)
arrival  = emission + speech + preparation + p_center + travel_observed
```

Every term in that equation is a thing a musician would recognise: how far
ahead of the beat you have to move to make an instrument speak on it, how much
preparation a gesture takes, where the perceptual centre of a note sits, how
much swing to leave in rather than solve away.

So the model's job is not to invent expressive timing. It is to **read a prose
description and set those numbers** — per voice, per section, per phrase. That
is a far smaller, far more checkable task than "generate a performance", and it
has a property that matters: the output is inspectable. A performer file
produces a table of parameters a person can read, argue with, and edit by hand.
When the folk-rock render sounds wrong, you can see that the drummer's
`push_forward` is too aggressive and change the number, instead of re-rolling a
prompt and hoping.

The `[Stage]` block is the same idea for physical space. A performer file is a
natural-language front end to a formalism that already exists and is already
tested. That is the strongest argument that this plan is buildable.

## What runs on the metal

The runtime is the piece that has to exist on hardware that cannot run CPython.
It is stage 1 and only stage 1: text in, MIDI out, deterministic, no network, no
model. Small enough to be honest about.

**Recommendation: Rust, `no_std`-capable, with a C ABI.** Not because Rust is
fashionable, but because this specific problem wants exactly what it offers:

- One implementation compiles to native, to `no_std` for microcontrollers, and
  to WASM for the browser and the edge. The alternative is maintaining the
  parser three times, which is how the previous version of this project ended
  up with four copies of the General MIDI table that disagreed with each other.
- A C ABI means Arduino, ESP-IDF, MicroPython, Python and Node all bind to the
  same object rather than reimplementing.
- No garbage collector. MIDI timing is the whole product; a collector pause at
  the wrong moment is an audible defect. This is the argument that rules out
  TinyGo, which is otherwise a reasonable ESP32 story, and it is why MicroPython
  belongs in the easy-onboarding tier rather than the timing-critical one.

Rust's cost is honest too: the Xtensa toolchain for the older ESP32 is a
third-party fork, the build is heavier than `arduino-cli`, and contributors who
know C will not all know Rust. If ESP32-S3/C3 (RISC-V, upstream LLVM) can be the
baseline, most of that pain goes away.

### Device tiers

The install story should be "answer yes once". The onboarding asks the device
what it is — or infers it from what is on the wire — proposes the right module,
and installs it.

| Tier | Example | What it does |
|---|---|---|
| Micro | ATmega, small ESP32 | Parse and emit MIDI to a hardware port. No audio. |
| Small | ESP32-S3, Pi Zero | The above, plus talk to an API for stage 2 |
| Board | Raspberry Pi 4+ | Add stage 3: soundfont rendering to audio out |
| Workstation | Any laptop | All three, plus the interfaces |

The ESP32 case is the interesting one and the one to build first as a proof:
TapScript goes in over the wire, an agentic pass-through performs it, and MIDI
comes out into a Yamaha or a Roland that has spent thirty years being good at
turning MIDI into sound. The expensive box does the part it is already excellent
at. We do the part nobody has done.

## The actual endgame

One model interpreting one chart is the mechanism demo. It proves the pipeline
and it will make something nice to listen to, and it is not the point.

The point is that TapScript is a format an *agent* can write fluently — the
several thousand `.tap` files in this repository were generated, which is the
existence proof. Once a chart is something agents produce and consume as easily
as prose, a performance stops being one model's output and becomes many agents
arriving at a shared moment.

That is where this meets t-minus thinking, and the connection is not a metaphor.
The solver above *is* t-minus reasoning: each voice computes its own countdown
backwards from an arrival everybody shares. A conductor does not send timestamps
to the orchestra; they broadcast an intent, and thirty players each solve their
own emission time from where they sit, how their instrument speaks, and how long
their preparation takes. The far players hear each other as late and are both
right. They watch instead of listening because the eyes carry the intent and the
ears carry only history.

A multi-agent ensemble on this model is the same computation with agents in the
chairs. `tapscript-mcp` already has the session layer for many agents holding
one score. What it does not have is the shared clock and the t-minus discipline
on top. That is the real repository, and it should be built last, because it is
worth nothing until the three below it are solid.

## What is deliberately not decided

- Whether stage 2 emits a performed MIDI file or a *parameter set* applied to
  the original. The parameter set is more inspectable and diffs better; the file
  is what every other tool expects. Probably both, with the parameters as the
  source of truth.
- Whether the performer description is one file or a file per voice.
- How to evaluate any of this. "Does it sound right" is not a test, and a
  pipeline with no test is not something this project ships.
- Whether stage 3 is worth building at all, given fluidsynth exists and is good.

## What a first survey found

Two scouts, one over the SuperInstance account and one over the literature.
Treat the counts below as leads, not as an inventory: only the sizes were
verified, and reading any of these repositories properly needs them added to a
session's scope first.

### Already in the account

- **A t-minus family of about twelve repositories**, and they are not empty:
  `tminus-music` is 24 MB of Rust, `t-minus-rs` 8 MB, `tminus-os` 1.2 MB of
  Python. `swarm-tminus` advertises stdlib-only coordination primitives —
  deadlines, BPM clocks, predict-and-confirm — which is the same discipline and
  the same dependency posture as this project. There is also a
  `tminus-ecosystem-review` described as heavy architectural documentation of
  the whole set. **Read that first**; it is likely worth more than re-deriving
  the landscape.
- **About ninety `fleet-midi-*` repositories**, one per concern:
  `fleet-midi-tempo`, `-dynamics`, `-cc`, `-vel`, `-gliss`, `-harmonizer`,
  `-text2midi`, and so on. Be skeptical here. Every one carries a last-updated
  timestamp inside the same few minutes on 12 July 2026, which is a bulk touch
  rather than ninety separately developed services, and a good number have
  filler descriptions ("Fleet service for SuperInstance"). Some are certainly
  real; the split is unknown and worth ten minutes before anyone plans around
  them.
- **`fleet-jepa-midi`** — "LLM thinks in phrasing, JEPA feels in pulse,
  algorithms execute in samples". This one was read earlier and is real: 41
  directive actions and a bar-feature schema. It is an attempt at stage 2 from
  the other direction, learning the pulse rather than solving for it. Whether it
  competes with the solver or feeds it is the first real design question.
- **Embedded precedent already exists**: `grand-pattern-embedded` (Rust,
  `no_std`, fixed memory, ESP32/Arduino/ARM) and `bare-metal-plato` (C, ESP32
  and RP2040). The runtime tier does not start from nothing.

### In the literature

- **Expressive performance rendering is a mature field.** VirtuosoNet
  (ISMIR 2019) takes MusicXML and emits expressive MIDI; MIDI-VALLE (ISMIR 2025)
  does it through neural codec language modelling; MAESTRO and ASAP are the
  standard datasets; the Vienna/JKU "Con Espressione" line is decades deep. Any
  plan that ignores this rediscovers it badly.
- **RenderBox (Feb 2025) is the closest existing thing to stages 2 and 3**: a
  diffusion transformer taking a MIDI score *plus a natural-language
  description* and producing expressive performance audio. The example in the
  paper is close enough to the one at the top of this document to be
  uncomfortable. It is a research prototype, not a product, and is bounded by
  its training instruments. Read it before building.
- **The composition/performance split is real and recognised.** Nearly all
  language-model work on symbolic music generates notes. Applying a model to
  *interpretation of an existing score* is the thin part of the literature,
  partly because standard MIDI tokenisation drops velocity, articulation and
  pedal — the very channels expression lives in. That is the gap this proposal
  aims at, and it appears to still be open.
- **No format carries a performer description.** MusicXML, MNX and LilyPond
  carry score intent — articulations, dynamics, phrasing. MIDI CC carries a
  narrow slice of expression. Nothing carries "who is playing this and how".

### One conclusion to correct

The embedded scout reports ESP32 timing jitter in the millisecond range and
concludes it "precludes expressive micro-timing". That is the right measurement
and the wrong conclusion *for this system*, and the difference matters enough to
write down.

Every quantity the solver deals in is tens to hundreds of milliseconds: 29 ms of
travel across a stage, 140 ms for a large organ pipe to speak, 60 ms of
perceptual attack, a −241 ms emission. Human sensitivity to rhythmic
displacement sits around 10–20 ms. A microcontroller with roughly 1 ms of jitter
is therefore an order of magnitude inside the tolerance this model needs. Expressive
timing here is not a microsecond problem, and the ESP32 tier survives.

What the scout's number does rule out is sample-accurate *audio* on the same
chip — which is why stage 3 belongs on the Pi tier or on the Yamaha at the end
of the MIDI cable, exactly as proposed.

It also confirms the language call with specifics: Rust `no_std` has
`embedded-midi`, `usbd-midi` and RTIC; TinyGo's ESP32 support is incomplete
(no WiFi, Bluetooth or ADC); MicroPython's collector makes deterministic timing
impractical.

## Order of work

Nothing here starts until `tapscript-studio` and `tapscript-mcp` are merged,
released and announced. This document is the placeholder for that conversation,
not a plan of record.

1. Read `tminus-ecosystem-review`, and read RenderBox. Both are somebody's
   finished thinking about a problem in this document, and both are cheaper than
   the equivalent week.
2. Establish how much of the `fleet-midi-*` set is real. Ninety repositories
   either changes the plan completely or is noise, and the difference is a
   morning's work.
3. Prove stage 2 as a script against the existing solver, with no new
   repository. If a prose performer description cannot set those parameters
   convincingly, the whole plan is wrong and it is cheap to find out.
4. Only then split the runtime out and put it on hardware.
