# TapScript: Interactive Music Notation for Markdown

## (1) Markdown Fence Syntax

```markdown
# My Song Document

Here's a track that renders as an interactive player:

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
```

## (2) VS Code Extension

### TextMate Grammar Scopes

```json
{
  "scopeName": "source.tapscript",
  "patterns": [
    { "include": "#track-header" },
    { "include": "#metadata" },
    { "include": "#section-header" },
    { "include": "#chords-line" },
    { "include": "#melody-line" },
    { "include": "#lyrics-line" },
    { "include": "#instrument-line" }
  ],
  "repository": {
    "track-header": {
      "match": "^\\*\\*(TRACK:.*?)\\*\\*",
      "captures": {
        "1": { "name": "entity.name.track.tapscript" }
      }
    },
    "metadata": {
      "match": "^\\[MetaData\\]",
      "name": "keyword.metadata.tapscript"
    },
    "section-header": {
      "match": "^\\[([A-Z0-9]+)\\]\\s*(?:\\((.*?)\\))?",
      "captures": {
        "1": { "name": "entity.name.section.tapscript" },
        "2": { "name": "comment.section-description.tapscript" }
      }
    },
    "chords-line": {
      "match": "^Chords:\\s*(.*)$",
      "captures": {
        "1": { "name": "entity.chord.tapscript" }
      }
    },
    "melody-line": {
      "match": "^Melody:\\s*(.*)$",
      "captures": {
        "1": { "name": "entity.melody.tapscript" }
      }
    },
    "lyrics-line": {
      "match": "^Lyrics:\\s*(.*)$",
      "captures": {
        "1": { "name": "string.lyrics.tapscript" }
      }
    },
    "instrument-line": {
      "match": "^@(\\w+)\\s+(.*)$",
      "captures": {
        "1": { "name": "entity.name.instrument.tapscript" },
        "2": { "name": "entity.pattern.tapscript" }
      }
    }
  }
}
```

### Webview Content Structure

```html
<div class="tapscript-player" data-key="Am" data-tempo="75">
  <div class="ts-header">
    <h3>Neon Shadows</h3>
    <div class="ts-controls">
      <button class="ts-play">▶</button>
      <button class="ts-pause">⏸</button>
      <button class="ts-download" data-format="wav">⬇ WAV</button>
      <button class="ts-download" data-format="midi">⬇ MIDI</button>
      <select class="ts-transpose">
        <option value="-2">-2 (Gm)</option>
        <option value="-1">-1 (G#m)</option>
        <option value="0" selected>0 (Am)</option>
        <option value="+1">+1 (Bbm)</option>
        <option value="+2">+2 (Bm)</option>
      </select>
    </div>
  </div>
  <div class="ts-timeline">
    <div class="ts-progress-bar">
      <div class="ts-progress-fill" style="width: 0%"></div>
    </div>
    <span class="ts-time">0:00 / 0:24</span>
  </div>
  <canvas class="ts-waveform" width="600" height="80"></canvas>
  <div class="ts-section-markers">
    <div class="ts-marker" data-section="V1" data-start="0">V1</div>
    <div class="ts-marker" data-section="C" data-start="8000">C</div>
  </div>
</div>
```

## (3) markdown-it Plugin Output

```html
<div class="tapscript-container">
  <div class="tapscript-player" data-key="Am" data-tempo="75" data-swing="10">
    <div class="ts-header">
      <h3>Neon Shadows</h3>
      <div class="ts-controls">
        <button class="ts-play" onclick="this.parentElement.parentElement.play()">▶ Play</button>
        <button class="ts-pause" onclick="this.parentElement.parentElement.pause()">⏸ Pause</button>
        <button class="ts-download-wav" onclick="downloadAudio('wav')">⬇ WAV</button>
        <button class="ts-download-midi" onclick="downloadAudio('midi')">⬇ MIDI</button>
      </div>
    </div>
    <audio class="ts-audio" controls style="display:none">
      <source src="data:audio/wav;base64,..." type="audio/wav">
    </audio>
    <canvas class="ts-waveform" width="600" height="100"></canvas>
  </div>
  <script>
    // Inline script for player initialization
    (function() {
      const player = document.querySelector('.tapscript-player');
      player.play = () => { /* Web Audio API implementation */ };
      player.pause = () => { /* Web Audio API implementation */ };
    })();
  </script>
</div>
```

