# Changelog

Notable changes, newest first. Dates are ISO 8601.

## 1.0.0 — 2026-08-13

A rebuild. One engine replaces the two that had drifted apart, and everything
that used to be compiled in — paths, model provider, rendering backend — is now
resolved at runtime.

### The compiler

- **One engine, both notations.** The labelled dialect (`Chords:`, `Melody:`,
  `@player`, scientific pitch) and the older relative one (roman numerals and
  scale degrees) are read by the same parser and compile through the same
  arranger.
- **Parsing and arranging are separate.** The parser builds a structural score
  and keeps tokens as written; the arranger decides timing. Transposition is
  parse, rewrite, emit — so it now moves the chord row, which the previous
  engine skipped.
- **A bar is one bar long.** Tokens in a bar divide it, so twelve tokens are
  triplets and a seventeenth cannot spill into the next bar. Fixes BUG-1 and
  BUG-2 in `examples/edge-cases/BUGS.md`. The old behaviour is available as
  `core.bar_fill = "grid"`, and reports every token it drops.
- **Repeated rows follow on.** Two `Melody:` rows in one section are eight bars,
  not four played twice. Rows of different kinds still sound together.
- **Time signatures are honoured**, including `3/4` and `6/8`.
- **Duration-by-spacing** (`C4~~~`) works in both dialects. It previously
  existed in only one engine.
- **Unclassifiable rows are reported, not guessed at.** The old heuristic could
  drop a melody silently if too few of its tokens looked like digits.
- Slot positions are computed from the bar start rather than accumulated, so
  timing cannot drift over a long piece.

### No dependencies

- MIDI writing and audio synthesis are written against the standard library. A
  clone with nothing installed compiles and produces sound. CI proves it on
  Python 3.10–3.13 across Linux, macOS and Windows with no install step.
- NumPy, fluidsynth, ffmpeg, mido and an audio player are detected at runtime
  and used when present. None is required.

### Portability

- Every path is derived from the environment, a project-local `.tapscript/`, or
  the platform convention. The hardcoded `~/.openclaw/workspace/output` and
  `/home/eileen/projects/tapscript-studio` are gone, and a test fails if either
  kind of path comes back.
- Layered configuration: defaults, user file, project file, environment, flags.
- Ports are configurable. The two engines both hardcoded 5557 and could not run
  together.

### Models

- **Any provider.** Anthropic, OpenAI, DeepSeek, OpenRouter, xAI, Gemini, Groq,
  Mistral, Together, Fireworks, Cerebras, Azure, Ollama, LM Studio, vLLM and
  anything else OpenAI-shaped. Providers are catalogue entries, so adding one is
  a JSON file.
- **Host bridge.** Running inside Claude Code, openclaw or a similar agent,
  TapScript can borrow that agent's model instead of asking for a second API
  key — by subprocess, by a documented file handshake, or over stdio.
- **Offline stub.** `--provider echo` returns valid notation with no network, so
  the agent loop and the interfaces can be used and tested with no connection.
- Keys are read from the environment or a separate credentials file that is
  never mixed into shareable configuration. `DEEPSEEK_API_KEY` is no longer
  found by grepping `~/.bashrc`.

### The agent

- A composer agent that writes and revises notation, and a build agent that
  probes the host and tailors the install to it.
- Twelve tools, sandboxed to a workspace. Notation is parsed before it is
  written, so invalid notation never reaches disk.
- Runs are bounded by a step budget and emit events, which is how the CLI shows
  progress and the web interface shows what happened.

### Interfaces

- A CLI with fifteen commands, `--json` on all of them, and useful exit codes.
- A terminal interface (`tapscript tui`) built on curses.
- A web interface (`tapscript serve`) on loopback, refusing cross-origin
  requests, serving rendered files only from the output directory.
- All three call the same `compile_text`, so compiling cannot come to mean
  different things in different places.

### Checking itself

- `specs/` states what the system promises and names the checks that prove it.
  `tapscript spec` runs them, `tapscript doctor` reports the host, and the build
  agent runs both to verify its own changes.
- 161 tests, plus a CI job that parses all 6,322 `.tap` files in the repository.

### Moved

- The previous engines, the image gallery, the MIDI studio, the fake book
  generator and the unrelated `src/` ports are in `legacy/`. Nothing imports
  them, nothing tests them, and the directory can be deleted.
- The old `docs/01`–`04` describe the old system and moved to `legacy/docs/`.

### Known limitations

- The built-in synthesiser is a preview renderer, not an instrument library.
  Install fluidsynth and a soundfont for accurate timbres.
- Audio is mono.
- The host bridge cannot stream and reports no token usage.
- `docs/fakebook/` is generated material and carries about 3,800 bar-count
  warnings. It parses; it is not all well written.
