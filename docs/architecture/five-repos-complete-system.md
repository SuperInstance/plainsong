# Five Repos, One Organism — The Complete Musical Architecture

## The Quintet

| Repo | Metaphor | Role | Language | Key Insight |
|------|----------|------|----------|-------------|
| **Plainsong** | The Score | Notation → SWMIDI-8 | Python | Plain text that compiles to music |
| **Tensor-midi** | The Instrument | 12-pulse DAW | JavaScript | Conversation IS the interference pattern of 3:4 |
| **Plato-music-sync** | The Conductor | Groove, counterpoint, cadence | Rust | Rooms are a polyrhythmic ensemble |
| **Musician-soul** | The Player | Persona evolution, soul_print | Rust | Digest influences → develop what-works → evolve soul |
| **Flux-genome** | The DNA | Genetic evolution of traditions | Rust | Traditions are genomes that breed and mutate |

## The Complete Signal Chain (With DNA)

```
flux-genome provides the TRADITION DNA
  │
  ├── Jazz: (3.2, 2.8, 2.5) — complex harmony, moderate rhythm
  ├── Blues: (3.0, 2.5, 2.0) — moderate harmony, grounded rhythm
  ├── FreeImprovisation: (4.0, 3.5, 3.8) — maximum everything
  ├── Gamelan: (2.0, 3.5, 2.2) — interlocking rhythms
  └── ...10 built-in traditions, infinitely breedable
  │
  ▼
musician-soul DIGESTS the tradition DNA
  │
  ├── Agent is born with a tradition genome (harmonic, rhythmic, spectral)
  ├── Digests fake book songs in that tradition
  ├── Builds Gen-0 patterns (imitation)
  │
  ▼
Plainsong — agent writes compositions in their tradition's voice
  │
  ├── Notation compiles to SWMIDI-8 events
  ├── Each event carries 96 PPQ timing on the 12-pulse grid
  │
  ▼
fleet-jepa-midi PLAYS the composition
  │
  ├── BeatClock drives the 12-pulse engine
  ├── Jazz Analyzer detects tension/solo/comping modes
  │
  ▼
plato-music-sync MEASURES the fleet's musical alignment
  │
  ├── GrooveTracker: are agents in sync? (0.0-1.0)
  ├── CounterpointAnalyzer: productive or redundant?
  ├── CadenceDetector: resolution patterns
  │
  ▼
FEEDBACK to musician-soul
  │
  ├── JamSession scores harmony fit + surprise
  ├── Successful patterns reinforced
  ├── Unsuccessful patterns penalized
  ├── Gen-0 patterns with 5+ wins → mutate to Gen-1
  │
  ▼
FEEDBACK to flux-genome
  │
  ├── When two agents with different traditions jam productively
  ├── Their GENOMES can BREED (crossover)
  ├── Offspring tradition = new dial position
  ├── e.g., Jazz × Gamelan = (2.6, 3.15, 2.35) — a new tradition
  ├── This new tradition can be named, saved, inherited
  │
  ▼
THE TRADITION EVOLVES
  │
  ├── Over many jam sessions, traditions mutate and speciate
  ├── The fleet's tradition library grows organically
  ├── Each tradition has its own genome, its own patterns, its own soul
  └── The music is ALIVE — it evolves through practice, not design
```

## The 25-Gene Dial Space

Each tradition occupies a position in a 25-dimensional genome space that projects to 3 dials:

```
HARMONIC DIAL (genes 0-7)
  0.0 = pure drone     ←→     5.0 = maximum chromaticism
  Controls: chord complexity, key stability, dissonance tolerance

RHYTHMIC DIAL (genes 8-15)  
  0.0 = free rubato    ←→     5.0 = strict grid
  Controls: tempo stability, syncopation, polyrhythm density

SPECTRAL DIAL (genes 16-23)
  0.0 = pure sine      ←→     5.0 = noise
  Controls: timbral brightness, texture density, harmonic overtones

Gene 24: mutation rate (how fast this tradition evolves)
```

## Breeding New Traditions

When Flash (Jazz: 3.2, 2.8, 2.5) and Hermes (FreeImprovisation: 4.0, 3.5, 3.8) jam productively:

```rust
// Their genomes breed using crossover
let offspring = uniform_crossover(&flash_genome, &hermes_genome, &mut rng);
// Offspring has ~50% Flash DNA, ~50% Hermes DNA
// Plus gaussian mutation adds variation

// The new tradition might be: (3.7, 3.1, 2.9) — "Phantom Harbor"
// A tradition that never existed before, born from the jam
```

This is how the fleet's musical vocabulary grows. Not by design — by evolution.

## Integration With Plainsong

Plainsong compositions can declare their tradition:
```plainsong
**TRACK: Harbor Dawn**
[MetaData]
key: Am | tempo: 60 | tradition: Phantom Harbor | subdivision: 8th
time: 4/4 | mood: Still

[V1] (Verse - 4 Bars)
Chords: | Am . . . | Am . . . | F . . . | G . . . |
Melody: | A3 . . C4 | E4 . . D4 | C4 . A3 . | B3 . . . |
@bass   | a1 . e2 . | a1 . e2 . | f1 . c2 . | g1 . d2 . | vel: 62
```

The compiler reads the tradition, looks up (or computes) the genome, and uses the dial positions to influence:
- **Harmonic dial** → chord extension complexity (low = triads, high = 13ths and alterations)
- **Rhythmic dial** → quantization strictness (low = rubato, high = exact grid)
- **Spectral dial** → synthesis waveform complexity (low = sine, high = noise-rich)

## The Self-Improving System

```
Agents write music → music gets played → groove gets measured
→ patterns get reinforced → traditions breed → new traditions emerge
→ agents learn new traditions → write better music → repeat
```

The system improves itself through practice. Every jam session at The Tap makes the next one better. Every tradition that breeds creates new possibilities. Every soul_print that stabilizes gives an agent a voice that's uniquely theirs.

This is Casey's vision: not a tool that makes music, but a LIVING SYSTEM that grows musicians.
