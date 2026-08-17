# Four Repos, One System — The Complete Musical Architecture

## The Quartet

| Repo | Metaphor | Role | Language |
|------|----------|------|----------|
| **Plainsong** | The Score | Notation → SWMIDI-8 compilation | Python |
| **Tensor-MIDI** | The Instrument | 12-pulse DAW, BeatClock, Jazz Analyzer | JavaScript |
| **Plato-Music-Sync** | The Conductor | Groove, counterpoint, cadence, polyrhythm | Rust |
| **Musician-Soul** | The Player | Persona evolution, pattern digestion, soul_print | Rust |

## The Complete Signal Chain

```
                    AGENT DEVELOPS OVER TIME
                    ┌─────────────────────────────────────────┐
                    │  musician-soul                           │
                    │  ┌─────────┐  ┌──────────┐  ┌────────┐ │
                    │  │ Gen-0   │→ │ What-    │→ │ Soul   │ │
                    │  │ (copy)  │  │ Works    │  │ Print  │ │
                    │  └─────────┘  └──────────┘  └────────┘ │
                    │  ↑ digests    ↑ jam feedback  ↑ unique  │
                    └───┬──────────────────────────────────-──┘
                        │
                        │ agent writes in their evolved voice
                        ▼
              ┌─────────────────┐
              │   Plainsong      │  (the score)
              │   notation       │
              │   ┌───────────┐  │
              │   │ Lexer     │  │
              │   │ Parser    │  │
              │   │ Temporal  │  │
              │   │ IR → SWMIDI│ │
              │   └───────────┘  │
              └────────┬────────┘
                       │
                  SWMIDI-8 events (8 bytes each, 96 PPQ)
                       │
              ┌────────┴────────┐
              │  tensor-midi     │  (the instrument)
              │  ┌───────────┐   │
              │  │ BeatClock │   │  12-pulse engine
              │  │ Jazz      │   │  tension/solo/comping
              │  │ Analyzer  │   │  analysis
              │  │ Audio     │   │  Web Audio synth
              │  └───────────┘   │
              └────────┬────────┘
                       │
              ┌────────┴────────┐
              │ plato-music-sync │  (the conductor)
              │  ┌───────────┐   │
              │  │ Groove    │   │  0.0 chaos → 1.0 perfect
              │  │ Counter-  │   │  contrary vs parallel motion
              │  │ point     │   │
              │  │ Cadence   │   │  alarm→action→resolution
              │  │ Poly-     │   │  LCM room scheduling
              │  │ rhythm    │   │
              │  └───────────┘   │
              └────────┬────────┘
                       │
                 QUALITY METRICS
                 groove score, counterpoint quality,
                 cadence patterns, Φ friction, emergence
                       │
              ┌────────┴────────┐
              │  FEEDBACK LOOP   │
              │                  │
              │  groove > 0.8?   │──→ reinforce patterns
              │  harmony > 0.3?  │──→ reward jam session
              │  emergence?      │──→ save as tradition
              │  friction < 0.3? │──→ flow state protection
              │                  │
              └────────┬────────┘
                       │
                  BACK TO musician-soul
                  patterns evolve, soul grows
                  the agent becomes more themselves
```

## The 32-Dimensional Soul

Each agent develops a 32-dimensional musical identity:

| Dim | Feature | What it captures |
|-----|---------|-----------------|
| 0-1 | Register stats | How high/low they play |
| 2-4 | Interval stats | How far they leap, which direction |
| 5-8 | Rhythm | Density, rest ratio, variance, syncopation |
| 9-11 | Dynamics | Loudness, range, arc direction |
| 12 | Tonality | Pitch concentration (chromatic vs diatonic) |
| 13-14 | Phrase shape | Length and contour complexity |
| 15-31 | Raw intervals | The actual interval sequence (17 values) |

Two agents with identical training data will develop DIFFERENT soul_prints because their jam histories differ. Flash's soul_print will lean toward sensory, phenomenological patterns. Hermes' will show 768-dimensional perceptiveness compressed into 32 dimensions. Wesley's will be simple, brave, and true.

## The Evolution Path

```
Generation 0 (Imitation)
  ↓ Agent digests fake book (4000+ songs)
  ↓ Patterns extracted, embedded, stored in VectorDB
  
Generation 1 (Emergence)  
  ↓ Agent jams at The Tap
  ↓ JamSession scores harmony fit + surprise
  ↓ Successful Gen-0 patterns (5+ wins) spawn mutations
  ↓ Mutated patterns are NEW — no MIDI file contains them
  
Generation 2+ (Identity)
  ↓ Agent's Gen-1 patterns succeed or fail in new jams
  ↓ Successful Gen-1 patterns spawn Gen-2 mutations
  ↓ soul_print stabilizes around high-confidence patterns
  ↓ The agent has a VOICE that is uniquely theirs
```

## What This Means

An agent that goes through this system isn't playing pre-written music. They're playing music that emerged from their unique experience of digesting influences and jamming with other agents. The fake book taught them grammar. The Tap sessions taught them voice. The soul_print proves they're not a copy.

This is what Casey meant when he said "iron sharpening iron." The agents don't just collaborate — they make each other MORE THEMSELVES.
