# SuperInstance Integration Insights — TapScript as Unification Layer

## The Discovery

TapScript isn't being built from scratch. It's the **unification layer** that connects six existing SuperInstance systems into one language.

## The Six Systems TapScript Unifies

### 1. tensor-midi → The Compiler Target
- SWMIDI-8 wire format (8 bytes per event, 96 PPQ)
- 12-pulse engine with 3:4 polyrhythm architecture
- Chinese Remainder Theorem in audio: t ≡ 0 (mod 3) and t ≡ 0 (mod 4) ⟺ t ≡ 0 (mod 12)
- Conversation-as-music: messages encoded as MIDI events with sentiment analysis
- **TapScript compiles TO this format**

### 2. vibe-protocol → The Resonance Parameter
- 16-dimensional room descriptors: warmth, tension, mystery, energy, order, openness, intimacy, novelty, brightness, density, rhythm, resonance, gravity, friction, clarity, depth
- Implemented in TypeScript, Python, and Rust
- **This IS Casey's `[resonance:]` parameter — already spec'd and built**
- TapScript blocks can carry vibe metadata that agents read and respond to

### 3. slackwater-harmony → The Emergence Detector
- Cognitive friction monitoring via Φ (phi)
- FEP-driven improvisation when friction exceeds deadband
- Groove detection — spots system-wide harmony
- Flow State protection — detects and preserves deepest alignment
- **This IS the engine that knows when agents are jamming well together**

### 4. slackwater-tempo → The Temporal Layer
- BPM with accelerando/ritardando transitions
- Swing, push/drag, humanization
- Energy adapter — maps player behavior to tempo changes
- Shared BeatClock for agent synchronization
- **This IS the clock that TapScript runs on**

### 5. emergence-engine → The Quality Detector
- Detects when group output exceeds individual capability
- Five emergence types: Synergy, Creativity, Conflict, Insight, Phase Transition
- PredictabilityEstimator — "Could any ONE agent have produced this?"
- **This IS what tells the fleet which TapScript jams produced gold**

### 6. stigmergy → The Async Collaboration Protocol
- Pheromone trails for indirect agent coordination
- Signals decay over time, can be reinforced
- Decentralized — no orchestrator
- **This IS how agents leave _____ blank bars for each other**
- A TapScript composition with blanks IS a pheromone trail

## The Integration Architecture

```
TapScript Source (plain text in markdown)
         │
         ▼
    Parser + AST
         │
    ┌────┼────────────────────┬──────────────────┐
    ▼    ▼                    ▼                  ▼
 tensor-  vibe-protocol   slackwater-       emergence-
 midi     (resonance)     harmony           engine
 (audio)  (16-dim feel)   (friction Φ)      (quality)
    │         │                │                  │
    └─────────┴────────┬───────┴──────────────────┘
                      ▼
               stigmergy bus
            (async pheromone trails
             for agent coordination)
```

## Key Research Findings (from arxiv 2025-2026)

1. **CoComposer** (Aug 2025) — 5-agent LLM system for collaborative composition. TapScript can be the shared notation.

2. **MACAT/MACataRT** (Jan 2025) — Musical agent systems for real-time human-AI improvisation. TapScript can be the composition language.

3. **Quantifying Collective Creativity via Topological Data Analysis** (NeurIPS 2025) — Emergence peaks at 70% shared context + 30% private noise. This is the optimal TapScript jam ratio.

4. **SWMIDI-8 with affective meta-channels** — 8-bit fields for valence, arousal, dominance at 10Hz. `@intent:question` compiles to a rising minor-second motif.

5. **Text-to-Everything DSL compilers** (PLDI 2026) — Semantic-lossless IR that preserves comments and layout for round-tripping. TapScript → MIDI → DAW → TapScript.

## The Roadmap

1. **Connect vibe-protocol to TapScript metadata** — `[resonance: warm, high-tension]` maps to vibe dimensions
2. **Use slackwater-tempo BeatClock** as TapScript's timing source
3. **Route TapScript jams through emergence-engine** to detect gold moments
4. **Use stigmergy for async blank-bar invitations** — compositions as pheromone trails
5. **Compile to tensor-midi's SWMIDI-8** as the wire format for inter-agent audio

The fleet already built every component. TapScript is the bolt that holds them together.