## (4) Compiler Pipeline

### AST TypeScript Interfaces

```typescript
// AST Node Types
type NoteName = 'C' | 'D' | 'E' | 'F' | 'G' | 'A' | 'B';
type Accidental = '' | '#' | 'b' | '##' | 'bb';
type Octave = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9;

interface Note {
  name: NoteName;
  accidental: Accidental;
  octave: Octave;
}

interface Chord {
  root: Note;
  quality: 'maj' | 'min' | 'dim' | 'aug' | 'sus2' | 'sus4' | '7' | 'maj7' | 'min7' | 'dom7';
  bass?: Note;
  extension?: '9' | '11' | '13' | 'b9' | 'b5' | '#5';
}

interface Duration {
  beats: number;  // 1 = quarter, 0.5 = eighth, 0.25 = sixteenth
  isRest: boolean;
  isContinuation: boolean;  // for ties/sustains
}

interface Cell {
  note?: Note;      // for melody
  chord?: Chord;    // for harmony
  duration: Duration;
  velocity?: number; // 0-127
}

interface InstrumentPattern {
  instrumentId: string;
  cells: Cell[];
  velocity: number;
  pattern: string; // original text
}

interface Section {
  id: string;
  description?: string;
  bars: Bar[];
}

interface Bar {
  cells: Cell[];
  instruments: InstrumentPattern[];
  lyrics?: string[];
}

interface MetaData {
  key: string;
  tempo: number;
  swing: number; // 0-100%
  subdivision: '8th' | '16th' | '32nd';
}

interface TapScriptAST {
  trackName: string;
  metadata: MetaData;
  sections: Section[];
  errors: CompileError[];
}

interface CompileError {
  line: number;
  column: number;
  message: string;
  severity: 'error' | 'warning';
}
```

### Pipeline Stages

```typescript
class TapScriptCompiler {
  // Stage 1: Lexical Analysis (text → tokens)
  lexer(input: string): Token[] {
    // Token types: HEADER, METADATA, SECTION, CHORD, MELODY, LYRIC, INSTRUMENT
    // Returns array of tokens with line/column positions
  }

  // Stage 2: Parsing (tokens → AST)
  parser(tokens: Token[]): TapScriptAST {
    // Build hierarchical structure
  }

  // Stage 3: AST → MIDI
  toMidi(ast: TapScriptAST): MidiData {
    // Convert notes to MIDI numbers (C4 = 60)
    // Create MIDI events with timing
  }

  // Stage 4: MIDI → WAV
  toWav(midi: MidiData): AudioBuffer {
    // Use Web Audio API synthesis
    // Apply instrument sounds (synth, piano, drums)
    // Add swing timing
  }

  // Stage 5: WAV → Base64 for embedding
  wavToBase64(wav: AudioBuffer): string {
    // Convert to PCM and encode
  }
}
```

## (5) Interactive Transposition

### UX Flow

