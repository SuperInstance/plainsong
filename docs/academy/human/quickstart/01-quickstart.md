# TapScript Quickstart: For Humans Who’ve Never Seen It

**What is TapScript?**  
TapScript is a plain-text music notation that lets you write a full song (melody, chords, lyrics, and performance dynamics) in a simple, readable file—then compile it into MIDI or WAV with a single command.

---

## The 5 Lines of a TapScript Section

Every section (verse, chorus, etc.) is built from exactly five lines, in this order:

1. **Chords** – Chord symbols (e.g., `C`, `Am`, `G7`) placed above the beat.  
2. **Melody** – Note names (e.g., `E4`, `G#3`) or rests (`-`) matching the rhythm.  
3. **Lyrics** – Your words, one syllable per melody note. Use `*` for sustained syllables.  
4. **@player** – The instrument/sound (e.g., `@piano`, `@guitar`, `@synth`).  
5. **Dyn** – Dynamic markings like `p` (piano), `f` (forte), or `cresc`.  

Everything is aligned by **spaces**—think of it as a spreadsheet that becomes music.

---

## Your First 4-Bar Composition, Step by Step

Let’s write a simple, happy tune in C major. We’ll use 4/4 time, one chord per bar.

**Step 1: Create a new file** called `first.tap` and open it in any text editor.

**Step 2: Write the Chords line.**  
We’ll use `C`, `G`, `Am`, `F`—a classic pop progression. Each chord lasts one bar, so we write them with spaces to fill 4 beats:

```
C       G       Am      F
```

**Step 3: Write the Melody line.**  
Decide a rhythm. Let’s use quarter notes (one note per beat). For bar 1, play `E4`, `G4`, `C5`, `E5`. Bar 2: `D5`, `B4`, `G4`, `B4`. Bar 3: `A4`, `C5`, `E5`, `A5`. Bar 4: `G4`, `F4`, `E4`, `D4`. Align them under the chords:

```
C       G       Am      F
E4 G4 C5 E5  D5 B4 G4 B4  A4 C5 E5 A5  G4 F4 E4 D4
```

**Step 4: Add Lyrics.**  
Keep it simple: “La la la la, la la la la, la la la la, la la la la.” One syllable per note. Use `*` if a syllable lasts more than one note (not here).

```
C       G       Am      F
E4 G4 C5 E5  D5 B4 G4 B4  A4 C5 E5 A5  G4 F4 E4 D4
La la la la  La la la la  La la la la  La la la la
```

**Step 5: Assign a player.**  
Write `@piano` on the line below the lyrics. This applies to the whole section.

**Step 6: Add dynamics.**  
Write `mf` (mezzo-forte, medium loud) on the final line. You can add `cresc` or `dim` later.

Your first section now looks like:

```
C       G       Am      F
E4 G4 C5 E5  D5 B4 G4 B4  A4 C5 E5 A5  G4 F4 E4 D4
La la la la  La la la la  La la la la  La la la la
@piano
mf
```

**Step 7: Save and compile.**  
Run the TapScript compiler (you installed it earlier—it’s a command-line tool).  
`taps compile first.tap -o first.mid` for MIDI, or `-o first.wav` for audio.

That’s it! You’ve written and played your first piece.

---

## How to Play It (Compile to MIDI/WAV)

1. **Install TapScript** from the official site (it’s a single binary).  
2. In your terminal, navigate to the folder with your `.tap` file.  
3. Run:  
   - `taps compile yourfile.tap -o output.mid` → MIDI (plays in any DAW or media player).  
   - `taps compile yourfile.tap -o output.wav` → audio (renders with a built-in soundfont).  
4. Add `--tempo 120` to change speed (default is 100 BPM).  
5. For multiple sections, just write them one after another in the same file. The compiler stitches them together.

---

## Common Beginner Mistakes

1. **Misaligned columns** – Spaces matter! Use a monospace font. If lyrics and melody don’t line up, you’ll get garbled timing.  
2. **Forgetting the `@player` line** – Without it, the default is `piano`, but if you omit `@player`, you might get silence in WAV mode.  
3. **Writing chords as `C` but melody as `C4`** – Chords are *root names* (no octave), melody notes *must* have octave numbers.  
4. **Using commas or tabs**
