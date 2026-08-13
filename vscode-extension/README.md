# TapScript — VS Code Extension

Syntax highlighting, snippets, and linting for **TapScript**, a plain-text music notation system for composing, sharing, and compiling music to MIDI and WAV.

## Features

### 🎵 Syntax Highlighting

Full TextMate grammar covering both TapScript notation styles:

- **v2 (labeled):** `Chords:`, `Melody:`, `Lyrics:`, `@player` lines with `[MetaData]` blocks
- **v1 (unlabeled):** Roman numeral chords (`i`, `IV`, `V7`) and scale-degree melodies (`1`, `5`, `b3`)

Highlighted elements:

| Element | Example | Scope Color |
|---------|---------|-------------|
| Track headers | `**TRACK: Neon Shadows**` | Entity |
| Section headers | `[V1]`, `[Chorus]`, `[Bridge]` | Heading |
| Track labels | `Chords:`, `Melody:`, `Lyrics:` | Keyword |
| Player tracks | `@wesley`, `@flash`, `@drums` | Variable |
| Notes (SPN) | `C4`, `Bb2`, `F#5` | Constant |
| Chord symbols | `Am`, `Cmaj7`, `Gsus4` | Entity |
| Roman numerals | `i`, `IV`, `vii°`, `bIII` | Entity |
| Scale degrees | `1`, `5`, `b3`, `#4` | Constant |
| Pipe delimiters | `\|` | Punctuation |
| Sustain/rest | `.` | Constant |
| Ties/continuation | `-` | Constant |
| Comments | `# ...` or `// ...` | Comment |
| Velocity | `vel: 70` | Constant |
| Repeat markers | `\|\|:`, `:\|\|` | Operator |
| Dynamics | `pp`, `mf`, `ff` | Constant |
| Metadata directives | `key:`, `tempo:`, `swing:`, `subdivision:` | Keyword |

### 📝 Snippets

| Trigger | Description |
|---------|-------------|
| `verse` | Complete verse block (v2 labeled) |
| `chorus` | Complete chorus block (v2 labeled) |
| `player` | Player/instrument track line |
| `meta` | Track header + metadata block |
| `section` | Section header |
| `chords` | Chord line |
| `melody` | Melody line |
| `lyrics` | Lyrics line |
| `dynamics` | Dynamics line |
| `art` | Articulation line |
| `keychange` | Key change block |
| `repeat` | Repeated section (v1) |
| `v1header` | v1 notation header |
| `v1section` | v1 notation section |

### ✅ Pipe Delimiter Linting

Real-time checks for:

- **Unbalanced pipe delimiters** — flags lines with odd pipe counts
- **Bar count mismatches** — flags lines within a section that have a different number of bars than other lines

Run a manual check via the Command Palette: **TapScript: Check Pipe Delimiter Balance**

## Installation

### From Source (Developer)

1. Navigate to the extension directory:
   ```bash
   cd tapscript-studio/vscode-extension
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Package the extension (requires `vsce`):
   ```bash
   npx @vscode/vsce package
   ```

4. Install the `.vsix` file:
   ```bash
   code --install-extension tapscript-0.1.0.vsix
   ```

### Or: Symlink for Development

For live development, symlink the folder into your VS Code extensions directory:

```bash
ln -s /path/to/tapscript-studio/vscode-extension ~/.vscode/extensions/tapscript
```

Then reload VS Code (`Ctrl+Shift+P` → "Reload Window").

### Or: Launch in Extension Development Host

Open the `vscode-extension/` folder in VS Code and press `F5` to launch a debug instance with the extension loaded.

## File Association

Files with the `.tap` extension are automatically recognized as TapScript files.

## Language Configuration

- **Comment toggle:** `#` (line comments), `//` (alternative line comments)
- **Bracket matching:** `[...]`, `{...}`, `(...)`, `|...|`
- **Auto-closing:** Brackets, pipes, and quotes auto-close
- **Folding:** Sections (`[Section]` headers) are foldable

## Notation Support

This extension supports both TapScript notation variants:

### v2 (Labeled — recommended for new work)

```tapscript
**TRACK: Neon Shadows**
[MetaData]
key: Am | tempo: 75 | swing: 10% | subdivision: 16th

[V1] (Verse - 4 Bars)
Chords:  | Am    .    | F     G    |
Melody: | E4    . . . | A4    . G4 E4 |
Lyrics: | I     . . . | write . in code |
@wesley | e2-a2-c3 . . | f2-a2-c3 g2-b2-d3 | vel: 60
```

### v1 (Unlabeled — Roman numerals)

```tapscript
Key: Am
Tempo: 75
Meter: 4/4

[Intro]
| i . . . | VI . . . | VII . . . | i . . . |
| 1 . 3 . | 5 . 3 . | 7 . 6 . | 1 . . . |
```

## Extension Settings

This extension does not contribute any settings yet. Future plans:

- Custom color themes for musical elements
- MIDI preview playback
- Live error checking via the TapScript compiler
- Auto-formatting and alignment

## License

MIT — part of the [TapScript Studio](https://github.com/SuperInstance/tapscript-studio) project.
