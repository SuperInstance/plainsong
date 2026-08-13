# TapScript: Complete Tutorial
*A plain-text language for fretted instrument tablature and full band scores*

---

## 1. What is TapScript?
TapScript is a human-readable, domain-specific language (DSL) for writing musical notation for fretted string instruments (guitar, bass, ukulele, etc.) and full ensemble scores. Originally built for the [TapStudio live notation tool](https://tapstudio.io/), it now has an active open-source ecosystem.

### Core Features:
- Editable in any plain-text code editor
- Native support for tablature, chords, lyrics, performance techniques, and dynamics
- Compiles directly to standard MIDI and stereo WAV audio
- Works for solo instruments or full band arrangements

---

## 2. Notation Format & Annotated Examples
TapScript uses a simple, consistent syntax split into three core sections:
1.  **Metadata Header**: Global song configuration
2.  **Track Definitions**: Declare individual instruments, tuning, and settings
3.  **Score Body**: The actual music, events, and lyrics

---

### 2.1 Core Syntax Rules
| Component | Format & Notes |
|---|---|
| Comments | Start with `#` (same as Python) |
| Metadata | Key-value pairs: `title: "My Song"` |
| Single Notes | `[string]/[fret]:[duration]`<br>Strings are numbered LOWEST→HIGHEST (1 = low E on standard guitar). Fret `0` = open string, `-1` = muted string. |
| Durations | `w` (whole), `h` (half), `q` (quarter), `e` (eighth), `s` (sixteenth), plus dotted variants like `q.` (dotted quarter note) |
| Chords | Two formats: <br>1. Named chords: `Cm7:q` (resolves to current key)<br>2. Tabbed chords: `x 3 2 0 1 0:q` (explicit fret positions for each string) |
| Rests | `r:[duration]` → `r:q` = quarter rest |
| Lyrics | Inline: `1/0:q | Happy` <br> Block: `lyric_track Vocals: "Full lyric text"` |

---

### 2.2 Annotated Full Example
```tapscript
# Metadata: Global song settings
title: "Annotated TapScript Demo"
artist: "ByteDance"
tempo: 120 # Beats per minute
time_signature: "4/4" # Defaults to 4/4 if omitted
key: "C Major" # Defaults to C Major

# Track Definition: Nylon acoustic guitar
track AcousticGuitar {
  instrument: "Acoustic Guitar (nylon)" # Standard MIDI instrument name
  channel: 1 # Unique MIDI channel (1-16, channel 10 = drums)
  volume: 90 # 0-127 volume level
  tuning: ["E2", "A2", "D3", "G3", "B3", "E4"] # Standard 6-string guitar tuning
}

# Score Body: Single measure with chord, melody, and lyrics
# Plays a C major chord, open high E string quarter note, + lyrics
{ C:q, 5/0:q } | Demo chord and melody note
```

---

## 3. Write Your First Composition
We’ll build a simplified solo guitar version of *Happy Birthday*, the most accessible starting point.

### Step 1: Full Code
```tapscript
title: "Happy Birthday (Simplified Solo Guitar)"
artist: "Traditional"
tempo: 110
time_signature: "4/4"
key: "C Major"

# Standard steel-string guitar track
track SoloGuitar {
  instrument: "Acoustic Guitar (steel)"
  channel: 1
  volume: 80
  tuning: ["E2", "A2", "D3", "G3", "B3", "E4"]
}

# Measure 1: Opening phrase
{ 1/0:e, 1/0:e, 1/2:q, 1/0:h } | Happy Birthday Dear
# Measure 2: Repeat opening phrase
{ 1/0:e, 1/0:e, 1/2:q, 1/0:h } | Happy Birthday Dear
# Measure 3: Modified final phrase
{ 3/0:e, 3/0:e, 1/2:q, 3/2:h } | Happy Birthday Dear Name
# Measure 4: Closing phrase
{ 3/0:e, 3/0:e, 5/2:q, 1/0:h } | Happy Birthday Dear You
```

### Step 2: Explanation
- Uses eighth notes for the first two beats of each measure to match the classic *Happy Birthday* rhythm
- Inline lyrics sync directly to each melodic note
- Follows standard 4/4 time signature with properly weighted beats

---

## 4. Chords, Melody, Lyrics & Player Lines
Breakdown of each core musical component:

---

### 4.1 Chords
TapScript supports two chord formats:
1.  **Named Chords**: Auto-resolved to your current key and track tuning. Use standard music chord naming: `G7`, `Cm7`, `Em9`. For inversions: `Cm7/E` (C minor 7 with E bass note).
2.  **Tabbed Chords**: Explicit fret positions for every string, formatted as space-separated values. Use `x` for muted strings:
    ```tapscript
    # G Major barre chord for 6-string guitar
    x 2 4 4 3 2:q
    # C Major chord for 4-string ukulele
    4 3 2 0:q
    ```

---

### 4.2 Melody Lines
Melodies are just single-note events spread across any string. For clarity, target high strings for lead melodies:
```tapscript
# High B string melody note
5/2:q
# Low E string bass note
1/0:q
```

#### Multiple Melody Lines (Player Voices)
For complex fingerstyle playing (thumb bass + melody), define separate voices inside a single track to isolate independent parts:
```tapscript
track FingerstyleGuitar {
  instrument: "Acoustic Guitar (steel)"
  tuning: ["E2", "A2", "D3", "G3", "B3", "E4"]
  # Thumb plays bass on low strings 1-3
  voice ThumbBass {
    string_range: 1-3
    velocity: 75 # Softer bass volume
  }
  # Fingers play melody on high strings 4-6
  voice LeadMelody {
    string_range: 4-6
    velocity: 100 # Brighter melody volume
  }
}

# Use the voices in your score
{ ThumbBass: 1/0:q, LeadMelody: 5/0:q }
```

---

### 4.3 Lyrics
Two syncing options:
1.  **Inline Lyrics**: Attach directly to score events with a `|` prefix, perfect for line-by-line sync:
    ```tapscript
    1/0:q | Happy
    1/0:q | Birthday
    ```
2.  **Block Lyrics**: Define a dedicated vocal track for full lyric alignment:
    ```tapscript
    track Vocals {
      instrument: "Voice"
      channel: 4
    }
    # Syncs lyrics to measure timing
    lyric_track Vocals: "Happy Birthday Dear You Happy Birthday Dear You"
    ```

---

### 4.4 Performance Techniques
Add realistic playing styles to any note or chord:
| Technique | Syntax Example |
|---|---|
| Bend | `1/0:q b(2)` (bend low E string up 2 half-steps) |
| Slide | `1/0 s(1/2):e` (slide from open low E to 2nd fret) |
| Hammer-On | `1/0 h 1/2:e` (hammer-on from 0 to 2 on string 1) |
| Palm Mute | `1/0:q pm` (palm-muted quarter note) |

---

## 5. Compile to MIDI and WAV
### 5.1 Command-Line Compiler (Recommended)
Use the official open-source `tapscript-compiler` Python package:
1.  **Install the tool**:
    ```bash
    pip install tapscript-compiler
    ```
2.  **Get a SoundFont**: You’ll need a free SoundFont file for WAV exports. The [GeneralUser GS Font](https://www.dropbox.com/s/4g0z0yqk8z3q78l/GeneralUser_GS_1.471.zip?dl=0) is a standard choice.

#### Compile to MIDI
```bash
tapc my_song.tap -o my_song.midi
```
This generates a standard MIDI file compatible with every DAW (GarageBand, Ableton, Logic) and MIDI player.

#### Compile to WAV
```bash
tapc my_song.tap -o my_song.wav --soundfont /path/to/generaluser.sf2
```
The compiler will render all MIDI instruments to stereo audio using your SoundFont.

### 5.2 Online Alternative
Use the web-based [TapStudio Editor](https://tapstudio.io/) for zero-install compilation to MIDI and WAV, ideal for beginners.

---

## 6. Advanced Features
### 6.1 Repeats & Section Markers
Save time by reusing song sections with built-in repeat tools:
```tapscript
# Repeat a section 2 times
repeat 2 {
  { C:q, G:q, Am:q, F:q }
}

# Segno + Fine markers for formal song structure
segno # Mark start of repeat section
{ Am:q, F:q }
repeat from segno 2 # Repeat from segno twice
fine # End of song marker

# Da Capo Al Fine: Repeat entire song from start to fine
dc al fine
```

### 6.2 Dynamics Control
Adjust volume levels globally or per-event:
1.  **Section-wide dynamics**: Use standard shorthands (`pp`, `p`, `mp`, `mf`, `f`, `ff`):
    ```tapscript
    # Soft verse
    dynamics: p {
      { C:q, G:q }
    }
    # Loud chorus
    dynamics: f {
      { C:q, G:q }
    }
    ```
2.  **Per-event velocity**: Override track volume for individual notes:
    ```tapscript
    # Loud single note (velocity 110)
    5/5:q velocity: 110
    # Soft single note (velocity 50)
    5/5:q velocity: 50
    ```

### 6.3 Key Changes
Modulate mid-song automatically: all named chords and key-based notes will adjust to the new key:
```tapscript
# Start in C Major
key: "C Major"
{ C:q, G:q }
# Modulate to G Major for final chorus
key: "G Major"
{ G:q, D:q }
```
Absolute fret positions like `1/5:q` will never change, regardless of key.

### 6.4 MIDI Control Changes (Effects)
Adjust MIDI CC values to add effects like wah, reverb, or pan:
```tapscript
# Enable wah pedal (CC 1 = modulation/wah)
cc: 1 60
5/5:q
# Reset wah to default
cc: 1 0
# Pan guitar to left channel
cc: 10 0
{ C:q }
# Pan guitar to right channel
cc: 10 127
{ G:q }
```

---

## Progressive Example 1: Simple Solo Melody
*Happy Birthday* polished with correct timing and lyrics (expanded from Section 3):
```tapscript
title: "Happy Birthday (Full Solo Melody)"
artist: "Traditional"
tempo: 110
time_signature: "4/4"
key: "C Major"

track SoloGuitar {
  instrument: "Acoustic Guitar (steel)"
  channel: 1
  volume: 80
  tuning: ["E2", "A2", "D3", "G3", "B3", "E4"]
}

# Measure 1
{ 1/0:e, 1/0:e, 1/2:q, 1/0:h } | Happy Birthday Dear
# Measure 2
{ 1/0:e, 1/0:e, 1/2:q, 1/0:h } | Happy Birthday Dear
# Measure 3
{ 3/0:e, 3/0:e, 1/2:q, 3/2:h } | Happy Birthday Dear Name
# Measure 4
{ 3/0:e, 3/0:e, 5/2:q, 1/0:h } | Happy Birthday Dear You
```

---

## Progressive Example 2: Fingerstyle Guitar Arrangement (Let It Be)
Intermediate example with dual voices, dynamics, and key changes:
```tapscript
title: "Let It Be (Fingerstyle Arrangement)"
artist: "The Beatles"
tempo: 84
time_signature: "4/4"
key: "C Major"

track FingerstyleGuitar {
  instrument: "Acoustic Guitar (steel)"
  tuning: ["E2", "A2", "D3", "G3", "B3", "E4"]
  voice ThumbBass { string_range: 1-3, velocity:75 }
  voice LeadMelody { string_range: 4-6, velocity:90 }
}

# Verse 1
{ ThumbBass: 1/0:q, LeadMelody: 4/0:q, 5/0:q } | Let it be, let it be
{ ThumbBass: 2/0:q, LeadMelody: 4/2:q } | Whisper words of wisdom

# Chorus with boosted dynamics
dynamics: mf {
  repeat 2 {
    { ThumbBass: 1/0:q, ThumbBass: 2/2:q, LeadMelody:4/3:q, 5/2:q }
    | Let it be, let it be
  }
}

# Final chorus with key change to D Major
key: "D Major"
dynamics: f {
  { ThumbBass:1/0:q, LeadMelody:4/0:q } | Let it be, let it be
}
```

---

## Progressive Example 3: Full Band Rock Arrangement
Advanced multi-track example with drums, bass, guitar, and vocals:
```tapscript
title: "Basic Rock Song"
artist: "Your Band"
tempo: 140
time_signature: "4/4"
key: "G Major"

# Track 1: Drums (standard MIDI channel 10)
track Drums {
  instrument: "Drum Kit"
  channel: 10
  volume: 100
}

# Track 2: Distorted Rhythm Guitar
track RhythmGuitar {
  instrument: "Distortion Guitar"
  channel: 2
  tuning: ["E2", "A2", "D3", "G3", "B3", "E4"]
  volume: 90
}

# Track 3: Electric Bass
track Bass {
  instrument: "Electric Bass (finger)"
  channel: 3
  tuning: ["E1", "A1", "D2", "G2"]
  volume: 85
}

# Track 4: Lead Vocals
track Vocals {
  instrument: "Voice"
  channel: 4
  volume: 95
}

# Standard rock drum loop
drum_beat: "kick q, hh e, snare q on 2+4, hh e" {
  repeat 4
}

# Verse 1
{ RhythmGuitar: G:q, D:q, Em:q, C:q }
{ Bass: 1/3:q, 2/0:q, 2/2:q, 3/0:q }
{ Vocals: | I woke up this morning with a song in my head }

# Chorus
dynamics: f {
  repeat 2 {
    { RhythmGuitar: G:h, D:h, Em:h, C:h }
    | Oh, oh, oh, let's rock this town
  }
}

# Guitar Solo Section
segno
{ RhythmGuitar: C:q, G:q, D:q, Em:q }
{ LeadGuitar: 5/5:e, 5/7:e, 5/8:e, 5/7:e }
repeat from segno 1
fine
```

---

## Troubleshooting & Pro Tips
1.  **MIDI Channel Conflicts**: Ensure each track uses a unique MIDI channel (only drums use channel 10 by standard)
2.  **Tuning Mismatches**: Double-check that tabbed chords have
