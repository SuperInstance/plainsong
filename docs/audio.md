# Audio Rendering

Plainsong compiles notation to MIDI and audio. The built-in synthesiser works with no dependencies, but there is a quality path — fluidsynth with a soundfont — one command away.

## The built-in renderer

When you compile, Plainsong writes audio with a pure-Python synthesiser:

```bash
plainsong compile song.song -o out.wav
```

No dependencies required. The output is WAV (mono, 44.1 kHz). The synthetic timbres are approximations, but the instrument selection, velocity, and panning are accurate.

`plainsong doctor` shows what you can use:

```bash
plainsong doctor
```

## The quality path: fluidsynth + soundfont

For instrument-accurate audio, install fluidsynth and a General MIDI soundfont. This renders from the same MIDI, but substitutes real instrument samples.

### macOS

Install fluidsynth:

```bash
brew install fluidsynth
```

Then install a General MIDI soundfont. Download one (e.g., [FluidR3 GM](https://sourceforge.net/projects/fluidsynth/files/)) and place it in `~/Library/Audio/Sounds/Banks/`:

```bash
# Expand to your Downloads folder and move it
mkdir -p ~/Library/Audio/Sounds/Banks
mv ~/Downloads/FluidR3-GM.sf2 ~/Library/Audio/Sounds/Banks/
```

Then compile:

```bash
plainsong compile song.song -o out.wav
```

Plainsong will detect fluidsynth and use it automatically. Check `plainsong doctor` to confirm a soundfont was found.

### Linux (Debian/Ubuntu)

```bash
sudo apt-get install fluidsynth
```

Then install a General MIDI soundfont. The most commonly packaged one is FluidR3:

```bash
sudo apt-get install fluid-soundfont-gm
```

This installs to `/usr/share/sounds/sf2/`, where Plainsong looks by default.

Then compile:

```bash
plainsong compile song.song -o out.wav
```

### Linux (Fedora/RHEL)

```bash
sudo dnf install fluidsynth
sudo dnf install soundfont2-default-gm
```

Then compile:

```bash
plainsong compile song.song -o out.wav
```

### Windows

Download fluidsynth from [the official releases](https://github.com/FluidSynth/fluidsynth/releases). Extract it and add the bin directory to your PATH, or provide the full path to `fluidsynth.exe`.

Then download a General MIDI soundfont. Common options:
- [FluidR3 GM](https://sourceforge.net/projects/fluidsynth/files/) — the most common choice
- [GeneralUser GS](https://schristianlins.github.io/musical-artifacts/generaluser-gs/) — high quality, lighter weight
- [Timbality](https://freepats.zenvoid.org/) — another quality option

Place the `.sf2` or `.sf3` file in a soundfont directory:
- `C:\soundfonts\` (Plainsong checks this first)
- `~\soundfonts\`
- Or set the environment variable `PLAINSONG_SOUNDFONT` to the full path

Then compile:

```bash
plainsong compile song.song -o out.wav
```

## Pointing to a soundfont

Plainsong searches for soundfonts in standard locations:

- `/usr/share/soundfonts`
- `/usr/share/sounds/sf2`
- `/usr/local/share/soundfonts`
- `/usr/local/share/generaluser-gs`
- `~/.local/share/soundfonts`
- `~/soundfonts`
- `~/Library/Audio/Sounds/Banks` (macOS)
- `C:/soundfonts` (Windows)

If your soundfont is elsewhere, set the `PLAINSONG_SOUNDFONT` environment variable:

```bash
export PLAINSONG_SOUNDFONT="/path/to/font.sf2"
plainsong compile song.song -o out.wav
```

Check what Plainsong found:

```bash
plainsong doctor | grep soundfont
```

## Output formats

The compiled audio is always WAV by default. To export to other formats, install ffmpeg and use the `-o` flag with a different suffix:

```bash
plainsong compile song.song -o out.mp3
plainsong compile song.song -o out.ogg
plainsong compile song.song -o out.flac
plainsong compile song.song -o out.m4a
```

ffmpeg must be installed:

```bash
# macOS
brew install ffmpeg

# Debian/Ubuntu
sudo apt-get install ffmpeg

# Fedora/RHEL
sudo dnf install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html or use scoop/chocolatey
```

## Playing from the terminal

`plainsong play` compiles and plays in one step:

```bash
plainsong play song.song
```

This requires an audio player. On Linux and macOS with PulseAudio/ALSA, it usually works. On Windows or with different audio setups, you may need to install ffmpeg (which includes ffplay):

```bash
# macOS
brew install ffmpeg

# Debian/Ubuntu
sudo apt-get install ffmpeg

# Windows
# Install ffmpeg from https://ffmpeg.org/download.html
```

## MIDI only

If you only need MIDI, no audio is needed at all:

```bash
plainsong compile song.song -o out.mid
```

Any DAW (Ableton, Logic, Studio One, Reaper, etc.) can open the MIDI and render it with its own instruments.

## Hardware MIDI

To stream MIDI to a connected instrument or synthesiser, install mido:

```bash
pip install mido python-rtmidi
```

Then list available MIDI ports:

```bash
plainsong doctor | grep midi_ports
```

If a port is open, compile will stream to it:

```bash
plainsong compile song.song --midi-port "Device Name"
```

## What the synthesiser actually does

The built-in renderer:
- Reads General MIDI program numbers and selects instrument samples (for fluidsynth) or synthesis parameters (built-in)
- Respects velocity across the full MIDI range (0-127)
- Handles note length, sustain, and release
- Applies pan and volume per voice
- Operates in real time: a 60-second score takes roughly 60 seconds to render

The pure-Python built-in synthesiser uses oscillators and an ADSR envelope. It is fast enough for interactive use but the timbres are synthetic. The fluidsynth path substitutes recorded instrument samples.

## Speeding up synthesis

If you have numpy installed, the built-in synthesiser is about 20x faster (CPU time):

```bash
pip install numpy
```

This is entirely optional. Without it, Python's native math handles it.

## Checking what's available

`plainsong doctor` shows what your machine can do:

```bash
plainsong doctor
```

`plainsong spec` verifies that the promises work:

```bash
plainsong spec
```

These tell you whether fluidsynth is installed, whether a soundfont was found, whether ffmpeg can convert formats, and whether an audio player is available.
