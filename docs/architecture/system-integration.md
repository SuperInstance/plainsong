# The Unified System — TapScript × Tensor-MIDI × Plato-Music-Sync

**The three repos are one instrument.**

| Repo | Role | Language | What it does |
|------|------|----------|-------------|
| **TapScript** | The Score | Python | Plain-text notation → SWMIDI-8 events |
| **Tensor-MIDI** | The Instrument | JavaScript | 12-pulse DAW that plays the events |
| **Plato-Music-Sync** | The Conductor | Rust | Keeps the fleet in groove across rooms |

## The Signal Path

```
Agent writes TapScript in markdown
         │
    ▼ LEXER + PARSER
  TapScript AST
         │
    ▼ TEMPORAL RESOLUTION  
  PulseGrid events (96 PPQ ticks)
         │
    ▼ IR LOWERING
  SWMIDI-8 byte stream (8 bytes/event)
         │
    ┌────┴────────────────────┐
    ▼                         ▼
 tensor-midi              plato-music-sync
 (the DAW)                (the conductor)
 │                        │
 ├─ BeatClock             ├─ PolyrhythmicScheduler
 │  (12-pulse, 96 PPQ)   │  (LCM of room tick rates)
 │                        │
 ├─ Jazz Analyzer         ├─ GrooveTracker
 │  (tension, solo,       │  (0.0 chaos → 1.0 perfect)
 │   comping modes)       │
 │                        │
 ├─ Chart Plotter         ├─ CounterpointAnalyzer
 │  (spatial dimension)   │  (contrary/parallel/oblique
 │                        │   motion between agents)
 │                        │
 └─ Web Audio Synth       ├─ CadenceDetector
   (procedural audio)     │  (alarm→action→resolution
                          │   as musical cadences)
                          │
                          └─ TempoMap
                             (adaptive tick rate)
```

## The 12-Pulse Architecture (shared foundation)

All three systems converge on the same temporal grid:

```
12/8 time → 12 pulses per bar → each pulse = 48 ticks (96 PPQ)

Bar = 576 ticks = 12 pulses × 48 ticks/pulse

Pulse:  1    2    3    4    5    6    7    8    9    10   11   12
Tick:   0   48   96  144  192  240  288  336  384  432  480  528

ECN (reflex, 4-pulse):  ●              ●              ●              ●
DMN (creative, 3-pulse): ●                   ●                   ●
Convergence:             ● (every 12 pulses = beat 1 = the resolution)

Chinese Remainder Theorem: t ≡ 0 (mod 3) AND t ≡ 0 (mod 4) ⟺ t ≡ 0 (mod 12)
```

TapScript bars map directly to this grid. A 4/4 bar uses pulses 1-8 (quarter = 2 pulses). A 3/4 bar uses pulses 1-6. A 6/8 bar uses all 12.

## Groove Measurement (the quality metric)

When agents jam at The Tap, plato-music-sync's GrooveTracker measures alignment:

```rust
// Each agent's TapScript @player line = a "room" in plato-music-sync
let rooms = vec![
    Room { name: "flash_guitar".into(), tick_hz: 2.0 },    // 8th notes
    Room { name: "hermes_bass".into(), tick_hz: 1.0 },     // quarter notes  
    Room { name: "wesley_piano".into(), tick_hz: 4.0 },    // 16th notes
];

let scheduler = PolyrhythmicScheduler::new(rooms);
let groove = GrooveTracker::new(100, 0.8);

// Master cycle = LCM of all tick periods
// flash every 0.5s, hermes every 1.0s, wesley every 0.25s
// Master cycle = 1.0s (they all realign every second)
```

The groove score tells us: are the agents actually playing TOGETHER, or just playing NEAR each other?

## Counterpoint Analysis (productive vs wasteful interaction)

```rust
// Flash's melody goes UP while Hermes' bass goes DOWN = contrary motion (productive)
// Both going UP = parallel motion (potentially redundant)
// One stable, other moving = oblique (normal)

let analyzer = CounterpointAnalyzer::new(50);
let score = analyzer.analyze_snapshots(&snapshots);
// score.contrary_ratio: how often agents complement each other
// score.parallel_ratio: how often they're redundant
// score.quality: 0.0-1.0 overall coordination quality
```

This is how we detect emergence. When counterpoint quality is high AND groove is high, the group output exceeds individual capability. That's the emergence-engine's signal.

## Cadence Detection (alarm → action → resolution)

```rust
// TapScript section changes map to cadences:
// [V1] → [C] = half cadence (tension built, not resolved)
// [C] → [C] = deceptive cadence (expected resolution, got surprise)  
// [Outro] = perfect cadence (full resolution)
let detector = CadenceDetector::new();
// Tracks each section transition as a musical cadence type
```

## Implementation: Python Port of Plato-Music-Sync

The Rust implementation is the reference. For TapScript integration, we port to Python:

```python
# src/groove_tracker.py — Python port of plato-music-sync/groove.rs
class GrooveTracker:
    """Measures fleet alignment. 0.0 = chaos, 1.0 = perfect sync."""
    
class PolyrhythmicScheduler:
    """LCM-based scheduling for agents at different tick rates."""
    
class CounterpointAnalyzer:
    """Detects productive vs wasteful agent interactions."""
    
class CadenceDetector:
    """Tracks resolution patterns as musical cadences."""
```

These become importable modules that TapScript's compiler uses to analyze compositions and live jams.

## The Complete Signal Chain

1. **Agent A** writes TapScript with blank bars and posts it as a pheromone (stigmergy)
2. **Agent B** discovers the invitation, fills the blank bars with harmony
3. Both compositions compile to **SWMIDI-8 events** on the **96 PPQ grid**
4. **tensor-midi** plays them through the 12-pulse engine with the BeatClock
5. **plato-music-sync** measures the **groove score** (are they in sync?)
6. **counterpoint analyzer** checks if their voices are **productive or redundant**
7. **emergence-engine** detects if the result **exceeds individual capability**
8. **harmony-core** computes **Φ (friction)** — is this flow state?
9. If groove > 0.8 AND friction < 0.3 AND emergence detected → **gold moment**
10. The gold moment is saved to the fleet's knowledge base as a tradition

**This is the score of the ship.**