```typescript
class TranspositionHandler {
  selectedKey: Note;
  originalKey: Note;
  transposeInterval: number;

  initialize() {
    this.originalKey = this.parseKey(metadata.key);
    this.selectedKey = this.originalKey;
    
    // Add dropdown listener
    dropdown.addEventListener('change', (e) => {
      this.transposeInterval = this.getSemitones(
        this.selectedKey,
        this.parseKey(e.target.value)
      );
      this.retranspose();
    });
  }

  retranspose() {
    // Re-render with new key
    const newAST = this.transposeAST(originalAST, this.transposeInterval);
    
    // Regenerate MIDI
    const newMidi = compiler.toMidi(newAST);
    
    // Regenerate audio
    const newWav = compiler.toWav(newMidi);
    
    // Update player
    this.updatePlayer(newWav);
    
    // Update display
    this.updateChordDisplay(newAST);
    this.updateMelodyDisplay(newAST);
  }

  private transposeAST(ast: TapScriptAST, semitones: number): TapScriptAST {
    // Deep clone AST
    const newAST = structuredClone(ast);
    
    // Adjust key
    newAST.metadata.key = this.transposeKey(newAST.metadata.key, semitones);
    
    // Transpose all chords
    for (const section of newAST.sections) {
      for (const bar of section.bars) {
        for (const cell of bar.cells) {
          if (cell.chord) {
            cell.chord.root = this.transposeNote(cell.chord.root, semitones);
            if (cell.chord.bass) {
              cell.chord.bass = this.transposeNote(cell.chord.bass, semitones);
            }
          }
        }
      }
    }
    
    // Transpose all melodies
    for (const section of newAST.sections) {
      for (const bar of section.bars) {
        for (const cell of bar.cells) {
          if (cell.note) {
            cell.note = this.transposeNote(cell.note, semitones);
          }
        }
      }
    }
    
    // Transpose instrument patterns
    for (const section of newAST.sections) {
      for (const bar of section.bars) {
        for (const inst of bar.instruments) {
          for (const cell of inst.cells) {
            if (cell.note) {
              cell.note = this.transposeNote(cell.note, semitones);
            }
          }
        }
      }
    }
    
    return newAST;
  }

  private transposeNote(note: Note, semitones: number): Note {
    // Convert to MIDI number
    let midi = this.noteToMidi(note);
    
    // Apply transposition
    midi += semitones;
    
    // Convert back to Note
    return this.midiToNote(midi);
  }

  private transposeKey(key: string, semitones: number): string {
    // Parse key (e.g., "Am" → {root: A, mode: 'minor'})
    const parsed = this.parseKey(key);
    
    // Transpose root
    const newRoot = this.transposeNote(parsed.root, semitones);
    
    // Return new key
    return `${newRoot.name}${newRoot.accidental}${parsed.mode === 'minor' ? 'm' : ''}`;
  }
}
```

### Transposition Algorithm

```typescript
// Note to MIDI conversion
const NOTE_TO_MIDI: Record<string, number> = {
  'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11
};

const ACCIDENTAL_OFFSET: Record<string, number> = {
  '': 0, '#': 1, 'b': -1, '##': 2, 'bb': -2
};

function noteToMidi(note: Note): number {
  const base = NOTE_TO_MIDI[note.name];
  const accidental = ACCIDENTAL_OFFSET[note.accidental];
  return (note.octave + 1) * 12 + base + accidental;
}

function midiToNote(midi: number): Note {
  const octave = Math.floor(midi / 12) - 1;
  const pitchClass = midi % 12;
  
  // Map pitch class to note name + accidental
  const noteMap: Array<[string, string]> = [
    ['C', ''], ['C', '#'], ['D', ''], ['D', '#'], ['E', ''],
    ['F', ''], ['F', '#'], ['G', ''], ['G', '#'], ['A', ''],
    ['A', '#'], ['B', '']
  ];
  
  const [name, accidental] = noteMap[pitchClass];
  
  return {
    name: name as NoteName,
    accidental: accidental as Accidental,
    octave: octave as Octave
  };
}

// Key detection and parsing
function parseKey(keyString: string): { root: Note; mode: 'major' | 'minor' } {
  // Handle formats: "Am", "F#m", "Bb", "C"
  const match = keyString.match(/^([A-G])([#b]?)(m?)$/);
  
  return {
    root: {
      name: match[1] as NoteName,
      accidental: match[2] as Accidental,
      octave: 4
    },
    mode: match[3] === 'm' ? 'minor' : 'major'
  };
}

function getSemitones(fromKey: Note, toKey: Note): number {
  return noteToMidi(toKey) - noteToMidi(fromKey);
}
```

This design ensures the transposition works seamlessly with the compiler pipeline, maintaining audio quality while allowing real-time key changes without recompiling the entire song.
